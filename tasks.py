import uuid
import time
import logging
from celery import chord, group
from celery_app import celery_app
from database import SessionLocal, RFPJob, RFPQuestionResponse, JobStatus, QuestionStatus
from llm_factory import RFPLLMFactory

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="tasks.process_rfp_document_task")
def process_rfp_document_task(self, job_id: str):
    """
    Producer task: Parses RFP document text, extracts questions using DeepInfra,
    creates question records, and fans out parallel execution via Celery chord/group.
    """
    db = SessionLocal()
    try:
        job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
        if not job:
            logger.error(f"RFPJob {job_id} not found in database.")
            return {"status": "error", "message": "Job not found"}

        job.status = JobStatus.PARSING
        db.commit()

        # Step 1: Extract questions using DeepInfra Llama 3
        questions = RFPLLMFactory.extract_questions(job.document_text)
        logger.info(f"Extracted {len(questions)} questions for RFPJob {job_id}")

        if not questions:
            job.status = JobStatus.COMPLETED
            job.summary_notes = "No questions found in document."
            db.commit()
            return {"status": "completed", "total_questions": 0}

        # Step 2: Save individual question records in DB
        question_records = []
        for idx, q_text in enumerate(questions, start=1):
            q_resp = RFPQuestionResponse(
                id=str(uuid.uuid4()),
                job_id=job.id,
                question_index=idx,
                question_text=q_text,
                status=QuestionStatus.PENDING
            )
            db.add(q_resp)
            question_records.append(q_resp)

        job.total_questions = len(question_records)
        job.status = JobStatus.PROCESSING
        db.commit()

        # Step 3: Fan-out parallel Celery tasks via chord
        header = [
            answer_question_task.s(q_resp.id, job.knowledge_base)
            for q_resp in question_records
        ]

        callback = aggregate_rfp_results_task.s(job_id)

        # Dispatch chord execution
        chord(header)(callback)

        return {
            "status": "processing",
            "job_id": job_id,
            "questions_count": len(question_records)
        }

    except Exception as e:
        logger.exception(f"Error in process_rfp_document_task for job {job_id}: {e}")
        job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.summary_notes = f"Failed during document parsing: {str(e)}"
            db.commit()
        raise e
    finally:
        db.close()


@celery_app.task(bind=True, name="tasks.answer_question_task")
def answer_question_task(self, question_response_id: str, knowledge_base: str):
    """
    Parallel Worker Task: Retrieves local context via Ollama embeddings and
    synthesizes a persuasive answer using OpenAI GPT-4o.
    """
    db = SessionLocal()
    try:
        q_resp = db.query(RFPQuestionResponse).filter(RFPQuestionResponse.id == question_response_id).first()
        if not q_resp:
            logger.error(f"RFPQuestionResponse {question_response_id} not found.")
            return {"status": "error", "id": question_response_id}

        q_resp.status = QuestionStatus.PROCESSING
        db.commit()

        # Step 1: Retrieve context via local Ollama embedding search
        context = RFPLLMFactory.embed_and_retrieve_context(q_resp.question_text, knowledge_base)

        # Step 2: Synthesize persuasive response via OpenAI GPT-4o
        synth_result = RFPLLMFactory.synthesize_persuasive_answer(q_resp.question_text, context)

        # Step 3: Save results
        q_resp.retrieved_context = context
        q_resp.generated_answer = synth_result["answer"]
        q_resp.provider_used = synth_result["provider"]
        q_resp.latency_seconds = synth_result["latency_seconds"]
        q_resp.status = QuestionStatus.COMPLETED
        db.commit()

        return {
            "status": "completed",
            "question_id": q_resp.id,
            "question_index": q_resp.question_index,
            "provider": synth_result["provider"],
            "latency_seconds": synth_result["latency_seconds"]
        }

    except Exception as e:
        logger.exception(f"Error answering question {question_response_id}: {e}")
        q_resp = db.query(RFPQuestionResponse).filter(RFPQuestionResponse.id == question_response_id).first()
        if q_resp:
            q_resp.status = QuestionStatus.FAILED
            q_resp.generated_answer = f"Generation failed: {str(e)}"
            db.commit()
        return {"status": "failed", "question_id": question_response_id, "error": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True, name="tasks.aggregate_rfp_results_task")
def aggregate_rfp_results_task(self, results: list, job_id: str):
    """
    Chord Callback Task: Aggregates parallel question answers, computes job metrics,
    and updates job status to COMPLETED in database.
    """
    db = SessionLocal()
    try:
        job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
        if not job:
            logger.error(f"RFPJob {job_id} not found for aggregation.")
            return {"status": "error", "job_id": job_id}

        questions = db.query(RFPQuestionResponse).filter(RFPQuestionResponse.job_id == job_id).all()
        completed_count = sum(1 for q in questions if q.status == QuestionStatus.COMPLETED)

        job.completed_questions = completed_count
        if completed_count == job.total_questions or job.total_questions == 0:
            job.status = JobStatus.COMPLETED
        else:
            job.status = JobStatus.COMPLETED  # Partial completion handled gracefully

        # Calculate execution duration
        if job.created_at:
            time_diff = (job.updated_at - job.created_at).total_seconds()
            job.execution_time_seconds = round(max(time_diff, 0.1), 3)

        job.summary_notes = (
            f"Successfully answered {completed_count}/{job.total_questions} questions "
            f"across parallel worker tasks."
        )
        db.commit()

        logger.info(f"RFPJob {job_id} completed: {job.summary_notes}")
        return {
            "status": "completed",
            "job_id": job_id,
            "total_questions": job.total_questions,
            "completed_questions": completed_count,
            "execution_time_seconds": job.execution_time_seconds
        }

    except Exception as e:
        logger.exception(f"Error aggregating RFPJob {job_id}: {e}")
        job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.summary_notes = f"Aggregation error: {str(e)}"
            db.commit()
        raise e
    finally:
        db.close()

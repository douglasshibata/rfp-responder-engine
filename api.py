import uuid
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db, RFPJob, RFPQuestionResponse, JobStatus
from tasks import process_rfp_document_task

router = APIRouter(prefix="/api/v1/rfp", tags=["RFP Responder"])

class RFPSubmitRequest(BaseModel):
    title: Optional[str] = Field("Enterprise RFP", description="Title or name of the RFP/Tender")
    document_text: str = Field(..., min_length=10, description="Full text of the RFP document containing questions")
    knowledge_base: Optional[str] = Field(None, description="Internal company knowledge base / past proposal context")

class RFPSubmitResponse(BaseModel):
    job_id: str
    title: str
    status: str
    message: str

class QuestionResponseSchema(BaseModel):
    id: str
    question_index: int
    question_text: str
    retrieved_context: Optional[str] = None
    generated_answer: Optional[str] = None
    provider_used: Optional[str] = None
    status: str
    latency_seconds: Optional[float] = None

class RFPJobStatusResponse(BaseModel):
    job_id: str
    title: str
    status: str
    progress_percentage: float
    total_questions: int
    completed_questions: int
    execution_time_seconds: Optional[float] = None
    created_at: str
    updated_at: str
    summary_notes: Optional[str] = None

class RFPJobResultsResponse(BaseModel):
    job_id: str
    title: str
    status: str
    total_questions: int
    execution_time_seconds: Optional[float] = None
    questions: List[QuestionResponseSchema]


@router.post("/submit", response_model=RFPSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_rfp_job(payload: RFPSubmitRequest, db: Session = Depends(get_db)):
    """
    Submits an RFP document for automated parsing and multi-provider question answering.
    Pushes parsing task to Redis queue for asynchronous Celery worker processing.
    """
    job_id = str(uuid.uuid4())
    job = RFPJob(
        id=job_id,
        title=payload.title or "Enterprise RFP",
        document_text=payload.document_text,
        knowledge_base=payload.knowledge_base,
        status=JobStatus.PENDING,
        total_questions=0,
        completed_questions=0
    )
    db.add(job)
    db.commit()

    # Dispatch Celery task
    process_rfp_document_task.delay(job_id)

    return RFPSubmitResponse(
        job_id=job_id,
        title=job.title,
        status=JobStatus.PENDING.value,
        message="RFP document submitted successfully. Processing initialized asynchronously."
    )


@router.get("/job/{job_id}", response_model=RFPJobStatusResponse)
def get_rfp_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Polls status and execution progress of an RFP processing job.
    """
    job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFP job with ID {job_id} not found."
        )

    progress = 0.0
    if job.total_questions > 0:
        progress = round((job.completed_questions / job.total_questions) * 100.0, 1)
    elif job.status == JobStatus.COMPLETED:
        progress = 100.0

    return RFPJobStatusResponse(
        job_id=job.id,
        title=job.title,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        progress_percentage=progress,
        total_questions=job.total_questions,
        completed_questions=job.completed_questions,
        execution_time_seconds=job.execution_time_seconds,
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
        summary_notes=job.summary_notes
    )


@router.get("/job/{job_id}/results", response_model=RFPJobResultsResponse)
def get_rfp_job_results(job_id: str, db: Session = Depends(get_db)):
    """
    Retrieves extracted questions and synthesized answers for an RFP job.
    """
    job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RFP job with ID {job_id} not found."
        )

    questions_db = db.query(RFPQuestionResponse).filter(
        RFPQuestionResponse.job_id == job_id
    ).order_by(RFPQuestionResponse.question_index.asc()).all()

    questions_schema = [
        QuestionResponseSchema(
            id=q.id,
            question_index=q.question_index,
            question_text=q.question_text,
            retrieved_context=q.retrieved_context,
            generated_answer=q.generated_answer,
            provider_used=q.provider_used,
            status=q.status.value if hasattr(q.status, "value") else str(q.status),
            latency_seconds=q.latency_seconds
        )
        for q in questions_db
    ]

    return RFPJobResultsResponse(
        job_id=job.id,
        title=job.title,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        total_questions=job.total_questions,
        execution_time_seconds=job.execution_time_seconds,
        questions=questions_schema
    )

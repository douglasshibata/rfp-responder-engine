import os
import sys
import uuid
import pytest
from fastapi.testclient import TestClient

# Ensure rfp-responder-engine is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import settings
from database import init_db, SessionLocal, RFPJob, RFPQuestionResponse, JobStatus, QuestionStatus
from llm_factory import RFPLLMFactory
from celery_app import celery_app
from tasks import process_rfp_document_task, answer_question_task, aggregate_rfp_results_task
from main import app

@pytest.fixture(autouse=True)
def setup_test_env():
    """Sets up test database and configures Celery for eager synchronous execution."""
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    init_db()

def test_database_models_and_session():
    """Tests SQLAlchemy ORM job and question response records creation and relationship."""
    db = SessionLocal()
    job_id = str(uuid.uuid4())
    job = RFPJob(
        id=job_id,
        title="Test Security RFP",
        document_text="Q1. What is your data retention policy?",
        knowledge_base="Data is retained for 7 years according to compliance rules."
    )
    db.add(job)
    db.commit()

    q_id = str(uuid.uuid4())
    q_resp = RFPQuestionResponse(
        id=q_id,
        job_id=job_id,
        question_index=1,
        question_text="What is your data retention policy?",
        status=QuestionStatus.PENDING
    )
    db.add(q_resp)
    db.commit()

    saved_job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
    assert saved_job is not None
    assert saved_job.title == "Test Security RFP"
    assert len(saved_job.questions) == 1
    assert saved_job.questions[0].question_text == "What is your data retention policy?"
    db.close()

def test_llm_factory_routing():
    """Tests RFPLLMFactory question extraction, context retrieval, and answer synthesis."""
    doc_text = "1. How do you handle disaster recovery?\n2. What is your SLA uptime guarantee?"
    questions = RFPLLMFactory.extract_questions(doc_text)
    assert isinstance(questions, list)
    assert len(questions) >= 2

    kb = "We offer 99.99% SLA uptime with automated multi-region disaster recovery."
    context = RFPLLMFactory.embed_and_retrieve_context(questions[0], kb)
    assert len(context) > 0

    synth = RFPLLMFactory.synthesize_persuasive_answer(questions[0], context)
    assert "answer" in synth
    assert "provider" in synth
    assert "latency_seconds" in synth

def test_celery_task_chord_pipeline():
    """Tests end-to-end Celery task chord fan-out and result aggregation in eager mode."""
    db = SessionLocal()
    job_id = str(uuid.uuid4())
    job = RFPJob(
        id=job_id,
        title="Automated Celery Test RFP",
        document_text="Q1. What encryption standards are used?\nQ2. Is SOC2 compliance available?",
        knowledge_base="Encryption at rest is AES-256 and in transit TLS 1.3. We hold SOC2 Type II certification."
    )
    db.add(job)
    db.commit()
    db.close()

    task_res = process_rfp_document_task.delay(job_id)
    assert task_res is not None

    db = SessionLocal()
    updated_job = db.query(RFPJob).filter(RFPJob.id == job_id).first()
    assert updated_job.status == JobStatus.COMPLETED
    assert updated_job.total_questions == 2
    assert updated_job.completed_questions == 2
    assert len(updated_job.questions) == 2
    for q in updated_job.questions:
        assert q.status == QuestionStatus.COMPLETED
        assert q.generated_answer is not None
    db.close()

def test_fastapi_rest_endpoints():
    """Tests FastAPI web gateway routes: /health, /submit, /job/{id}, and /job/{id}/results."""
    client = TestClient(app)

    # Health check
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "online"

    # Submit RFP document
    submit_payload = {
        "title": "GovCloud RFP Bid",
        "document_text": "Q1. Do you support ISO27001 compliance?\nQ2. What is your incident response SLA?",
        "knowledge_base": "We are ISO27001 certified with a 15-minute incident response SLA for critical events."
    }
    sub_resp = client.post("/api/v1/rfp/submit", json=submit_payload)
    assert sub_resp.status_code == 202
    data = sub_resp.json()
    assert "job_id" in data
    job_id = data["job_id"]

    # Get job status
    status_resp = client.get(f"/api/v1/rfp/job/{job_id}")
    assert status_resp.status_code == 200
    st_data = status_resp.json()
    assert st_data["job_id"] == job_id
    assert st_data["status"] == "COMPLETED"
    assert st_data["progress_percentage"] == 100.0
    assert st_data["total_questions"] == 2

    # Get job results
    results_resp = client.get(f"/api/v1/rfp/job/{job_id}/results")
    assert results_resp.status_code == 200
    res_data = results_resp.json()
    assert res_data["job_id"] == job_id
    assert len(res_data["questions"]) == 2
    assert "ISO27001" in res_data["questions"][0]["question_text"]

    # Test 404 for non-existent job
    fake_id = str(uuid.uuid4())
    nf_resp = client.get(f"/api/v1/rfp/job/{fake_id}")
    assert nf_resp.status_code == 404

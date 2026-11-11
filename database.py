import enum
import datetime
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, Enum, ForeignKey, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class QuestionStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class RFPJob(Base):
    __tablename__ = "rfp_jobs"

    id = Column(String(36), primary_key=True, index=True)
    title = Column(String(255), nullable=False, default="Untitled RFP")
    document_text = Column(Text, nullable=False)
    knowledge_base = Column(Text, nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, index=True)
    total_questions = Column(Integer, default=0)
    completed_questions = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    execution_time_seconds = Column(Float, nullable=True)
    summary_notes = Column(Text, nullable=True)

    questions = relationship("RFPQuestionResponse", back_populates="job", cascade="all, delete-orphan")

class RFPQuestionResponse(Base):
    __tablename__ = "rfp_question_responses"

    id = Column(String(36), primary_key=True, index=True)
    job_id = Column(String(36), ForeignKey("rfp_jobs.id"), nullable=False, index=True)
    question_index = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    retrieved_context = Column(Text, nullable=True)
    generated_answer = Column(Text, nullable=True)
    provider_used = Column(String(50), nullable=True)
    status = Column(Enum(QuestionStatus), default=QuestionStatus.PENDING, index=True)
    latency_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    job = relationship("RFPJob", back_populates="questions")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 📄 Automated RFP & Tender Responder Engine (B2B SaaS)

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-green)](https://fastapi.tiangolo.com/)
[![Celery](https://img.shields.io/badge/Queue-Celery%20%2B%20Redis-red)](https://docs.celeryq.dev/)
[![LangChain](https://img.shields.io/badge/LLM-Multi--Provider%20LangChain-purple)](https://www.langchain.com/)

An enterprise-grade, asynchronous event-driven **Automated RFP & Tender Responder Engine** built with **FastAPI**, **Redis**, **Celery**, **SQLAlchemy**, and a **Multi-Provider LangChain strategy** (routing across **DeepInfra**, **Ollama**, and **OpenAI**).

---

## 🏛️ System Architecture

The diagram below illustrates how data flows asynchronously from the web client, through the FastAPI gateway, onto the Redis message queue, and across parallel Celery workers orchestrating specialized multi-provider LLMs before persisting results into the database.

```mermaid
flowchart TD
    subgraph Client ["Frontend / Client Application"]
        A[Client Web App]
    end

    subgraph Gateway ["API Gateway (FastAPI)"]
        B[POST /api/v1/rfp/submit]
        C[GET /api/v1/rfp/job/job_id]
        D[GET /api/v1/rfp/job/job_id/results]
    end

    subgraph Storage ["Database & Message Queue"]
        E[(PostgreSQL / SQLite)]
        F[Redis Message Broker]
    end

    subgraph Workers ["Celery Distributed Worker Pool"]
        G[Producer Task: process_rfp_document_task]
        H[Worker Task 1: answer_question_task]
        I[Worker Task 2: answer_question_task]
        J[Worker Task N: answer_question_task]
        K[Chord Callback: aggregate_rfp_results_task]
    end

    subgraph LLM_Providers ["Multi-Provider LLM Routing Engine"]
        L[DeepInfra - Llama 3\nHigh-Volume Question Extraction]
        M[Ollama - Local Embeddings\nPrivacy-First Knowledge Base Search]
        N[OpenAI - GPT-4o\nPersuasive Answer Synthesis]
    end

    %% Flow connections
    A -->|1. Submit RFP Document & KB| B
    B -->|2. Create Job Record PENDING| E
    B -->|3. Push Task to Broker| F
    A -->|Poll Status & Progress| C
    C -->|Read Progress %| E
    A -->|Fetch Final Proposal| D
    D -->|Read Q&A Results| E

    F -->|4. Consume Task| G
    G -->|5. Extract Questions via| L
    G -->|6. Save Questions PENDING| E
    G -->|7. Fan-out Parallel Chord| H & I & J

    H -->|8a. Retrieve Local KB Context| M
    H -->|8b. Synthesize Answer| N
    I -->|8a. Retrieve Local KB Context| M
    I -->|8b. Synthesize Answer| N
    J -->|8a. Retrieve Local KB Context| M
    J -->|8b. Synthesize Answer| N

    H & I & J -->|9. Update Question Record COMPLETED| E
    H & I & J -->|10. Trigger Callback| K
    K -->|11. Update Job Status COMPLETED| E
```

---

## ⚡ Multi-Step Worker Pipelines (Celery Chords / Groups)

1. **Document Ingestion & Question Extraction (`process_rfp_document_task`)**:
   - The producer task receives the raw RFP document text.
   - Routes question extraction to **DeepInfra (Llama 3)** to parse and extract 50+ individual requirement questions in seconds.
   - Writes `RFPQuestionResponse` records with state `PENDING` into the database.

2. **Parallel Fan-out (`answer_question_task`)**:
   - Constructs a **Celery Chord** header distributing `N` parallel tasks across Celery worker processes.
   - Each worker retrieves relevant company context using **Ollama local vector embeddings** (maintaining corporate data privacy).
   - Each worker routes context + question to **OpenAI (GPT-4o)** to generate a persuasive, compliant proposal answer.

3. **Chord Aggregation (`aggregate_rfp_results_task`)**:
   - Executes automatically as a callback once all parallel question tasks finish.
   - Calculates total execution duration, updates completion counts, and transitions job state to `COMPLETED`.

---

## 🤖 Multi-Provider LLM Strategy

| Task | Selected Provider | Model | Rationale |
| :--- | :--- | :--- | :--- |
| **Question Extraction** | **DeepInfra** | `meta-llama/Meta-Llama-3.1-8B-Instruct` | Ultra-fast, highly cost-effective extraction over 100+ page documents. |
| **Context Retrieval** | **Ollama** | `nomic-embed-text` / `llama3.2` | Runs 100% locally on internal infrastructure; prevents proprietary company knowledge base leakage. |
| **Answer Synthesis** | **OpenAI** | `gpt-4o` | Superior nuance, reasoning, and persuasive writing quality for winning multi-million dollar tenders. |

---

## 📊 Database Schema & State Management

The system tracks asynchronous job states via two main tables in SQLite/PostgreSQL:

- `rfp_jobs`:
  - `id` (UUID primary key)
  - `status`: `PENDING` ➔ `PARSING` ➔ `PROCESSING` ➔ `COMPLETED` / `FAILED`
  - `total_questions`, `completed_questions`, `execution_time_seconds`
- `rfp_question_responses`:
  - `id` (UUID primary key), `job_id` (foreign key)
  - `question_index`, `question_text`, `retrieved_context`, `generated_answer`
  - `provider_used`, `latency_seconds`, `status`

The frontend polls `GET /api/v1/rfp/job/{job_id}` to calculate real-time completion progress (`progress_percentage = completed_questions / total_questions * 100`).

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.11+
- Redis Server (Running on `redis://localhost:6379/0` or via Docker)

### 1. Installation

```bash
cd rfp-responder-engine
pip install -r requirements.txt
```

### 2. Run Redis Broker (Docker)

```bash
docker run -d --name redis-rfp -p 6379:6379 redis:alpine
```

### 3. Start Celery Worker

```bash
celery -A tasks.celery_app worker --loglevel=info
```

### 4. Start FastAPI Gateway

```bash
python3 main.py
```

### 5. API Testing

Submit RFP Document:
```bash
curl -X POST "http://localhost:8000/api/v1/rfp/submit" \
     -H "Content-Type: application/json" \
     -d '{
       "title": "Cloud Platform Tender",
       "document_text": "Q1. What is your data encryption policy?\nQ2. Do you support SAML SSO?",
       "knowledge_base": "We enforce AES-256 encryption at rest and TLS 1.3 in transit. We support SAML 2.0 SSO via Okta."
     }'
```

Check Job Status:
```bash
curl "http://localhost:8000/api/v1/rfp/job/<JOB_ID>"
```

Get Complete Proposal Results:
```bash
curl "http://localhost:8000/api/v1/rfp/job/<JOB_ID>/results"
```

---

## 🧪 Automated Testing

Run the unit and integration test suite:

```bash
PYTHONPATH=. pytest tests/ -v
```

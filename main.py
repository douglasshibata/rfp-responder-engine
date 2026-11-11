import datetime
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from api import router as rfp_router

# Initialize database schema
init_db()

app = FastAPI(
    title=settings.APP_NAME,
    description="Automated RFP & Tender Responder Engine using LangChain multi-provider routing and Redis/Celery queue.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rfp_router)

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

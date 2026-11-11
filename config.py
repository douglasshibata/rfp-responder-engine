import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Automated RFP & Tender Responder Engine"
    API_V1_STR: str = "/api/v1"

    # Storage & Queue
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./rfp_engine.db")

    # Celery Configuration
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
    CELERY_TASK_ALWAYS_EAGER: bool = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"

    # Multi-Provider LLM Settings
    # DeepInfra: Cheap, high-volume extraction & parsing
    DEEPINFRA_API_KEY: str = os.getenv("DEEPINFRA_API_KEY", "mock_deepinfra_key")
    DEEPINFRA_BASE_URL: str = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai")
    DEEPINFRA_MODEL: str = os.getenv("DEEPINFRA_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")

    # Ollama: Local privacy-first vector embeddings & knowledge base search
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # OpenAI: Complex reasoning & persuasive answer synthesis
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "mock_openai_key")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

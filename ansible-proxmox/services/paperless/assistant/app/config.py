import os
from pathlib import Path
from pydantic import BaseModel

class Settings(BaseModel):
    # Paperless API
    paperless_api_url: str = os.getenv("PAPERLESS_API_URL", "http://paperless:8000/api").rstrip("/")
    paperless_api_token: str = os.getenv("PAPERLESS_API_TOKEN", "")
    base_paperless_url: str = os.getenv("BASE_PAPERLESS_URL", "https://paperless.davidharo.store").rstrip("/")

    # AI / LLM Configuration (Defaulting to Google Gemini OpenAI-compatible endpoint)
    ai_base_url: str = os.getenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    ai_model: str = os.getenv("AI_MODEL", os.getenv("PAPERLESS_ASSISTANT_MODEL", "gemini-3.5-flash-lite"))

    # Local Persistence
    data_dir: Path = Path(os.getenv("DATA_DIR", "/app/data"))
    db_path: Path = Path(os.getenv("DATA_DIR", "/app/data")) / "assistant.db"

    # Financial / Accounting heuristics
    financial_tags: list[str] = [
        "banco", "factura", "recibo", "estado de cuenta", "nomina", "sat", 
        "tarjeta", "cfdi", "finanzas", "gastos", "inversion"
    ]

settings = Settings()

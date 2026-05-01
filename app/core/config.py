import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    app_name: str = "Chatbot Tư vấn Tuyển sinh"
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    chat_history_limit: int = int(os.getenv("CHAT_HISTORY_LIMIT", 30))
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key")
    port: int = int(os.getenv("PORT", 8001))
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    mongo_url: str = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "ai_chatbot")

    # SGK PDF Processing
    storage_path: str = os.getenv("STORAGE_PATH", "./storage")
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    mathpix_app_id: Optional[str] = os.getenv("MATHPIX_APP_ID")
    mathpix_app_key: Optional[str] = os.getenv("MATHPIX_APP_KEY")
    mathpix_enabled: bool = os.getenv("MATHPIX_ENABLED", "false").lower() == "true"
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", 50))

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
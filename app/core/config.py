from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Chatbot Tư vấn Tuyển sinh"
    debug: bool = False
    secret_key: str = "your-secret-key"
    port: int = 8001
    api_prefix: str = "/api/v1"

    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    chat_history_limit: int = 30

    # MongoDB
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "sgk_toan"

    # Redis
    redis_url: str = "redis://localhost:6379"
    enable_rate_limit: bool = True

    # Logging
    log_level: str = "INFO"

    # Internal API Key (shared with BE to prevent direct access)
    internal_api_key: Optional[str] = "change-me-in-production"

    # SGK PDF Processing
    storage_path: str = "./storage"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    mathpix_app_id: Optional[str] = None
    mathpix_app_key: Optional[str] = None
    mathpix_enabled: bool = False
    max_file_size_mb: int = 50

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
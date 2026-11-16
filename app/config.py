from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    database_url: str = ""
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"
    groq_transcription_model: str = "whisper-large-v3-turbo"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

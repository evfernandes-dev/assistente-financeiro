import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        telegram_bot_token="test-token",
        telegram_webhook_secret="test-secret",
        database_url="postgresql://test:test@localhost/test",
        groq_api_key="test-groq-key",
        groq_model="test-model",
        groq_transcription_model="test-whisper",
    )

from __future__ import annotations

import httpx

from .config import Settings
from .models import AudioInput

GROQ_CHAT_TIMEOUT_SECONDS = 25.0
GROQ_TRANSCRIPTION_TIMEOUT_SECONDS = 60.0
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class GroqError(RuntimeError):
    pass


def _truncate_detail(text: str, limit: int = 300) -> str:
    return text[:limit]


class GroqClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
        payload: dict[str, object] = {
            "model": self._settings.groq_model,
            "temperature": 0.2,
            "max_tokens": 800,
            "messages": messages,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=GROQ_CHAT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"authorization": f"Bearer {self._settings.groq_api_key}"},
                json=payload,
            )

        if response.status_code >= 400:
            raise GroqError(
                f"Groq chat falhou: {response.status_code} {_truncate_detail(response.text)}"
            )

        try:
            data = response.json()
        except ValueError as error:
            raise GroqError("Groq retornou JSON inválido") from error

        choices = data.get("choices") or []
        content = choices[0].get("message", {}).get("content") if choices else None

        if not isinstance(content, str) or not content.strip():
            raise GroqError("Groq retornou resposta vazia")

        return content.strip()

    async def transcribe(self, audio: AudioInput) -> str:
        if not audio.data:
            raise GroqError("Áudio vazio")

        if len(audio.data) > MAX_AUDIO_BYTES:
            raise GroqError("Áudio acima do limite de 25 MB")

        mime_type = (audio.mime_type or "audio/ogg").replace("audio/oga", "audio/ogg")
        file_name = (audio.file_name or "audio.ogg").replace(".oga", ".ogg")

        async with httpx.AsyncClient(timeout=GROQ_TRANSCRIPTION_TIMEOUT_SECONDS) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"authorization": f"Bearer {self._settings.groq_api_key}"},
                files={"file": (file_name, audio.data, mime_type)},
                data={
                    "model": self._settings.groq_transcription_model,
                    "language": "pt",
                    "response_format": "json",
                    "temperature": "0",
                },
            )

        if response.status_code >= 400:
            raise GroqError(
                f"Transcrição Groq falhou: {response.status_code} {_truncate_detail(response.text)}"
            )

        try:
            data = response.json()
        except ValueError as error:
            raise GroqError("Groq retornou JSON inválido") from error

        text = data.get("text")

        if not isinstance(text, str) or not text.strip():
            raise GroqError("Transcrição vazia")

        return text.strip()

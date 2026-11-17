from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from .ai import handle_financial_message
from .audio import MAX_TELEGRAM_AUDIO_BYTES, download_telegram_audio
from .config import Settings
from .db import FinanceRepository
from .groq import GroqClient
from .models import AudioInput, TelegramAudioFile

logger = logging.getLogger(__name__)

TELEGRAM_TIMEOUT_SECONDS = 15.0
TELEGRAM_MESSAGE_LIMIT = 4000


class TelegramGateway(Protocol):
    async def send_message(self, chat_id: int, text: str) -> None: ...

    async def download_audio(self, file: TelegramAudioFile) -> AudioInput: ...


def split_message(text: str, max_length: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    current = ""

    for line in text.split("\n"):
        while len(line) > max_length:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:max_length])
            line = line[max_length:]

        if len(current) + len(line) + (1 if current else 0) > max_length:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)

    return chunks


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def _call_api(self, method: str, payload: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=TELEGRAM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self._settings.telegram_bot_token}/{method}",
                json=payload,
            )

        try:
            data = response.json()
        except ValueError as error:
            raise RuntimeError(f"Telegram {method} retornou JSON inválido") from error

        if response.status_code >= 400 or not data.get("ok"):
            detail = data.get("description") or response.status_code
            raise RuntimeError(f"Telegram {method} falhou: {detail}")

        return data.get("result")

    async def send_message(self, chat_id: int, text: str) -> None:
        for chunk in split_message(text):
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            try:
                await self._call_api("sendMessage", payload)
            except RuntimeError:
                await self._call_api(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": chunk,
                        "disable_web_page_preview": True,
                    },
                )

    async def download_audio(self, file: TelegramAudioFile) -> AudioInput:
        return await download_telegram_audio(file, self._settings)


async def handle_telegram_update(
    update: dict[str, Any],
    *,
    repo: FinanceRepository,
    groq: GroqClient,
    telegram: TelegramGateway,
) -> None:
    message = update.get("message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        return

    chat_id = chat.get("id")
    if not isinstance(chat_id, int) or isinstance(chat_id, bool):
        return

    try:
        text_value = message.get("text")
        text = text_value.strip() if isinstance(text_value, str) else ""
        source = "text"

        audio_file = message.get("voice") or message.get("audio")
        if not text and isinstance(audio_file, dict):
            file_size = audio_file.get("file_size")
            if isinstance(file_size, int) and file_size > MAX_TELEGRAM_AUDIO_BYTES:
                await telegram.send_message(
                    chat_id,
                    "⚠️ Áudio muito grande. Envie um áudio de até 20 MB.",
                )
                return

            file_id = audio_file.get("file_id")
            if not isinstance(file_id, str) or not file_id:
                raise ValueError("Áudio sem file_id")

            audio = await telegram.download_audio(
                TelegramAudioFile(
                    file_id=file_id,
                    mime_type=audio_file.get("mime_type"),
                    file_size=file_size if isinstance(file_size, int) else None,
                )
            )
            text = await groq.transcribe(audio)
            source = "audio"

        if not text:
            await telegram.send_message(
                chat_id,
                "🎤 Envie um texto ou um áudio para eu registrar ou consultar seus gastos.",
            )
            return

        from_data = message.get("from")
        if not isinstance(from_data, dict):
            raise ValueError("Update sem usuário")

        telegram_id = from_data.get("id")
        if not isinstance(telegram_id, int) or isinstance(telegram_id, bool):
            raise ValueError("Update sem id do usuário")

        user = await repo.ensure_user(
            telegram_id,
            first_name=from_data.get("first_name"),
            username=from_data.get("username"),
        )
        reply = await handle_financial_message(
            user=user,
            text=text,
            source=source,
            repo=repo,
            groq=groq,
        )
        await telegram.send_message(chat_id, reply)
    except Exception:
        logger.exception("handle_telegram_update falhou")
        try:
            await telegram.send_message(
                chat_id,
                "⚠️ Não consegui processar sua mensagem agora. Tente novamente em instantes.",
            )
        except Exception:
            logger.exception("Falha ao enviar mensagem de erro para o Telegram")

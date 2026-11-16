from __future__ import annotations

import re

import httpx

from .config import Settings
from .models import AudioInput, TelegramAudioFile

MAX_TELEGRAM_AUDIO_BYTES = 20 * 1024 * 1024
TELEGRAM_TIMEOUT_SECONDS = 15.0


class TelegramAudioError(RuntimeError):
    pass


async def download_telegram_audio(
    file: TelegramAudioFile,
    settings: Settings,
) -> AudioInput:
    if file.file_size and file.file_size > MAX_TELEGRAM_AUDIO_BYTES:
        raise TelegramAudioError("Áudio acima do limite de 20 MB do Telegram")

    async with httpx.AsyncClient(timeout=TELEGRAM_TIMEOUT_SECONDS) as client:
        info_response = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile",
            params={"file_id": file.file_id},
        )

        if info_response.status_code >= 400:
            raise TelegramAudioError(
                f"Falha ao obter arquivo do Telegram: {info_response.status_code}"
            )

        try:
            info = info_response.json()
        except ValueError as error:
            raise TelegramAudioError("Telegram retornou JSON inválido") from error

        result = info.get("result") or {}
        file_path = result.get("file_path")

        if not info.get("ok") or not file_path:
            raise TelegramAudioError("Telegram não retornou o caminho do arquivo")

        file_size = result.get("file_size")
        if file_size and file_size > MAX_TELEGRAM_AUDIO_BYTES:
            raise TelegramAudioError("Áudio acima do limite de 20 MB do Telegram")

        file_response = await client.get(
            f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
        )

    if file_response.status_code >= 400:
        raise TelegramAudioError(f"Falha ao baixar áudio do Telegram: {file_response.status_code}")

    extension_match = re.search(r"\.([a-z0-9]+)$", file_path, re.IGNORECASE)
    raw_extension = extension_match.group(1).lower() if extension_match else "ogg"
    extension = "ogg" if raw_extension == "oga" else raw_extension

    mime_type = file.mime_type or "audio/ogg"
    if mime_type == "audio/oga":
        mime_type = "audio/ogg"

    return AudioInput(
        data=file_response.content,
        mime_type=mime_type,
        file_name=f"audio.{extension}",
    )

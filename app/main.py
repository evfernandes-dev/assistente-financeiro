from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import Settings
from .db import FinanceRepository, PostgresRepository
from .groq import GroqClient
from .telegram import TelegramClient, TelegramGateway, handle_telegram_update

SERVICE_NAME = "assistente-financeiro"


def create_app(
    *,
    settings: Settings | None = None,
    repo: FinanceRepository | None = None,
    groq: GroqClient | None = None,
    telegram: TelegramGateway | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    resolved_groq = groq or GroqClient(resolved_settings)
    resolved_telegram = telegram or TelegramClient(resolved_settings)
    owns_repo = repo is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database: FinanceRepository = repo or PostgresRepository(resolved_settings.database_url)
        if owns_repo:
            await database.connect()  # type: ignore[attr-defined]

        app.state.repo = database
        app.state.groq = resolved_groq
        app.state.telegram = resolved_telegram

        try:
            yield
        finally:
            if owns_repo:
                await database.close()  # type: ignore[attr-defined]

    app = FastAPI(title="Assistente Financeiro", lifespan=lifespan)

    @app.get("/health")
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": SERVICE_NAME,
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )

    @app.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> PlainTextResponse:
        received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        expected_secret = resolved_settings.telegram_webhook_secret

        if (
            not expected_secret
            or not received_secret
            or not hmac.compare_digest(received_secret, expected_secret)
        ):
            return PlainTextResponse("unauthorized", status_code=401)

        try:
            update: Any = await request.json()
        except Exception:
            return PlainTextResponse(
                '{"ok":false,"error":"invalid json"}',
                status_code=400,
                media_type="application/json",
            )

        if (
            not isinstance(update, dict)
            or not isinstance(update.get("update_id"), int)
            or isinstance(update.get("update_id"), bool)
        ):
            return PlainTextResponse(
                '{"ok":false,"error":"invalid update"}',
                status_code=400,
                media_type="application/json",
            )

        background_tasks.add_task(
            handle_telegram_update,
            update,
            repo=app.state.repo,
            groq=app.state.groq,
            telegram=app.state.telegram,
        )
        return PlainTextResponse("ok")

    return app


app = create_app()

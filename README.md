# AI Finance Assistant

Telegram bot that records expenses and income from text or voice, answers questions and generates monthly reports. It replies in Brazilian Portuguese.

## Stack

Python 3.11+ · FastAPI · Telegram Bot API · Groq (Qwen + Whisper) · Neon PostgreSQL · pytest

## How it works

Telegram → FastAPI → Whisper transcription → LLM intent extraction → validation → PostgreSQL → reply.

## Run

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill `.env`, apply `database/schema.sql` in Neon, then run:

```powershell
uvicorn app.main:app --reload
```

## Tests

```powershell
pytest
ruff check app tests
```

FastAPI needs a long-running host such as Render, Railway or Fly.io.

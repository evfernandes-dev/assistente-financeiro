# AI Finance Assistant

AI-powered personal finance assistant on Telegram. Users send text or voice messages, and the assistant records expenses and income, answers questions, generates reports and fixes mistakes. The bot replies in Brazilian Portuguese; code and documentation are in English.

> Rewritten from TypeScript/Cloudflare Workers to Python/FastAPI. The previous implementation remains available in the Git history.

## How it works

1. Telegram sends a webhook update to the FastAPI app.
2. The webhook validates the secret token.
3. Voice notes are downloaded and transcribed with Whisper (Groq).
4. An LLM (Qwen via Groq) extracts the intent and fields as strict JSON.
5. The response is validated before any database write.
6. Neon PostgreSQL stores the transaction and an audit entry.
7. The bot replies in Brazilian Portuguese.

```text
Telegram
   |
   v
FastAPI -> Whisper (audio) -> LLM extraction
   -> validation -> Neon PostgreSQL (transactions + audit) -> reply
```

Two AI capabilities are core to the product:

- **Speech-to-text:** Whisper (`whisper-large-v3-turbo` via Groq).
- **Natural-language understanding:** an LLM (`qwen/qwen3.8-27b` via Groq) that maps free-form text to one of seven intents: create expense, create income, query, report, correct, delete or unknown.

The project does not train or fine-tune a model. The engineering work is in prompt design, structured output validation, guardrails and the end-to-end pipeline.

## AI safeguards

- Allowlisted intents and categories.
- Amounts and dates parsed and validated in code.
- Ambiguous or incomplete input asks the user for clarification.
- User messages are treated as data, not instructions (prompt-injection rule).
- Invalid JSON, empty responses, timeouts and API errors fall back to a safe reply.
- Tests mock the AI services, so no real credentials are required.

## Features

- Expenses and income from text or voice
- Queries by period and category
- Monthly reports with totals and category breakdown
- Corrections and soft deletion of the last transaction
- Audit log with before/after states
- Per-user data isolation
- Webhook secret validation
- 62 automated tests

## Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.11+ |
| Web framework | FastAPI + Uvicorn |
| Bot | Telegram Bot API |
| LLM | Groq (`qwen/qwen3.8-27b`) |
| Speech-to-text | Groq Whisper (`whisper-large-v3-turbo`) |
| Database | Neon PostgreSQL |
| DB driver | `asyncpg` |
| Tests | pytest + respx |
| Lint | Ruff |

## Structure

```text
app/
├── main.py           FastAPI entrypoint, health check and webhook authentication
├── telegram.py       Telegram updates, message splitting and replies
├── audio.py          Voice note download and size limits
├── groq.py           Whisper transcription and LLM chat client
├── ai.py             Intent extraction, validation and orchestration
├── db.py             asyncpg queries, audit log and soft delete
├── reports.py        Reply and report formatting
├── config.py         Environment settings
├── models.py         Internal dataclasses
└── categories.py     Default categories
database/schema.sql   PostgreSQL schema
prompts/              Agent and extraction prompts
dashboard/            Web dashboard plan (not built yet)
tests/                Unit and webhook tests with fakes
```

## Running locally

Requirements: Python 3.11+, a Telegram bot, a Neon database and a Groq API key.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill `.env`, then apply `database/schema.sql` in the Neon SQL Editor and run:

```powershell
pytest
uvicorn app.main:app --reload
```

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_WEBHOOK_SECRET` | Secret token sent by Telegram |
| `DATABASE_URL` | Neon pooled PostgreSQL connection string |
| `GROQ_API_KEY` | Groq API key |
| `GROQ_MODEL` | Chat model (`qwen/qwen3.8-27b`) |
| `GROQ_TRANSCRIPTION_MODEL` | Transcription model (`whisper-large-v3-turbo`) |

Never commit `.env`, `.env.*` or real credentials.

## Tests

```powershell
pytest
ruff check app tests
```

The tests cover parsing/validation, agent flows, report formatting, webhook authentication, Telegram text/audio handling, audio limits and Groq HTTP clients. External services are mocked with `respx` and in-memory fakes. The PostgreSQL queries are not covered by an automated integration test yet; validate them against a staging Neon database before deploying.

## Deployment

FastAPI needs a long-running process, so the app is no longer deployable on Cloudflare Workers. Use a host such as Render, Railway or Fly.io, keep Neon as the database and configure the environment variables above.

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

After deploying, register the webhook:

```powershell
curl "https://api.telegram.org/bot<TOKEN>/setWebhook" `
  -d "url=https://<YOUR-DOMAIN>/telegram/webhook" `
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

## Production and security

- Webhook requests require the `X-Telegram-Bot-Api-Secret-Token` header.
- Secret comparison uses constant-time comparison.
- Every query filters by `user_id`.
- Corrections and deletions are recorded in `audit_log`; deletions are logical (`status = 'deleted'`).
- Audio size limits are enforced before download and transcription.
- `.env` is ignored by Git; production secrets belong in the hosting provider.

## Limitations and roadmap

- No `update_id` deduplication or rate limiting yet.
- No formal evaluation dataset for the LLM yet.
- The web dashboard is not implemented.
- The assistant does not give investment or credit advice.

Next: build the dashboard, add an evaluation dataset, add deduplication/rate limiting and richer conversational reports.

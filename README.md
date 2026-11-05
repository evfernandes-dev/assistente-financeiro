# AI Finance Assistant

AI-powered personal finance assistant on Telegram. Users send text or voice messages, and the assistant records expenses and income, answers questions, generates reports and fixes mistakes.

- Live bot: [@economyze_bot](https://t.me/economyze_bot)
- Health check: `https://assistente-financeiro.assistente-financeiro-worker.workers.dev/health`
- The bot replies in Brazilian Portuguese; code and documentation are in English.

## How it works

1. Telegram sends a webhook update to a Cloudflare Worker.
2. The Worker validates the secret token.
3. Voice notes are transcribed with Whisper (Groq).
4. An LLM (Qwen via Groq) extracts the intent and fields as strict JSON.
5. The response is validated before any database write.
6. Neon PostgreSQL stores the transaction and an audit entry.
7. The bot replies in Brazilian Portuguese.

```text
Telegram
   |
   v
Cloudflare Worker -> Whisper (audio) -> LLM extraction
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
- 44 automated tests

## Stack

| Layer | Technology |
| --- | --- |
| Language | TypeScript |
| Runtime | Cloudflare Workers |
| Bot | Telegram Bot API |
| LLM | Groq (`qwen/qwen3.8-27b`) |
| Speech-to-text | Groq Whisper (`whisper-large-v3-turbo`) |
| Database | Neon PostgreSQL |
| DB driver | `@neondatabase/serverless` |
| Deploy | Wrangler 4 |
| Tests | Vitest + PGlite |

## Structure

```text
worker/src/
├── index.ts            HTTP entrypoint and webhook authentication
├── telegram.ts         Telegram updates and replies
├── audio.ts            Voice note download
├── transcription.ts    Whisper transcription
├── ai.ts               LLM intent extraction and orchestration
├── expenses.ts         Neon queries, audit and soft delete
└── reports.ts          Reply and report formatting
database/schema.sql     PostgreSQL schema
prompts/                Agent and extraction prompts
dashboard/              Web dashboard plan (not built yet)
```

## Running locally

Requirements: Node.js 20+, npm, a Telegram bot, a Neon database and a Groq API key.

```powershell
cd worker
npm install
npm test
npm run dev
```

Create `worker/.dev.vars` and apply `database/schema.sql` in the Neon SQL Editor.

| Variable | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_WEBHOOK_SECRET` | Secret token sent by Telegram |
| `DATABASE_URL` | Neon pooled PostgreSQL connection string |
| `GROQ_API_KEY` | Groq API key |
| `GROQ_MODEL` | Chat model (`qwen/qwen3.8-27b`) |
| `GROQ_TRANSCRIPTION_MODEL` | Transcription model (`whisper-large-v3-turbo`) |

Never commit `.dev.vars`, `.env` or real credentials.

## Tests

```powershell
cd worker
npm test
npm run typecheck
npx wrangler deploy --dry-run
```

PGlite runs the real PostgreSQL schema, including the `updated_at` trigger and audit tables. External services are mocked.

## Production and security

The Worker is deployed on Cloudflare and the Telegram webhook is registered at `/telegram/webhook`. Secrets are stored with `wrangler secret put`.

- Webhook requests require the `X-Telegram-Bot-Api-Secret-Token` header.
- Secret comparison uses SHA-256 digests.
- Every query filters by `user_id`.
- Corrections and deletions are recorded in `audit_log`; deletions are logical (`status = 'deleted'`).
- Audio size limits are enforced before download and transcription.

## Limitations and roadmap

- No `update_id` deduplication or rate limiting yet.
- No formal evaluation dataset for the LLM yet.
- The web dashboard is not implemented.
- The assistant does not give investment or credit advice.

Next: build the dashboard, add an evaluation dataset, add deduplication/rate limiting and richer conversational reports.

# AI Finance Assistant

An AI-powered personal finance assistant on Telegram. Users send a text or voice message, and the assistant understands the request, records transactions, answers questions, fixes mistakes, and generates reports.

- Live bot: [@economyze_bot](https://t.me/economyze_bot)
- API health: `https://assistente-financeiro.assistente-financeiro-worker.workers.dev/health`
- The bot replies in Brazilian Portuguese; code and documentation are in English.

## What makes this an AI project

Two AI capabilities are core to the product:

1. **Speech-to-text**: Whisper (`whisper-large-v3-turbo` via Groq) transcribes Telegram voice notes.
2. **Natural-language understanding**: an LLM (`qwen/qwen3.8-27b` via Groq) converts free-form text into strict JSON.

The model extracts one of seven intents: create expense, create income, query, report, correct, delete, or unknown. It also extracts amount, description, category, and date.

This project does not train or fine-tune a model. The engineering work is in prompt design, structured output validation, guardrails, and the end-to-end pipeline around the LLM.

## How it works

1. Telegram sends a webhook update to a Cloudflare Worker.
2. The Worker validates the secret token.
3. Voice notes are downloaded from Telegram and transcribed with Whisper.
4. The LLM extracts the intent and fields as JSON.
5. The response is validated before any database write: allowed intents and categories, valid amounts and dates, and safe fallbacks.
6. A single SQL operation writes or reads Neon PostgreSQL and records an audit entry.
7. The bot replies in Brazilian Portuguese.

```text
Telegram
   |
   v
Cloudflare Worker
   |-- text ------------------------------+
   |                                      |
   +-- audio -> Whisper (Groq) -----------+
                                          |
                                          v
                              LLM intent extraction (Groq)
                                          |
                                          v
                              validation and guardrails
                                          |
                                          v
                     Neon PostgreSQL (transactions + audit)
                                          |
                                          v
                              Telegram reply
```

## AI safeguards

- The LLM must return JSON with an allowlisted intent.
- Categories are restricted to the application's category list.
- Amounts and dates are parsed and validated in code.
- Ambiguous or incomplete input asks the user for clarification.
- The user message is treated as data, not as instructions (prompt-injection rule).
- Invalid JSON, empty responses, timeouts, and API errors fall back to a safe reply.
- Tests mock the AI services, so the suite does not depend on real credentials.

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

## Project structure

```text
.
├── worker/
│   ├── src/
│   │   ├── index.ts            HTTP entrypoint and webhook authentication
│   │   ├── telegram.ts         Telegram updates and replies
│   │   ├── audio.ts            Voice note download
│   │   ├── transcription.ts    Whisper transcription
│   │   ├── ai.ts               LLM intent extraction and orchestration
│   │   ├── expenses.ts         Neon queries, audit and soft delete
│   │   └── reports.ts          Reply and report formatting
│   ├── tests/                  Vitest suite with PGlite
│   ├── vitest.config.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── wrangler.toml
├── database/
│   ├── schema.sql
│   └── migrations/001_init.sql
├── prompts/
│   ├── financial-agent.md
│   ├── expense-extraction.md
│   └── response.md
├── dashboard/                  Implementation plan (not built yet)
├── tests/README.md
├── .env.example
└── README.md
```

## Running locally

Requirements: Node.js 20+, npm, a Telegram bot, a Neon database, and a Groq API key.

```powershell
cd worker
npm install
npm test
npm run dev
```

Create `worker/.dev.vars` with the variable names below, then apply `database/schema.sql` in the Neon SQL Editor.

## Environment variables

| Variable | Type | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | secret | Telegram bot token |
| `TELEGRAM_WEBHOOK_SECRET` | secret | Secret token sent by Telegram |
| `DATABASE_URL` | secret | Neon pooled PostgreSQL connection string |
| `GROQ_API_KEY` | secret | Groq API key |
| `GROQ_MODEL` | var | Chat model (`qwen/qwen3.8-27b`) |
| `GROQ_TRANSCRIPTION_MODEL` | var | Transcription model (`whisper-large-v3-turbo`) |

Never commit `.dev.vars`, `.env`, or real credentials.

## Tests

```powershell
cd worker
npm test
npm run typecheck
npx wrangler deploy --dry-run
```

The suite covers:

- expense and income creation
- text intent extraction and JSON validation
- audio download and transcription
- queries, reports, corrections, and deletion
- per-user isolation and audit events
- webhook authentication and invalid updates

PGlite runs the real PostgreSQL schema, including the `updated_at` trigger and audit tables. External services are mocked; no real credentials are required.

## Production

The Worker is deployed on Cloudflare and the Telegram webhook is registered. The production URL is shown at the top of this README.

Secrets are stored in Cloudflare with `wrangler secret put` and locally in `worker/.dev.vars`, which is ignored by Git.

To register the webhook, use the published Worker URL with `/telegram/webhook` and the same value as `TELEGRAM_WEBHOOK_SECRET`.

## Security

- Webhook requests require the `X-Telegram-Bot-Api-Secret-Token` header.
- The secret comparison uses SHA-256 digests.
- Every query filters by `user_id`.
- Corrections and deletions are recorded in `audit_log`.
- Deletions are logical (`status = 'deleted'`), not physical.
- Audio size limits are enforced before download and transcription.
- API errors are logged without exposing user data or credentials.

## Limitations

- No persistent `update_id` deduplication or rate limiting yet.
- No formal evaluation dataset for the LLM yet.
- The web dashboard is not implemented.
- The assistant does not give investment or credit advice.

## Roadmap

- Build the dashboard described in `dashboard/README.md`.
- Add an AI evaluation dataset and track intent accuracy over prompt changes.
- Add update deduplication and per-user rate limiting.
- Add more conversational context and richer reports.

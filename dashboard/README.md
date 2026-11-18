# Web Dashboard (planned)

Dashboard for viewing transactions and reports from the finance assistant. It is not implemented yet; this document describes the proposed design.

## Current state

- Only this documentation exists.
- The FastAPI app exposes only `/health` and `/telegram/webhook`.
- Query helpers in `app/db.py` can be reused by dashboard routes.

## Proposed architecture

- Static front end (HTML/JS or React, decision pending) hosted separately.
- Dashboard API in the same FastAPI app under `/api/dashboard/*`.
- Session cookie (`HttpOnly`, `Secure`, `SameSite=Strict`) signed with HMAC.
- No tokens in `localStorage` and no broad CORS.
- Data always filtered by the authenticated user.

## Planned routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/auth/login` | POST | Create the signed session |
| `/api/auth/logout` | POST | End the session |
| `/api/dashboard/summary?from=&to=` | GET | Totals, balance and expenses by category |
| `/api/dashboard/transactions?from=&to=&category=` | GET | Paginated list |
| `/api/dashboard/transactions` | POST | Create a manual transaction |
| `/api/dashboard/transactions/{id}` | PATCH | Edit a transaction |
| `/api/dashboard/transactions/{id}` | DELETE | Soft delete |

All routes require a valid session and return only the authenticated user's data.

## Authentication

1. Add `DASHBOARD_PASSWORD_HASH` and `DASHBOARD_SESSION_SECRET` as environment variables.
2. `POST /api/auth/login` compares the password with the hash and creates a signed cookie.
3. The cookie contains only a session identifier and an expiration time.
4. Map the session to an existing `user_id` (the bot owner) or add a `dashboard_sessions` table in a future migration.
5. Add attempt limits and session invalidation on logout.

## Implementation steps

1. Static layout with mock data and loading/error states.
2. Read routes in FastAPI and session authentication.
3. Period/category filters and an expense chart.
4. Editing and deletion with confirmation, reusing the audit rules.
5. Route tests with pytest and front-end smoke tests.
6. Deploy the front end separately from the FastAPI host.

## Open decisions

- Chart library: custom SVG, Chart.js or Recharts.
- Front end: plain HTML/JS or React/Vite.
- Session model: dedicated table or stateless signed token.
- Single user (bot owner) or multiple users.

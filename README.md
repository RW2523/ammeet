# AmMeeting

> The AI meeting assistant that knows what to ask, collects the answers, and keeps work moving.

## What Is AmMeeting?

AmMeeting is a context-aware meeting intelligence platform. It:

- Understands previous meeting transcripts, Jira tickets, and project context
- Generates smart, categorized questions before a meeting
- Lets you edit, approve, and flag questions (proxy-allowed vs human-only)
- Shadows meetings and guides you in real time
- **Transparently joins as an AI proxy** — introduces itself, asks approved questions, acts on your knowledge, escalates restricted topics to you, never makes decisions
- Captures answers, decisions, action items, risks
- Generates structured post-meeting reports with Slack/email/Jira drafts
- Maintains a searchable RAG knowledge base across all your meetings

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind, shadcn/ui, TanStack Query |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.0 async, asyncpg |
| Database | PostgreSQL 16 + pgvector |
| Cache/Pubsub | Redis 7 |
| AI | OpenAI (real) or Anthropic via env key; Whisper/AssemblyAI STT; OpenAI TTS; Recall.ai bot |
| Integrations | Google Calendar / Slack / Jira via real OAuth (mock fallback without credentials) |
| Billing | Stripe subscriptions (Free/Pro/Team) with per-plan monthly usage limits; mock mode without keys |
| Auth | JWT (access + refresh), TOTP MFA, email verification, password reset, rate limiting + lockout |

---

## Quick Start (Local)

### Prerequisites
- Docker + Docker Compose
- Node.js 20+
- Python 3.12+

### 1. Clone and configure

```bash
cd ammeet
cp .env.example .env
# Edit .env — set your OPENAI_API_KEY (or ANTHROPIC_API_KEY)
```

### 2. Start infrastructure

```bash
docker compose up db redis -d
# Wait for postgres to be healthy: docker compose ps
```

### 3. Backend

```bash
cd backend
pip install -r requirements.txt
# Run migrations
alembic upgrade head
# Seed demo data (creates workspace, people, meeting, questions)
python seed.py
# Start API server
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### 5. Demo login

```
Email:    richard@ammeet.io
Password: ammeet2026
```

---

## Run With Docker Compose (full stack)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

---

## Demo Flow

1. **Login** as `richard@ammeet.io`
2. Open the **Client Dashboard Project** workspace (seeded)
3. Open the **Client Dashboard Follow-up (June 7)** meeting
4. **Prep Brief tab** — view previous summary, Jira tickets, open action items, suggested agenda
5. **Questions tab** — see 8 smart questions (7 proxy-allowed, 1 human-only)
6. **Proxy Room tab** — click **Start Proxy Session** to run a simulated proxy:
   - AmMeeting introduces itself with full disclosure
   - Asks approved questions one by one
   - Generates realistic simulated answers using your knowledge base
   - Escalates budget/legal/HR questions immediately
   - Asks KB-grounded clarifying questions for incomplete answers
   - Streams all events live
7. **Report tab** — view the auto-generated structured report, email draft, Slack draft

---

## API Reference

Full interactive docs at `/docs` (Swagger) or `/redoc`.

### Key endpoints

| Endpoint | Description |
|---|---|
| `POST /api/auth/register` | Register user |
| `POST /api/auth/login` | Login (supports MFA) |
| `GET /api/workspaces` | List workspaces |
| `POST /api/workspaces/{id}/meetings` | Create meeting |
| `POST /api/workspaces/{id}/meetings/{mid}/upload-context` | Upload transcript |
| `POST /api/workspaces/{id}/meetings/{mid}/generate-questions` | AI question generation |
| `POST /api/workspaces/{id}/meetings/{mid}/proxy/start` | Start proxy SSE stream |
| `POST /api/workspaces/{id}/meetings/{mid}/reports/generate` | Generate report |
| `POST /api/workspaces/{id}/knowledge/query` | Ask knowledge base |

---

## Billing & Plans

| Plan | Price | Proxy sessions | AI question batches | Reports |
|---|---|---|---|---|
| Free | $0 | 3/mo | 10/mo | 10/mo |
| Pro | $29/mo | 50/mo | 200/mo | 200/mo |
| Team | $99/mo | Unlimited | Unlimited | Unlimited |

- With `STRIPE_SECRET_KEY` set: real Stripe Checkout, customer portal, and webhook-driven plan sync (`/api/billing/webhook`)
- Without Stripe keys: mock billing — plan changes apply instantly so the full flow is demoable
- Limits enforced server-side with monthly usage counters (`usage_records` table); 402 returned when exceeded

## Integrations (real OAuth)

Set client credentials in `.env` to switch a provider from mock fixtures to real OAuth:

| Provider | Env vars | What it does |
|---|---|---|
| Google Calendar | `GOOGLE_CLIENT_ID/SECRET` | Imports upcoming events + attendees into prep briefs |
| Slack | `SLACK_CLIENT_ID/SECRET` | Sends report drafts to channels (after your review) |
| Jira | `JIRA_CLIENT_ID/SECRET` | Pulls open tickets/blockers into meeting context |

Tokens are encrypted at rest (Fernet) and auto-refreshed. Callback URL pattern:
`{WEBHOOK_BASE_URL}/api/integrations/oauth/{provider}/callback`

## Security & Privacy

- JWT auth, RBAC (owner/admin/manager/member/viewer/guest) per workspace
- TOTP MFA for admin-role users
- Email verification + password reset flows (console email in dev, SMTP in production)
- Password policy (length + complexity), per-IP rate limiting on auth endpoints, account lockout after repeated failures
- Integration OAuth tokens encrypted at rest with Fernet (`TOKEN_ENCRYPTION_KEY`)
- Tenant isolation: every query scoped by workspace; RAG cannot cross workspaces
- Audit log on: upload, recording start, proxy enable, question approval, AI questions asked, integration changes, transcript views, deletes, exports
- Capture levels 1-2 only (summary / transcript+summary), no video storage
- Retention policies configurable per workspace
- GDPR/CCPA: export + delete endpoints at `/api/admin/workspaces/{id}/export` and `/api/admin/workspaces/{id}/data`
- Prompt injection defense: meeting content treated as untrusted; system rules separated from retrieved content; no external write without review

---

## Proxy Attender — How It Works

The Transparent Proxy Attender is the flagship feature. It acts on your knowledge **as if you were there**:

1. **Mandatory disclosure**: Introduces itself before any question is asked. Logged to audit trail.
2. **Knowledge-grounded**: Uses pgvector RAG over all your uploaded transcripts and context to answer with full project context.
3. **Escalation classifier**: Intercepts budget, legal, contract, HR, final commitment topics with a dual regex + LLM classifier. Marks escalated, never proceeds.
4. **Clarifying questions**: When an answer is incomplete, asks a follow-up grounded in your KB — not a generic question but one anchored to your actual project context.
5. **Never commits**: All external actions (Slack send, Jira update, email) require explicit user review and action.

---

## Running Tests

```bash
cd backend
# Make sure test DB exists: createdb ammeet_test
pytest -v
```

Tests cover: auth flows, RBAC/tenant isolation, question generation, escalation classifier, retention policy, full meeting flow.

---

## Project Structure

```
ammeet/
  docker-compose.yml
  .env.example
  backend/
    app/
      core/        # config, database, redis, security, deps
      models/      # SQLAlchemy models (user, meeting, knowledge)
      schemas/     # Pydantic v2 schemas
      routers/     # FastAPI routers (auth, workspaces, meetings, questions, reports, knowledge, integrations, admin)
      services/
        llm/       # LLM provider abstraction (real OpenAI/Anthropic)
        stt/       # STT stub
        integrations/  # Jira/Calendar/Slack stubs
        extraction/    # Text extraction + chunking
        question_generator.py
        knowledge_rag.py
        escalation.py
        proxy_engine.py
        report_generator.py
      alembic/     # Database migrations
      tests/
    seed.py
    requirements.txt
  frontend/
    app/
      auth/        # login, register
      dashboard/
      workspaces/  # workspace list, detail, people, meetings, knowledge, integrations
    components/
      sidebar.tsx
      ui/          # shadcn components
    lib/
      api.ts       # axios client
      api-client.ts # typed API methods
      types.ts     # TypeScript types
      store.ts     # Zustand state
```

---

## Phase Roadmap

| Phase | Status | Scope |
|---|---|---|
| 1 - Prep & Shadow | ✅ Built | Upload, generate questions, shadow mode, reports |
| 2 - Live Navigator | ✅ Built | SSE live board, answer tracking, escalation |
| 3 - Proxy Attender | ✅ Built | Disclosure, KB-grounded proxy, escalation, report |
| 4 - Real Integrations | ✅ Built | Google Calendar/Slack/Jira OAuth, real STT/TTS, Recall.ai bot |
| 5 - Go-to-market | ✅ Built | Landing page, onboarding, Stripe billing, plan limits, email verification, CI |
| 6 - Marketplace | Planned | Google Workspace, Zoom App, Teams App |

# PMWizard Local Demo & First-Run Onboarding V0 — PR #25

This operator-only workflow creates a **synthetic demo workspace** that can be
used to explore the real PMWizard UI and API. It does **not** provision real
connectors, customer accounts, or a production tenant.

> **Docker-first option (PR #26):** For a complete local stack without
> installing Python/Node dependencies on the host, see
> [Containerized Local Demo](CONTAINERIZED_LOCAL_DEMO.md). The manual
> workflow below remains available.

## Prerequisites

- Python 3.11 or 3.12, Docker with Compose, Node.js 22, npm
- Local PostgreSQL 16 (see `docker-compose.yml`) or a local SQLite database
- A terminal with a Bash-compatible shell for the commands below
- A clean development database, with Alembic migrations applied

## Run locally

From the repository root:

```bash
cp .env.example .env
set -a
source .env
set +a

docker compose up -d
pip install -e ".[dev]"
alembic upgrade head

export PMWIZARD_ENV=development
export PMWIZARD_ENABLE_LOCAL_DEMO=true
read -rsp "Choose a demo password (12+ chars): " PMWIZARD_DEMO_PASSWORD
echo
export PMWIZARD_DEMO_PASSWORD

python -m pmwizard.demo.seed

# This is an independent API-signing secret, NOT the login password.
export PMWIZARD_AUTH_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn pmwizard.api.app:create_default_app --factory --reload
```

In a second terminal:

```bash
cd web
cp .env.local.example .env.local
npm install --no-audit --no-fund
npm run dev
```

Open `http://localhost:3000` and sign in using:

- **Workspace ID:** `269ba0ba-35e4-4e86-bd2e-7d43f09d2550`
- **Email:** `demo@example.com`
- **Password:** the password you typed at the prompt

The CLI prints the workspace, project ID, and whether rows were newly created
or preserved. It intentionally never echoes the password.

The API signing secret must remain stable between API restarts if you want
existing browser sessions to remain valid. Set it in a local secrets manager or
a safe environment configuration for longer-running development.

## Demo data

The fictional **Atlas Delivery — Synthetic Demo** project contains:

- A project manager user with only `project:read` and `project:review` rights
- Three Action Items: blocked, in progress, completed
- One Risk, one Issue, one Dependency and a pending Decision
- One synthetic meeting Evidence record with `project:read` scope
- One pending AI-style suggestion backed by the synthetic Evidence (for
  human review in Project Inbox)
- One activity Event (for Activity Timeline)
- A schedule window relative to the first seed time (for Project Health)

Expected workflow: sign in, select Atlas, open Project Inbox to inspect the
suggestion and its evidence, review only if desired, then explore Memory,
Health, Attention Center and Activity Timeline. Export is available to the demo
reviewer because both `project:read` and `project:review` are present.

## Safety and repeatability

The CLI **refuses to run** unless all conditions are met:

1. `PMWIZARD_ENV=development`
2. `PMWIZARD_ENABLE_LOCAL_DEMO=true`
3. The database is SQLite or PostgreSQL at `localhost`, `127.0.0.1`, or `::1`
4. `PMWIZARD_DEMO_PASSWORD` is set and meets the 12-character minimum

The service independently enforces the same guard when called by Python code.
There is no public signup route and no automatic seeding at API startup.

- Seed IDs are deterministic within the demo tenant and entries are
  **created if absent**, never silently overwritten. Repeat runs preserve
  existing review decisions, task statuses and passwords.
- A second run must use the original demo password. To change it, use an
  explicit password-management process, not the seeder.
- A transaction wraps all inserts. Identity collisions abort and roll back.
- The demo never asks for or initializes Microsoft Graph tokens, SMTP
  credentials, Teams webhooks or client records.
- The local development database is still a real database. **Never point the
  CLI at a production database, and avoid running it on a database with real
  client data**, including a shared local instance.
- This seed is not a migration, a load test, a privileged admin route or a
  substitute for production identity management and deployment hardening.

## Testing

```bash
pytest -q tests/test_local_demo.py
pytest -q
```

The new tests cover login and real API usage, seed idempotency, preservation
of reviewed values, cross-tenant isolation, local-only guard failures, password
validation, and atomic rollback on identity conflicts.

## Limitations

This workflow runs services separately; it is not a turnkey production
deployment. Web/API sessions require consistent auth configuration and
real integrations need separately authorized setup. Multi-user provisioning,
production signup, password recovery, user invitations, deployment health
checks, containerized app services and production secrets management are not
provided by this V0.

# PMWizard

**The intelligence layer for Project & Program Management.**

PMWizard is an open-source initiative exploring how AI can connect project information, understand context, identify delivery risks, explain project health, and support better Project & Program Management decisions.

The project is designed to evolve from structured Project Health AI into a broader Project Intelligence platform combining analytics, machine learning, retrieval-augmented generation, knowledge graphs, and specialized AI agents.

## Current focus

The first MVP is centered on **Project Memory + Action & Decision Intelligence**:

> Can PMWizard connect meetings, email, documents, and existing project records to keep Action Items, Decisions, RAID, and supporting evidence current with less manual effort?

Initial work will focus on:

- A reusable, tool-independent canonical project data model
- Meeting and email evidence ingestion
- Action Item progress detection
- Decision and RAID identification
- Entity resolution and duplicate prevention
- Human-reviewed AI suggestions through a Project Inbox
- Secure adapters for existing project ecosystems
- Foundations for later Project Health and predictive intelligence

## Foundation documents

- [`docs/VISION.md`](docs/VISION.md) — long-term product vision and guiding principles
- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — canonical entities, relationships, evidence, events, health, and security foundations
- [`docs/HUMAN_IN_THE_LOOP.md`](docs/HUMAN_IN_THE_LOOP.md) — AI suggestion boundaries, human accountability, source authority, and review governance
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — V1 system architecture, connectors, Project Memory, intelligence engine, security, and technology choices
- [`docs/ENTITY_RESOLUTION.md`](docs/ENTITY_RESOLUTION.md) — explainable matching of new evidence to existing project entities
- [`docs/PROGRESS_INTELLIGENCE.md`](docs/PROGRESS_INTELLIGENCE.md) — evidence-backed Action Item progress classification and human-reviewed updates
- [`docs/INGESTION.md`](docs/INGESTION.md) — deterministic source normalization, deduplication, provenance, and Evidence persistence
- [`docs/CONNECTORS.md`](docs/CONNECTORS.md) — common connector contract, incremental cursors, checkpoints, run results, and safe retries
- [`docs/MICROSOFT_GRAPH_MAIL.md`](docs/MICROSOFT_GRAPH_MAIL.md) — read-only Outlook mail delta sync through Microsoft Graph
- [`docs/SHAREPOINT_DOCUMENTS.md`](docs/SHAREPOINT_DOCUMENTS.md) — versioned SharePoint document-library ingestion and deterministic text extraction
- [`docs/PROJECT_INBOX_API.md`](docs/PROJECT_INBOX_API.md) — permission-aware human review API for AI suggestions
- [`docs/PROJECT_INBOX_WEB.md`](docs/PROJECT_INBOX_WEB.md) — responsive Next.js human-review interface and BFF security boundary
- [`docs/AUTH_PROJECT_SELECTION.md`](docs/AUTH_PROJECT_SELECTION.md) — local authentication, signed sessions, and per-project memberships
- [`docs/PROJECT_MEMORY_WORKSPACE.md`](docs/PROJECT_MEMORY_WORKSPACE.md) — read-only governed Action Items, RAID, Decisions, and project state
- [`docs/SOURCES_WORKSPACE.md`](docs/SOURCES_WORKSPACE.md) — durable source health, checkpoints, sync telemetry, skips, and errors
- [`docs/PROJECT_HEALTH.md`](docs/PROJECT_HEALTH.md) — deterministic, explainable project health scoring and assessment coverage
- [`docs/HEALTH_HISTORY_TRENDS.md`](docs/HEALTH_HISTORY_TRENDS.md) — persisted health snapshots, trend direction, factor deltas, and driver changes
- [`docs/PROGRAM_PORTFOLIO_INTELLIGENCE.md`](docs/PROGRAM_PORTFOLIO_INTELLIGENCE.md) — authorized Program/Portfolio rollups, attention ranking, and cross-project signals
- [`docs/EXECUTIVE_DASHBOARD.md`](docs/EXECUTIVE_DASHBOARD.md) — authenticated executive landing view for Health, Inbox, RAID, Decisions, Sources, and cross-project attention
- [`docs/AI_STATUS_REPORTS.md`](docs/AI_STATUS_REPORTS.md) — grounded structured AI drafting with fact citations, validation, and provider abstraction
- [`docs/AUTOMATION_SCHEDULER.md`](docs/AUTOMATION_SCHEDULER.md) — durable interval scheduling, leases, worker execution, run history, and automated Health snapshots
- [`docs/SECURE_SOURCE_RUNTIME.md`](docs/SECURE_SOURCE_RUNTIME.md) — opaque credential references, runtime secret resolution, and scheduled Outlook/SharePoint delta sync
- [`docs/SOURCE_CONNECTION_ADMIN.md`](docs/SOURCE_CONNECTION_ADMIN.md) — governed creation/editing, worker-executed connection tests, and safe checkpoint reset
- [`docs/ATTENTION_CENTER.md`](docs/ATTENTION_CENTER.md) — deterministic project attention signals with per-user seen, acknowledge, and snooze receipts
- [`docs/NOTIFICATION_DELIVERY.md`](docs/NOTIFICATION_DELIVERY.md) — secure Email/Teams delivery, user preferences, deduplication, and sanitized history

## Project status

PMWizard now includes governed Project Memory, deterministic Health, portfolio intelligence, human-reviewed AI suggestions, an Attention Center, Email/Teams notification delivery, an auditable Activity Timeline, and redacted CSV/JSON activity exports. PR #25 adds an explicitly gated **synthetic local demo** for reproducible first-run testing without real client data. These features are MVP modules, not a production-ready hosted service.

## Create your first project (PR #27)

Once you have a PMWizard login, select **+ New project** from the project
picker or the authenticated workspace. Enter its name and optionally its
objective, methodology and schedule. The project is created within your
authenticated tenant, you receive read/human-review access, and PMWizard
records the creation in its audit timeline. No synthetic project seed is needed.
See [`docs/PROJECT_ONBOARDING.md`](docs/PROJECT_ONBOARDING.md) for the API,
permissions, limits, and remaining multi-user onboarding work.

## Containerized local demo (PR #26)

To launch an isolated **synthetic PMWizard demo** with PostgreSQL, migrations,
project data, API and web using Docker Compose:

```bash
python scripts/init_demo_env.py
docker compose --env-file .env.demo -f compose.demo.yml up --build -d --wait
python scripts/smoke_demo_stack.py
```

Open **http://127.0.0.1:3000**. See
[`docs/CONTAINERIZED_LOCAL_DEMO.md`](docs/CONTAINERIZED_LOCAL_DEMO.md)
for the demo credentials, safe shutdown commands and security restrictions.
This is for **localhost development only**, not production hosting.

## Local demo and first-run walkthrough

Start with [`docs/LOCAL_DEMO_ONBOARDING.md`](docs/LOCAL_DEMO_ONBOARDING.md) for the complete **local-only** path: database migrations, a synthetic demo user and project, server startup, frontend startup, and a test login. No real customer content or third-party credentials are needed. Never seed a production or shared client database.

## Local development

```bash
cp .env.example .env
docker compose up -d
pip install -e ".[dev]"
alembic upgrade head
pytest -q

# API (requires PMWIZARD_DATABASE_URL + PMWIZARD_AUTH_SECRET)
uvicorn pmwizard.api.app:create_default_app --factory --reload

# Automation worker
python -m pmwizard.automation.worker
```

The test suite uses SQLite for fast domain/persistence tests, while CI also validates the Alembic migration against PostgreSQL 16.

**Note:** Shell commands above require `PMWIZARD_DATABASE_URL` and `PMWIZARD_AUTH_SECRET` to be exported as environment variables; copying an `.env` file alone does not load it into the current shell. The local demo walkthrough shows the full procedure.

## Data and privacy

PMWizard will use synthetic, public, explicitly authorized, or properly anonymized data for development and demonstrations. Confidential client information, proprietary corporate data, credentials, and personal information should never be committed to this repository.

## License

See [`LICENSE`](LICENSE).

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

## Project status

PMWizard now has **Project Memory V0** and is implementing **Entity Resolution V0**: explainable, tenant-scoped matching of new Evidence to existing open Action Items before semantic/LLM-assisted resolution is introduced.

## Local development

```bash
cp .env.example .env
docker compose up -d
pip install -e ".[dev]"
alembic upgrade head
pytest -q
```

The test suite uses SQLite for fast domain/persistence tests, while CI also validates the Alembic migration against PostgreSQL 16.

## Data and privacy

PMWizard will use synthetic, public, explicitly authorized, or properly anonymized data for development and demonstrations. Confidential client information, proprietary corporate data, credentials, and personal information should never be committed to this repository.

## License

See [`LICENSE`](LICENSE).

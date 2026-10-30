# Containerized Local Demo Stack V0 — PR #26

Run PMWizard's **synthetic** project workspace, API and web app together using
Docker Compose. This is intentionally a **local developer demo**, not a
production deployment or public SaaS environment.

PR #25's deterministic, idempotent seeder is reused unchanged. The Compose
file is separate from the legacy `docker-compose.yml` (database-only).

## Prerequisites

- Docker Engine + **Docker Compose v2** installed and running
- Python 3.11+ for a one-time local credential generator and smoke script
- Ports **3000** and **8000** available on the local machine

No PostgreSQL, Python packages, Node.js packages or external connector
credentials need to be installed on the host.

## Quick start

From the repository root:

```bash
# One-time: creates .env.demo with cryptographically random demo credentials
python scripts/init_demo_env.py

# Start isolated database, schema migrations, demo seed, FastAPI and Next.js
docker compose --env-file .env.demo -f compose.demo.yml up --build -d --wait

# Confirm login, project data, API, UI, Inbox and Activity endpoints all work
python scripts/smoke_demo_stack.py
```

Then visit **http://127.0.0.1:3000/**. Sign in using:

- **Workspace/tenant UUID:** `269ba0ba-35e4-4e86-bd2e-7d43f09d2550`
- **Email:** `demo@example.com`
- **Password:** shown once by `init_demo_env.py`; or read
  `PMWIZARD_DEMO_PASSWORD` from your local `.env.demo`.

The synthetic project **Atlas Delivery** contains Action Items, a Risk, an
Issue, a Dependency, a pending Decision, restricted synthetic Evidence, a
reviewable suggestion and an Event. No real user or client content is loaded.

## Services and ordering

| Service | Purpose | Access |
| --- | --- | --- |
| `demo-db` | Dedicated PostgreSQL 16 database | Internal only; no host port |
| `demo-migrate` | One-off `alembic upgrade head` | Starts after DB is healthy |
| `demo-seed` | One-off PR #25 synthetic seed | Starts after migrations |
| `demo-api` | Non-root FastAPI application | `127.0.0.1:8000` only |
| `demo-web` | Non-root Next.js **development** server | `127.0.0.1:3000` only |

The API waits for the seed to finish successfully; the web server waits for
API readiness. Seed and migrations are separate one-off services so an
incomplete database does not silently present a seemingly functional UI.

**Why the seed uses `network_mode: service:demo-db`:** The previous
seeder prohibits remote database hosts. The one-off seed temporarily shares
the *dedicated, unexposed database container network namespace* and connects
to its PostgreSQL on `127.0.0.1:5432`. This preserves the loopback-only guard
without weakening the PR #25 service's rules for regular Python callers.
The API and migrations instead use the Compose-internal hostname
`demo-db`. Only the explicit demo Compose file opts in to seeding.

## Health and verification

- `GET http://127.0.0.1:8000/health/live` checks API process liveness.
- `GET http://127.0.0.1:8000/health/ready` checks database connectivity **and
  that the `projects` table has been migrated**; responds 503 when not ready.
- `scripts/smoke_demo_stack.py` also checks Next.js, authenticated login,
  tenant-scoped project listing, Inbox and Activity. It does not print access
  tokens or infrastructure secrets.

The CI workflow builds both images and runs the Compose smoke test on the
synthetic workspace. Existing Python 3.11/3.12 and Next.js checks remain.

## Day-to-day commands

```bash
# Inspect healthy services and one-off completion
docker compose --env-file .env.demo -f compose.demo.yml ps -a

# View backend logs (no credentials are printed by demo seeder)
docker compose --env-file .env.demo -f compose.demo.yml logs --tail=80 demo-api

# Stop services while keeping the demo PostgreSQL volume
docker compose --env-file .env.demo -f compose.demo.yml down

# Irreversibly delete synthetic demo state, then start from scratch
docker compose --env-file .env.demo -f compose.demo.yml down --volumes
```

**Repeat runs:** With the existing volume and `.env.demo`, seed is
idempotent; it never overwrites completed tasks or human review decisions.
Do **not** regenerate `.env.demo` while retaining an existing database
volume: database and account credentials would no longer match.

## Security boundaries and limitations

- **Do not run this stack on a publicly accessible server.** No reverse
  proxy/TLS, session hardening for public hosting, production secret
  management, backups, monitoring, load balancing or multi-user signup exists
  here.
- `.env.demo` is randomly generated, excluded from Git and Docker build
  contexts, written with restrictive file permissions where supported, and
  cannot be overwritten by the generator.
- Host-published ports bind only to `127.0.0.1`. PostgreSQL publishes no
  host port. No Microsoft Graph/Teams/SMTP connection is configured.
- `demo-web` intentionally runs `next dev`: local HTTP can work with
  non-secure **development** cookies. This does not justify non-TLS
  production hosting. Do not switch this container to production mode without
  implementing a secure HTTPS deployment.
- Local Docker admins and users with Docker socket access can inspect
  container environment variables and volumes. Treat the machine as trusted.
- The demo database must be dedicated to synthetic data. Never attach real
  corporate or client data, and never point another application at its volume.
- If your operating system's firewall or local tooling forwards loopback
  ports to other machines, disable that forwarding for this demo.

## Troubleshooting

If startup fails, use `docker compose ... ps -a` and `logs` on the failing
service. Port conflicts on 3000/8000 require stopping the other local
application. A stale `.env.demo` paired with a different database volume can
cause seeding/auth failures. The readiness endpoint distinguishes process
liveness from a missing or unmigrated database schema.

This PR does **not** replace the independent local setup described in
`docs/LOCAL_DEMO_ONBOARDING.md`; it provides the easier Docker alternative.

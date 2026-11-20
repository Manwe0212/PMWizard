# PR #38 — Private Cloud Staging Readiness

## What this PR actually delivers

PMWizard already has `compose.staging.yml` with an unprivileged,
production-mode Next.js frontend bound to **127.0.0.1:3000**, private
FastAPI/PostgreSQL containers, durable Postgres volume and Alembic
migrations. **This PR does not deploy anything or make staging public.**

It adds:

- `deploy/Caddyfile.example` for **single-host** HTTPS termination
  targeting the existing loopback-only Next.js BFF.
- `scripts/smoke_cloud_staging.py` for anonymous, read-only checks over
  a live HTTPS URL, including non-local HTTPS origin, expected anonymous
  session rejection, HSTS, X-Frame-Options, CSP and non-cacheable session.
- Python regression tests for URL and response-header validation.
- A CI syntax check for the proposed Caddy configuration.

## Architecture (single trusted Linux host)

```text
Browser -- HTTPS 443 --> Caddy (host service, public)
                            |
                            +-- loopback 127.0.0.1:3000
                                  |
                            Next.js BFF (staging Compose)
                                  |
                            FastAPI (private Compose network)
                                  |
                            PostgreSQL 16 (private persistent volume)
```

Do not point public traffic at the Python API or the database. This
architecture is for private **synthetic-data staging UAT only**.
The staging host must have firewall rules denying 3000, 8000 and 5432
from public networks. Caddy's host-level access and abuse controls
must be separately evaluated; this reverse proxy **is not a WAF**.

## Before deploying to any server

1. Choose a cloud/VPS provider, region and host with Docker Compose
   and a supported Linux distribution; set a monthly budget and
   independent administrators. This PR does not create accounts.
2. Register or control a DNS name, e.g. `staging.example.org`
   (illustrative placeholder, not an existing PMWizard URL).
3. Point DNS A/AAAA records to the staging server; allow inbound TCP
   ports 80 and 443 for Caddy certificate issuance/renewal. Deny all
   other inbound application ports. Secure SSH via restrictive IP,
   strong keys, and appropriate host updates.
4. Arrange transactional email (real SMTP sender/host, ownership and
   reputation). Existing staging runtime intentionally **fails closed**
   unless invitations and password recovery are enabled with STARTTLS.
5. Produce independent, strong staging-only signing/DB/SMTP secrets
   **outside Git**, in a secret manager. Never reuse `.env.demo`.
   `PMWIZARD_PUBLIC_BASE_URL` must match the HTTPS domain exactly.
6. Arrange automated encrypted database backups, off-host retention,
   a tested restore process, logging/alerting and incident response.
7. Complete security/UAT review from
   `docs/SECURITY_DEPLOYMENT_READINESS.md`; no real customer data.

## Deployment steps (on the controlled Linux staging host)

Use the existing `compose.staging.yml`; **do not** mix it with
`compose.demo.yml`, which is strictly local/synthetic.

```bash
# In a secured checkout of PMWizard:
cp .env.staging.example .env.staging
# Populate .env.staging with non-default secrets securely (never commit).
docker compose --env-file .env.staging -f compose.staging.yml config --quiet
docker compose --env-file .env.staging -f compose.staging.yml up -d --build --wait
docker compose --env-file .env.staging -f compose.staging.yml ps
```

Install Caddy following the supported host operating-system instructions
and configure the host service. Example:

```bash
# Example service environment variable; configure persistently
# for the Caddy service through your init-system, not just this shell.
export PMWIZARD_PUBLIC_HOST=staging.example.org

# First validate a copied Caddyfile with Caddy, after substituting your
# controlled hostname; then put it in the Caddy service configuration.
caddy validate --config deploy/Caddyfile.example --adapter caddyfile
```

`deploy/Caddyfile.example` is a **template**. Setting an environment
variable in an interactive shell will not automatically configure the
Caddy systemd service. Arrange service-level environment injection and
use the host's standard Caddy configuration path and reload procedure.
Ensure Caddy can read the file and write certificates to persistent
storage.

For staging confirmation after TLS is fully operational:

```bash
python scripts/smoke_cloud_staging.py --origin https://staging.example.org
```

Use your **actual** controlled domain. Smoke is non-destructive and
anonymous: it checks `/` and `/api/session` only. It cannot prove that
SMTP, authentication UX, backups, role scoping or end-to-end UAT works.
Run a synthetic UAT with deliberately provisioned staging users once
email/recovery, threat controls and access restrictions are validated.

## Release / rollback protocol

- Keep `main` deployable: push branches through checks and approval.
- Capture a verified database backup **before** migrations.
- Note that Alembic migrations may not be trivially reversible. Stop
  and assess incompatible changes before attempting a rollback.
- Deploy versioned images rather than rebuilding unspecified future
  versions in a mature environment (future hardening).
- Roll back application images only when schema compatibility has been
  verified; do not destroy PostgreSQL volumes.
- `docker compose ... down` (without `--volumes`) stops services but
  preserves the database volume. Never use `down --volumes` as cleanup.

## No-cost promise boundaries

No cloud account, domain or OpenAI API key is created by this PR.
Cloud/VPS, domain, email, persistent storage, certificates (depending
on tooling) and external gateway services can have ongoing costs.
Caddy's automatic HTTPS supports publicly trusted certificate
automation when reachability and DNS are correctly configured.

## Go/no-go gates

- [ ] PR #38 CI and Caddy syntax check passed
- [ ] DNS and HTTPS certificates verified from another device/network
- [ ] Edge access policy and firewall externally verified
- [ ] Backend and DB not exposed as public host ports
- [ ] Email verification/password reset tested with synthetic addresses
- [ ] Backup and restore drill completed
- [ ] Host-level monitoring, alerting and incident ownership arranged
- [ ] `smoke_cloud_staging.py` passed against actual controlled origin
- [ ] Synthetic multi-user session and permission tests passed
- [ ] Explicit approval to grant private external UAT access

Until these boxes are completed, continue using `localhost:3000`
for the interview demo; do not characterize a staging design as a
live public deployment.

# PR #40 — Railway Staging: Zero-Spend Preparation Plan

## Verified Railway state (2026-11-20)

A Railway project named `PMWizard` exists in the owner's personal workspace:
- Project ID: `438abfb7-0c59-4008-b425-e84cf26888cc`
- Environment: `staging`, ID `4907fb8d-d5c3-42a2-8cea-068f802cbc18`
- Services: **0**; Deployments: **0** when checked.

**Spending instruction from the project owner: do not activate billable
resources.** No services, managed databases, volumes, domains, deployments,
runtime variables or scheduled operations may be provisioned under this plan.
A project record alone does not establish a running, free application.
Railway billing/pricing must be checked with the owner before activation.

## What is prepared now

This is a **manual, source-controlled deployment design**. It changes
documentation and tests only. It does **not** trigger Railway builds or
deployments.

PMWizard's PR #39 operator script implements a *single-VPS deployment*
through Docker Compose and Caddy; Railway is a different architecture.
Do not run `scripts/deploy_staging_host.sh` in Railway. Railway would
deploy **independent services** with private networking instead.

### Planned service map — NOT provisioned

| Proposed service | Source | Docker build | Runtime | Networking |
| --- | --- | --- | --- | --- |
| `pmwizard-web` | `Manwe0212/PMWizard`, root directory `/web` | `Dockerfile.staging` | Node 22, listens on `0.0.0.0:3000` | Only public-facing service via HTTPS, with restricted testers |
| `pmwizard-api` | Same GitHub repo, root directory `/` | `Dockerfile.api` | Python 3.12, listens on `0.0.0.0:8000` | Railway private network only, no public domain |
| `Postgres` | Railway PostgreSQL service (future) | Railway-managed database | PostgreSQL-compatible persistence | Private connection, no public TCP proxy |

A separate migration execution mechanism must be designed and verified
before deployment. The single-VPS `stage-migrate` service does not
automatically exist in Railway. Running schema upgrades as ordinary
web/API startup code is unsafe for multiple replicas. A dedicated,
once-per-release migration task with explicit operator approval is
preferred, backed by verified backup/restore; do not provision until
this path is tested.

## Planned environment variable contracts (NAMES ONLY)

The names below are requirements, **not concrete credentials**.

### Web
- `NODE_ENV=production`
- `PORT=3000`
- `PMWIZARD_API_URL`: private URL of `pmwizard-api`, expected
  `http://pmwizard-api.railway.internal:8000` after service creation
- `PMWIZARD_PUBLIC_BASE_URL`: exact public HTTPS origin obtained
  only after domain configuration

### API
- `PMWIZARD_ENV=staging`
- `PMWIZARD_DATABASE_URL`: **must use**
  `postgresql+psycopg://` scheme to satisfy the existing runtime
  preflight; a Railway `postgres://` / `postgresql://` value is not a
  drop-in replacement unless explicitly adapted
- `PMWIZARD_AUTH_SECRET`: independently random strong value, never
  copied from `.env.demo`
- `PMWIZARD_PUBLIC_BASE_URL`: same HTTPS origin as web
- `PMWIZARD_INVITATION_EMAIL_ENABLED=true`
- `PMWIZARD_INVITATION_REQUIRE_EMAIL_VERIFICATION=true`
- `PMWIZARD_PASSWORD_RESET_ENABLED=true`
- `PMWIZARD_NOTIFICATION_SMTP_HOST`: secure mail provider
- `PMWIZARD_NOTIFICATION_SMTP_PORT`: mail provider port (typically 587)
- `PMWIZARD_NOTIFICATION_EMAIL_FROM`: verified sender
- `PMWIZARD_NOTIFICATION_SMTP_STARTTLS=true`
- `PMWIZARD_NOTIFICATION_SMTP_CREDENTIAL_REF` or
  `PMWIZARD_SECRET_SMTP_NOTIFICATIONS` according to the notification
  adapter contract
- `PMWIZARD_ENABLE_LOCAL_DEMO=false`

Railway's service variable references can avoid copying database
credentials by hand. When activating, validate exact reference names
and URL encoding; never log resolved secret values. The existing API
will refuse to start in staging if secrets, HTTPS origin, PostgreSQL
configuration or SMTP requirements are invalid.

## Security and data rules

- Use synthetic `Atlas Delivery`-style records only.
- Do not copy the user's local `.env.demo` or the existing local
  PostgreSQL volume into Railway.
- Keep public ingress limited to the web BFF. Railway's default HTTPS
  domain alone is **not access control**; restrict testers with an
  independently configured access gateway/network policy before enabling
  public exposure.
- Do not expose FastAPI or PostgreSQL via a public domain/TCP proxy.
- Reuse authorization, CSRF, secure cookies, staging preflight and
  read-only smoke test already present in the repository.
- Review the provider's region, retention, backup options, usage budget,
  and documented billing behavior before any service creation.
- A backup/restore drill and authenticated synthetic UAT remain required
  before controlled external testing.
- The optional AI status report provider remains unconfigured. A
  ChatGPT subscription does not include an OpenAI Platform API key.

## Release activation gate (not part of PR #40)

Only after the owner expressly authorizes resource activation:

1. Review current Railway pricing, trial and spending controls. A selected
   monthly budget is not necessarily a hard spending cap.
2. Review Railway monorepo and Docker configuration for the pinned
   `main` commit, plus a safe one-off Alembic migration process.
3. Create the private database and API/web services in `staging`.
4. Inject non-demo secrets using Railway secret management and private
   service references.
5. Configure origin/TLS, domain and external access restrictions.
6. Deploy, then verify terminal SUCCESS statuses, runtime health,
   authenticated synthetic UAT and security headers.
7. Verify resource consumption and backups; publish the demo URL only
   after a successful restricted-access sign-off.

**No steps 3–7 are authorized by the current zero-spend instruction.**

## Safe next action

GitHub PR #40 can be merged after checks without incurring Railway
compute, database or bandwidth usage, because it creates no Railway
services or deployments. Continue using `localhost:3000` for the
technical assessment until activation is explicitly authorized.

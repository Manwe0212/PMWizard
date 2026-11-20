# PR #39 — Operator-Controlled PMWizard Cloud Staging Deployment

## Outcome and limitations

This increment adds an **operator-run deployment command** for the
**already-defined private Linux-host staging architecture**. It is a
reproducible path from a reviewed GitHub `main` commit to running
staging containers, not an actual cloud deployment. No provider, VPS,
DNS name, SMTP service, or online account is provisioned by GitHub.

The interview demo at `http://localhost:3000` remains the reliable
fallback until real network, TLS, access and backup tests pass.

## Proposed deployment model

The narrow, testable first path is one trusted Linux VPS or virtual
server, Docker Compose, PostgreSQL persisted inside a named volume,
FastAPI on an internal Compose network, Next.js BFF bound solely to
`127.0.0.1:3000`, and host-installed Caddy for HTTPS.

```
Verified GitHub main commit
           |
           v
Linux operator checks + database backup confirmation
           |
           v
bash scripts/deploy_staging_host.sh --apply
           |
           +--> stage-db, stage-migrate, stage-api, stage-web
           |
           v
Caddy host HTTPS reverse proxy --> Next.js BFF only
           |
           v
Anonymous remote smoke + synthetic authenticated UAT
```

A public DNS hostname is not proof of safe public production hosting.
Only synthetic test data and restricted testers are permitted in this
staging design. The current Caddy example has **no built-in login or
IP allowlist** and must NOT be exposed without separately configured
trusted ingress restrictions. The built-in application login is not a
substitute for an edge access control or anti-abuse protection.

## Prerequisites requiring action outside this PR

1. **Provider/host**: choose an accountable VPS/VM provider and region,
   agree costs, create a supported Linux host and a separate staging
   operator account. Secure the server OS and SSH first.
2. **Domain and DNS**: own a hostname and set DNS A/AAAA records. Use it
   consistently for `PMWIZARD_PUBLIC_BASE_URL` and Caddy host.
3. **Firewall and edge restrictions**: inbound TCP 80/443 for certificate
   operations, deny direct exposure of app port 3000, API 8000 and
   database 5432. Restrict staging audience through an independent
   edge access policy, IP allowlist or trusted access gateway.
4. **Secrets**: independent strong signing key, nondefault database
   credentials, SMTP provider and sender in `.env.staging`, protected
   outside Git. Do not copy `.env.demo` or publish screenshots of
   secrets. Run `chmod 600 .env.staging` on the Linux host.
5. **Backup and recovery**: retain an encrypted, off-host backup and
   verify the restore procedure. A GitHub CI pass cannot establish
   data-recovery capability.
6. **Caddy host service**: install/configure Caddy with durable
   certificate storage. Set `PMWIZARD_PUBLIC_HOST` on the Caddy
   **system service** and validate/reload it as required.
7. **SMTP and invitations**: stage requires working invitation and
   account-recovery delivery; validate with synthetic addresses.

## Exact deployment sequence

Run only on the trusted **Linux staging host** in a secured checkout of
this repository. The default command does not deploy:

```bash
git switch main
git pull --ff-only origin main
cp .env.staging.example .env.staging
# Populate the staging-only secrets securely.
chmod 600 .env.staging
bash scripts/deploy_staging_host.sh --check
```

The `--check` mode validates Docker/Compose presence, Linux host,
secret file permissions and staging Compose configuration. It does
not connect to the internet or inspect domain security.

Only after completing and **independently verifying** the off-host
backup, host hardening, firewall and restricted access should the
operator acknowledge the release gates:

```bash
PMWIZARD_BACKUP_VERIFIED=yes \
PMWIZARD_STAGING_ACCESS_APPROVED=yes \
bash scripts/deploy_staging_host.sh --apply
```

**These two environment flags are human attestations, NOT automated
proof** that a backup or edge security exists. The command requires a
clean checked-out `main` branch and keeps staging separate from
`compose.demo.yml`. It will run Alembic migrations as configured in
`compose.staging.yml`, which can change database schema. Review schema
compatibility and backup *before* applying.

After configuring DNS, TLS, and Caddy ingress restrictions separately:

```bash
python scripts/smoke_cloud_staging.py --origin https://YOUR-STAGING-HOSTNAME
```

Only use an actual hostname you control. The anonymous smoke checks
response status, security headers and session noncacheability.
It **does not** test login, email delivery, rate limits, backup restore,
multitenancy or realistic user journeys.

For real staging go-live, document manual UAT and a controlled
approval. Do not invite external testers until additional security
review is complete.

## Operator failure and rollback

- For `--check` failure, correct host settings; no deployment occurs.
- For container failure, inspect `docker compose --env-file
  .env.staging -f compose.staging.yml ps` and sanitized logs
  (avoid dumping secrets or passwords).
- Do not delete `stage_pgdata` or run `down --volumes`.
- A failed migration requires DBA-level recovery and potentially a
  restore from verified backup. Reverting Git does not automatically
  reverse migrated database tables.
- This script intentionally does not offer a one-click rollback:
  versioned image promotion and reversible migrations remain future
  release-engineering work.

## What this PR proves in CI

- Bash syntax and safe/default CLI behavior
- No demo Compose/volume-destruction commands in the release script
- Existing Python test matrix and frontend build
- Existing Docker demo smoke and staging proxy/image validation

CI does **not** purchase hosting, deploy to a live server, validate
mail sender credentials or certify the internet-exposed system.

## Release checklist

- [ ] CI passed and PR merged
- [ ] Linux staging host, monthly budget and responsible operator chosen
- [ ] DNS name and ingress restrictions verified
- [ ] Independent secrets and SMTP configured
- [ ] Off-host backup and restoration verified
- [ ] `--check` passed on the real host
- [ ] `--apply` completed against the reviewed main branch
- [ ] Caddy HTTPS trusted certificate and host reload verified
- [ ] Anonymous and authenticated synthetic UAT completed
- [ ] Sign-off obtained for limited external access

Until then, the PMWizard application is still locally hosted at
`localhost:3000`; the project does not yet have a live public URL.

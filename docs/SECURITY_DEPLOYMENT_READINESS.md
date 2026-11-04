# PR #32 — Security & Deployment Readiness V0

This PR hardens PMWizard's existing authenticated MVP so the next PR can run
**controlled UAT in a private staging environment**. It does not constitute
a production penetration test, compliance certification, or permission to
process live customer data.

## New runtime security controls

### Persistent authentication throttles

The API now uses an `auth_rate_limits` table shared by all application
replicas. Counter increments are **atomic** via PostgreSQL or SQLite
`INSERT ... ON CONFLICT DO UPDATE`, so restarting an API process does not
reset counters. The key is an **HMAC-SHA256 digest** using the application
signing secret, scoped to endpoint/identity/source and 15-minute window.
The database stores no plaintext email addresses, workspace IDs, raw IPs,
or secrets in its throttle keys.

| Protected operation | Maximum requests per 15-minute window |
| --- | --- |
| Login, same tenant/email | 12 |
| Login, same observed source | 100 |
| Password recovery request, same tenant/email | 15 |
| Password recovery request, same observed source | 60 |
| Password recovery confirmation, same source | 80 |
| Invitation redemption, same source | 80 |

Limits include successful and unsuccessful attempts. Rejected attempts
continue to count; an over-limit response returns **429** and
`Retry-After`. Recovery and invitation workflows retain their own
existing one-time-token rules. These are basic protections, **not an
adequate credential-stuffing or distributed abuse defense**.

**Important proxy limitation:** The API sees the address of the immediate
calling peer (often the internal Next.js server), rather than the end-user
IP. It intentionally ignores unsanitized `X-Forwarded-For`. This avoids
trusting spoofable headers but means source limits may be shared across
users behind the BFF. The tenant/email bucket remains independent.
Configure a trusted edge gateway/WAF with real-client-IP throttles
before providing any public access. Thresholds need monitoring and tuning
for legitimate teams sharing a workspace. A scheduled operational cleanup
should remove expired rate-limit rows, e.g. using a trusted maintenance job
with `DELETE FROM auth_rate_limits WHERE expires_at < CURRENT_TIMESTAMP`;
the application does **not** automatically prune these rows in V0.

### Browser protections

- All `/api/*` non-GET requests pass through a Next.js 16 proxy.
  In **production-mode Next.js**, an absent, mismatched or non-HTTPS
  `Origin` is rejected before a cookie-authenticated mutation executes.
  The expected origin is `PMWIZARD_PUBLIC_BASE_URL`. Local dev remains
  compatible with curl/demo scripts lacking `Origin`.
- The existing per-route Origin guards remain active.
- New response headers: `X-Frame-Options: DENY`,
  `Content-Security-Policy: frame-ancestors 'none'; base-uri 'self';
  form-action 'self'`, `Referrer-Policy: no-referrer`,
  `X-Content-Type-Options: nosniff`, `Cross-Origin-Opener-Policy`
  and a browser `Permissions-Policy`. Production-mode web adds HSTS.
- BFF API responses are marked `Cache-Control: private, no-store`.
- This deliberately does not claim a comprehensive script-src nonce
  CSP, full CSRF review or hardened client-side supply chain.

**Reverse-proxy contract:** Preserve the external HTTPS scheme and public
Host. Strip incoming `X-Forwarded-*` headers from untrusted clients and
set canonical forwarded headers at the trusted proxy. Terminate HTTPS
with a valid certificate. Do not publish the Python API or PostgreSQL
port to the Internet. Set the same canonical
`PMWIZARD_PUBLIC_BASE_URL=https://your-domain` for the web and API.
Production-mode `Secure` cookies will not work over plaintext HTTP.

### Fail-closed runtime preflight

`create_default_app()` validates deployment configuration whenever
`PMWIZARD_ENV` is `staging` or `production`:

- Signing key at least 48 characters, independently random (a basic
  sanity check, **not** a measured entropy guarantee)
- PostgreSQL with non-default credentials; **production** additionally
  requires a `sslmode=verify-full` or `verify-ca` DB connection setting
  (use `verify-full` and an appropriate root certificate in real production)
- A non-local, public HTTPS origin without fragments/credentials
- Email invitations enabled, strict email verification enabled, password
  recovery enabled, SMTP sender/host and STARTTLS configured
- Demo seeding must not be enabled
- Bearer expiry between 5 and 30 minutes

Preflight never prints signing secrets, DB credentials or SMTP passwords.
The local Docker demo retains its existing development configuration.

## Dedicated controlled staging stack

`compose.staging.yml` defines PostgreSQL, migrations, Python API and a
**production-mode Next.js standalone build**. It does not include any
demo seeder. Only the Next.js web port is published, on host
`127.0.0.1:3000`; PostgreSQL and the Python API are private Docker
network services. The web image uses an unprivileged Node user.

Prepare a private staging environment:

```bash
cp .env.staging.example .env.staging
# Populate .env.staging in a secret manager or secure local environment.
# Never commit the populated file.
docker compose --env-file .env.staging -f compose.staging.yml config --quiet
docker compose --env-file .env.staging -f compose.staging.yml up --build -d --wait
docker compose --env-file .env.staging -f compose.staging.yml ps
```

A TLS-terminating reverse proxy on the **same trusted host**, with
the correct public hostname and certificates, is required before the
web server can be used by other users. If using another host, replace
the loopback publishing strategy with a private service network and
strict network policies; do not open the port indiscriminately.

Make sure the `PMWIZARD_STAGING_DATABASE_URL` references the same
user/password/db defined by `PMWIZARD_DB_USER`,
`PMWIZARD_DB_PASSWORD` and `PMWIZARD_DB_NAME`. URL-encode special
characters. Never use a live production database, customer email
addresses, or real customer data in the staging environment.

Stop the staging stack without deleting persistent data:

```bash
docker compose --env-file .env.staging -f compose.staging.yml down
```

Perform backup/restore drills and define explicit retention/deletion
policies before using real data. `down --volumes` permanently destroys
the staging database volume; do not use it casually.

### Operator readiness checklist

- [ ] Distinct staging tenant, PostgreSQL volume and random credentials
- [ ] Public staging DNS and trusted HTTPS reverse proxy configured
- [ ] External client IP limiting at edge, WAF and abuse observability
- [ ] Verified SMTP sender, delivery reputation and inbox ownership testing
- [ ] No demo seed, test-only accounts, debug headers or shared secrets
- [ ] Backup/restore drill and migration rollback plan
- [ ] No direct Python API/DB ports exposed, verify external firewall
- [ ] Logs scrubbed of tokens, passwords, PII and raw email reset URLs
- [ ] Secure secret injection/rotation; credential ownership assigned
- [ ] Confirm BFF Origin rejection, login throttling and session invalidation
- [ ] Confirm least-privilege roles for connectors and automations
- [ ] Document a security incident response and account-access recovery path
- [ ] Run PR #33 UAT acceptance cases and record defects; go/no-go decision

## Tests and CI gate

```bash
alembic upgrade head
pytest -q tests/test_auth_rate_limits.py tests/test_deployment_security.py
pytest -q
npm --prefix web run lint
npm --prefix web run build
```

CI must pass Python 3.11/3.12 full suites, Next.js lint/build, Docker demo
smoke, and staging Compose validation. Real HTTPS/SMTP load testing,
penetration testing, backup restores and UAT are explicitly **not**
executed by the PR CI.

## Remaining risk before a public SaaS launch

This PR does not implement MFA, SSO/SCIM, a full OWASP threat-model
review, anti-bot/CAPTCHA, WAF configuration, fully audited connector
permissions, a CSP with nonce-based script isolation, managed remote
PostgreSQL TLS deployment, durable transactional email outbox, background
retention cleanup, vulnerability scanning or formal audit logging
retention. An externally accessible commercial service must address
these gaps in a subsequent hardening program.

**Release decision:** Passing PR #32 CI permits planning *private,
synthetic-data staging UAT*; it does not certify public production use.

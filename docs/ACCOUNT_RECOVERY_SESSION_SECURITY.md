# PR #31 — Password Recovery & Session Security V0

This milestone strengthens PMWizard's local password authentication. It
builds on PR #30's certificate-verified SMTP delivery and does not turn the
localhost demo into a public, production-ready identity provider.

## User workflows

**Forgot password:** On the sign-in page, select **Forgot your password?**
Enter the workspace/tenant UUID and your account email. If an active account
with a previously verified email address exists in that tenant, PMWizard
sends a **one-time link valid for 30 minutes**. Open it, choose a new password
(12–256 characters), and sign in again. The new password is Argon2id hashed;
every previously issued JWT becomes invalid immediately.

**Sign out:** The sign-out action now calls
`POST /v1/auth/logout` with the current bearer token before clearing the
HttpOnly browser cookies. A SHA-256 digest of the token's unique `jti` is
stored in `revoked_sessions`, and all future requests using that particular
token return 401, even if its expiry has not passed. Other devices stay
signed in.

**Sign out all devices:** The explicit action calls
`POST /v1/auth/logout-all`. It increments a database-backed
`app_users.auth_version`; any previously issued bearer token, including
the token on the device invoking the action, immediately becomes invalid.
The browser clears its own cookies afterward. New logins use the updated
version.

## Recovery API

These endpoints do not require an existing login session:

```http
POST /v1/auth/password-reset/request
Content-Type: application/json

{
  "tenant_id": "<workspace UUID>",
  "email": "verified-user@example.com"
}
```

If the recovery transport is configured, the API returns **202** with the
same generic text for known, unknown, unverified, inactive and throttled
addresses. No tenant directory information is returned. The web proxy
also intentionally produces only the generic acknowledgement. The sender
uses an email link like:

`https://your-public-app.example/reset-password#token=<random-secret>`

The token is in the URL **fragment**, is not sent in the initial GET, and
is immediately removed from the browser address bar by the reset form.

```http
POST /v1/auth/password-reset/confirm
Content-Type: application/json

{
  "token": "<one-time-secret>",
  "password": "<new-password-of-at-least-12-chars>"
}
```

When valid: **200**, with
`{"status":"password_updated","sessions":"revoked"}`. Expired, invalid,
consumed or replayed tokens return the same generic **400** error. Existing
verified users in other tenants cannot be reset with another tenant's
workspace identifier.

**Recovery is disabled by default.** With recovery disabled, both endpoints
return **503**; there is no fallback that emails a reset token through
insecure transport.

## Required environment

The operator must already have the PR #30 verified-mail provider configured
with a public HTTPS origin and STARTTLS/valid certificate:

```dotenv
PMWIZARD_PUBLIC_BASE_URL=https://your-domain.example
PMWIZARD_INVITATION_EMAIL_ENABLED=true
PMWIZARD_NOTIFICATION_SMTP_HOST=smtp.example.com
PMWIZARD_NOTIFICATION_SMTP_PORT=587
PMWIZARD_NOTIFICATION_EMAIL_FROM=security@example.com
PMWIZARD_NOTIFICATION_SMTP_STARTTLS=true
PMWIZARD_NOTIFICATION_SMTP_CREDENTIAL_REF=env:SMTP_NOTIFICATIONS
PMWIZARD_PASSWORD_RESET_ENABLED=true
```

Credentials are resolved through the existing
`EnvironmentSecretProvider`; **never commit a secret to Git**. Startup
fails with a clear configuration error when recovery is enabled without
the verified-email delivery configuration. The Compose synthetic demo
leaves recovery disabled, deliberately.

## Security and privacy guarantees

- Database migration `0013_account_security_v0` adds:
  `password_resets`, `revoked_sessions`, and
  `app_users.auth_version` defaulting to zero for existing accounts.
  The migration can be reversed.
- A password reset secret is generated from **256 random bits** and stored
  only as a SHA-256 hash; the raw secret appears only in the outbound email
  and recipient browser memory. JWT `jti` values are also stored only as
  SHA-256 digests when revoked.
- Password recovery is available only to active accounts with a
  pre-existing non-null `email_verified_at`. This is intentionally
  **not** the same as believing a typed email or a manually delivered
  PR #29 invitation. Unverified/bootstrap accounts require trusted
  operator assistance.
- No account discovery: unknown/unverified/inactive account requests
  receive the same public 202 result as eligible known accounts.
- A per-user, database-persisted **15-minute cooldown** prevents repeated
  reset emails to the same verified account. Generic responses do not
  reveal throttling.
- Successful recovery atomically writes the Argon2id password hash,
  increments the authentication version, consumes all outstanding reset
  links for that account, and emits an `account_password_reset` audit
  event. No password, SMTP secret, URL or reset token is in the audit.
- The backend validates each API bearer token against its current
  database-backed authentication version **and** the revoked-JTI table.
  It no longer relies solely on the JWT signature and expiry.
- JWTs remain short-lived (default **30 minutes**) and are stored
  in HttpOnly, SameSite cookies. The BFF now rejects mismatched
  origins on login, reset, logout, and logout-all requests; request
  payloads are size-limited, and internal diagnostics are not returned
  to unauthenticated callers.
- Logout clears local cookies even if the API cannot be reached and
  reports when server-side revocation was not confirmed.
- Only the backend can revoke a session or all sessions, and only with
  a validated Bearer token. Trusted development-header authentication
  cannot invoke session-security endpoints.
- The reset flow **does not automatically sign the user back in**.
  Existing sessions on other devices lose access immediately, so
  a stolen old cookie cannot continue using the project API.

## Operational limitations / next phase

- Recovery email submission is synchronous in the database transaction.
  SMTP failure rolls back the reset request; a database failure after
  successful SMTP submission may result in a dead link. A durable
  transactional outbox and retry worker are recommended for production.
- A hash stored in a token table is still sensitive operational
  metadata and should be protected by database access controls.
- IP-based login throttling, broader brute-force defenses, abuse monitoring,
  credential-stuffing protection, identity federation, MFA, verified
  recovery for existing legacy/bootstrap users, session-device history,
  account-lock recovery, CSRF defense-in-depth and production monitoring
  are **not included**. Handle them in security/deployment hardening
  (PR #32) before any internet-facing customer pilot.
- The original project governance, invitation permissions and tenant
  isolation remain unchanged.

## Verification

```bash
alembic upgrade head
pytest -q tests/test_account_recovery_security.py
pytest -q
```

CI also verifies full Python 3.11 and 3.12 suites, Next.js lint/build and
the end-to-end Docker demo smoke. No real SMTP emails are transmitted by
CI; tests use injected fake mail providers and in-memory databases.

# PR #30 — Verified Email Invitations & Account Onboarding V0

This change extends the one-time links introduced in PR #29 with **opt-in
email delivery over certificate-verified STARTTLS**, and records mailbox
verification **only after** the recipient redeems a link sent to their
invited email address.

It is suitable for controlled testing or a staged internal pilot after
the infrastructure has been properly configured. It is **not** a
production-ready public identity system.

## What changed

- Project managers with `project:manage_members` may select **Send by email**
  from the **Members & Roles → New-user invitations** form.
- The application uses the existing SMTP sender/credential-reference
  settings, but requires STARTTLS with system-trusted certificate validation
  for invitations.
- The email link uses a **256-bit random secret** in the URL fragment:
  `https://your-app.example/invite#token=<one-time-token>`. The fragment
  does not travel to the app server in the initial HTTP GET.
- **The manager never receives the token** when email delivery is selected:
  the API returns `"token": null` and a status of `sent`.
- The database stores only a token digest and metadata:
  `delivery_method`, `delivery_status`, `delivered_at`,
  `accepted_at`, `accepted_user_id`. The plaintext link and password
  never enter the invitation table or audit history.
- Following the emailed link and creating an account sets
  `app_users.email_verified_at`. The field is **null** for legacy users
  and for invitations manually shared in PR #29.
- An SMTP failure returns an error **without committing the invitation**
  or its audit record. The user can retry issuance.
- Existing expiry (seven days), one-time acceptance, revocation,
  capacity limit and tenant/project-scoped fixed roles remain enforced.

## Configuration

Only a trusted operator should enable email delivery. In an HTTPS
installation, configure environment variables securely:

```dotenv
PMWIZARD_PUBLIC_BASE_URL=https://pmwizard.example.com
PMWIZARD_INVITATION_EMAIL_ENABLED=true
PMWIZARD_INVITATION_REQUIRE_EMAIL_VERIFICATION=true

PMWIZARD_NOTIFICATION_SMTP_HOST=smtp.example.com
PMWIZARD_NOTIFICATION_SMTP_PORT=587
PMWIZARD_NOTIFICATION_EMAIL_FROM=invites@example.com
PMWIZARD_NOTIFICATION_SMTP_STARTTLS=true
PMWIZARD_NOTIFICATION_SMTP_CREDENTIAL_REF=env:SMTP_NOTIFICATIONS
# Do NOT commit the following secret; inject it via your secret manager:
# PMWIZARD_SECRET_SMTP_NOTIFICATIONS=<JSON with username/password>
```

These SMTP variables are shared with the existing optional notification
delivery subsystem. The credentials are referenced through
`EnvironmentSecretProvider` and never saved in the PMWizard database.
Do not put example or real SMTP credentials into version control.

The API refuses to start in strict mode without a configured email
transport. It refuses an email-enabled configuration without a valid
**public HTTPS origin** or STARTTLS. It also refuses manual invitation
creation and redemption when
`PMWIZARD_INVITATION_REQUIRE_EMAIL_VERIFICATION=true`.

For existing local demo installs, both new feature flags default to
`false`. Manual invitation links continue to work, but their users
have no `email_verified_at` timestamp. The frontend shows only delivery
methods allowed by the authenticated backend's settings. There is no
SMTP transport or public domain in the Docker demo stack by default.

**Strict mode recommended for any customer pilot:** enable *both*
environment flags. Do not treat already bootstrapped legacy user accounts
as email verified; migrating identity policies and restricting existing
logins require a separate, explicit rollout.

## API

Project manager issue request:

```http
POST /v1/projects/{project_id}/invitations
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "email": "new-colleague@example.com",
  "role": "viewer",
  "delivery_method": "email"
}
```

On success (`201 Created`):

```json
{
  "invitation": {
    "id": "<uuid>",
    "email": "new-colleague@example.com",
    "role": "viewer",
    "status": "pending",
    "invited_by": "<uuid>",
    "created_at": "<utc timestamp>",
    "expires_at": "<utc timestamp>",
    "delivery_method": "email",
    "delivery_status": "sent",
    "delivered_at": "<utc timestamp>"
  },
  "token": null
}
```

`GET /v1/projects/{project_id}/invitations` returns a manager-only list
without any token. It additionally advertises:
`email_available` and `strict_email_only` for the frontend's delivery
selector. Revocation and acceptance endpoints remain as in PR #29.

If the SMTP server rejects delivery, the issuance endpoint replies with
a generic `503` and **no invitation is created**. The underlying error,
secret alias, credentials and raw token are not included in the response.

## Security and operational caveats

- **Mailbox control is established by redemption of a secret received at
  the invited address, not by SMTP acceptance alone.** SMTP reports
  *submission*, not guaranteed mailbox delivery, and an invitation
  forwarded to someone else can be redeemed by that recipient. Users
  should not forward these links.
- Account email is bound to the **email on the original invitation**;
  signup cannot change it. A signed-in user with that existing email
  must use regular project membership management instead.
- Sending email occurs **inside a guarded database transaction** before
  commit. If SMTP succeeds but the DB commit fails, the recipient may
  receive a nonfunctional link. The manager should reissue after checking
  status; link tokens are intentionally not recoverable.
- Existing user accounts are **not retroactively verified**. Strict
  invitation policy only applies to new invitation issuance/redeeming;
  it does not enforce verified email on all older users' login.
- Emailed links are not logged by the app, but external email systems
  and a recipient's mailbox may retain the links. Expiry, one-use
  semantics, HTTPS, and revocation limit exposure.
- PR #30 does **not** include independent email bounce handling, SMTP
  rate limiting, CAPTCHA, public abuse protection, user password reset,
  session revocation, enterprise SSO, SCIM, passwordless sign-in,
  phishing protection, or dedicated tenant administrator approval.
- This system should not be made internet-facing with real customers
  without HTTPS, secret management, monitoring, backups, access
  controls and security review of the entire identity lifecycle.

## Testing

```bash
pytest -q tests/test_verified_email_invitations.py
pytest -q tests/test_project_invitations.py
pytest -q
```

Tests use an in-memory mail sink and fake SMTP transport. **No actual
email is sent by CI**. The tests cover no-token-in-response,
SMTP failure rollback, strict manual-link rejection, verified
timestamp on redemption, legacy unverified state and certificate-
verifying TLS configuration. The Docker end-to-end smoke continues
to validate the complete local stack after the migration.

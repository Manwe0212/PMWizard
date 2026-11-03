# PR #29 — User Invitations & Account Onboarding V0

> **Update (PR #30):** Verified email invitation delivery is now optionally
> supported with HTTPS + certificate-verified STARTTLS SMTP. Successful
> redemption of an emailed link sets `email_verified_at`; manual links
> remain unverified. For email-only onboarding configure the strict
> verification flag. See [Verified Email Invitations](VERIFIED_EMAIL_INVITATIONS.md).
>


PMWizard now supports **invitation-only registration for a project in an
existing tenant**. Project managers with `project:manage_members` may
generate a seven-day, single-use link for a person who does **not yet have
a PMWizard account in their tenant**. This workflow builds on PR #27
(project creation) and PR #28 (existing-member role administration).

This is **not public signup, email delivery, organization administration,
identity verification or production SSO**.

## Manager workflow

1. Sign in, select your project and open **Members & Roles**.
2. Under **New-user invitations**, enter the recipient's email address and
   select Viewer, Reviewer or Project Manager.
3. Click **Create invite**. The API returns a 256-bit random secret **once**.
4. Copy the `/invite#token=...` link using the button, and send it to
   the intended recipient through a separately authenticated, trusted channel.
   **No automatic email is sent.**
5. The recipient opens the link, supplies a display name and a password
   (12+ characters), and accepts. PMWizard creates the account, assigns
   the selected project role, signs them in, and opens the project.
6. Managers can see invitation status and expiry, and revoke a pending link.
   An expired or revoked link cannot be redeemed.

If the recipient already has an account in the same tenant, use the
**Add existing member** form from PR #28 instead. The same email in a
different tenant has no special access and does not block an invitation.

## Permission templates

| Role | Granted project permissions |
| --- | --- |
| Viewer | `project:read` |
| Reviewer | `project:read`, `project:review` |
| Project Manager | `project:read`, `project:review`, `project:manage_members` |

**Caution:** Under the current MVP authorization model,
`project:review` also permits some other operational actions, including
some connector configuration and automations. Reviewer is not a narrowly
restricted comment-only role. Manager delegates membership administration
on that **one project**, not the whole tenant.

## API

Bearer-authenticated project managers only:

```text
GET    /v1/projects/{project_id}/invitations?limit=50&offset=0
POST   /v1/projects/{project_id}/invitations
DELETE /v1/projects/{project_id}/invitations/{invitation_id}
```

Create request:

```json
{
  "email": "new-teammate@example.com",
  "role": "viewer"
}
```

Successful POST returns `201` with a non-cacheable response, containing:
an `invitation` record (id/email/role/status/expiry) and a `token`
**returned only on that response**. List responses intentionally omit
the token, even for the original inviting manager.

The recipient needs no account or tenant UUID:

```text
POST /v1/invitations/accept
```

```json
{
  "token": "<one-time-secret>",
  "display_name": "Collaborator Name",
  "password": "<new-password-12-plus-characters>"
}
```

Successful acceptance returns a short-lived signed access token, user
record and project ID. The Next.js `POST /api/invitations/accept`
proxy stores the token in a secure-configured HttpOnly, SameSite session
cookie and sets the project-selection cookie. It does not forward the
access token to the browser JavaScript client.

The landing page `/invite#token=...` reads the fragment *in the browser*
and immediately removes it from the address bar. The fragment is never
included in an HTTP request to the web server or request URL access logs.
Do not move the token into a query parameter. Browser memory contains the
token only during the activation flow.

## Persistence and enforcement

Migration: `0011_project_invitations_v0` (reversible), adding
`project_invitations` with tenant/project/email/role/inviter/expiry/status,
plus `token_hash` (SHA-256 of a 256-bit cryptographically random token).
**No plaintext invite token or new password** is stored in this table or
the audit log. Account passwords are Argon2id hashes in `app_users`.

- Maximum **25 active invitations per project**; duplicate active
  invitations to the same email are rejected. Expired/revoked links can
  be replaced. Links expire after **seven days**.
- Only the current `project:manage_members` bearer-authenticated manager
  may create, list or revoke; neither trusted-header dev auth nor other
  project members may issue invitations.
- List queries are scoped to the selected project and tenant with bounded
  pagination. User-directory enumeration is not exposed.
- The acceptance endpoint checks the token digest and deadline under a
  row-level database lock. Expired, revoked, previously accepted or
  unknown tokens receive the same generic invalid-invitation error.
- Account creation, membership, invitation consumption and the acceptance
  audit log are **committed together**, or rolled back together.
- Once used, the token cannot create a second account. Existing JWTs do
  not carry stale membership permissions; all access is still resolved
  against current project membership.
- Audit entries record project, actor, invitation ID, role and state
  transition, without raw token, password or plaintext invitation link.

## Development and testing

```bash
alembic upgrade head
pytest -q tests/test_project_invitations.py
pytest -q
```

The existing Compose demo stack applies Alembic migrations at startup;
its smoke test remains a CI check. No SMTP credentials or external
providers are required for manual link issuance.

## Important production limitations

This is a controlled MVP, **not a verified email invitation system**:
possession of the full secret link is sufficient to create an account
with the invited email, and the system does not independently verify
mailbox ownership. Only transmit invitations over trusted, authenticated
channels. For real external customers, add verified email delivery
and ownership proof, rate limiting and abuse controls, anti-CSRF policy
verification for the full deployment, account recovery, tenant-wide
policy enforcement, HTTPS, production secrets handling, and an operational
security review.

An invitation's role is fixed at issuance. If that role needs changing
after acceptance, a manager can use **Members & Roles**. Distributing a
manager-level invitation grants that person's account the ability to
manage project membership; use it sparingly.

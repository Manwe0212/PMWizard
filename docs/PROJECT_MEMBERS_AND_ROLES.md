# Project Members & Roles V0 — PR #28

The first team-management step after authenticated project creation (PR #27).

An existing PMWizard project manager with the explicit
`project:manage_members` permission can **grant, change and revoke
project-scoped access for existing accounts in the same tenant**. Membership
changes are immediately reflected by the backend's per-request database
membership checks. There is no public signup, bulk directory discovery,
email invitation, or global tenant administrator implied by these endpoints.

## Available role templates

| Role | Permissions | Intended use |
| --- | --- | --- |
| `viewer` | `project:read` | Read-only project access |
| `reviewer` | `project:read`, `project:review` | Human review of AI proposals |
| `project_manager` | `project:read`, `project:review`, `project:manage_members` | Manage this project's member list |

**Important:** In the current MVP, `project:review` also gates some\noperational actions (including certain source-connection configuration and\nautomation endpoints). Therefore the Reviewer preset has broader powers than\nreviewing AI suggestions alone. Treat it as a privileged project role until\nfiner-grained operational permissions are introduced.\n\nThese are strictly controlled server-side presets. Client-supplied permission
arrays and tenant IDs are rejected. Membership management cannot create
source credentials, enable cross-tenant access or assign tenant-wide powers.

Newly created project owners (PR #27) and **newly seeded demo accounts**
(PR #25) receive `project:manage_members` from PR #28 onwards. Existing
manager memberships are **not silently escalated**. A trusted operator must
explicitly grant the new permission through their controlled provisioning
process for an existing project. Restarting/reseeding the demo does not alter
existing membership values; this is deliberate to preserve idempotency.

## API

All endpoints require Bearer authentication, a membership in the specified
project and `project:manage_members`. Trusted-header development mode is
**not** permitted for membership management.

```text
GET    /v1/projects/{project_id}/members?limit=50&offset=0
POST   /v1/projects/{project_id}/members
PATCH  /v1/projects/{project_id}/members/{member_id}
DELETE /v1/projects/{project_id}/members/{member_id}
```

Add by exact account email and a fixed role:

```json
{
  "email": "teammate@example.com",
  "role": "reviewer"
}
```

A user must already exist and be **active** in the same tenant. A 404
means the account was not eligible for this workspace. Duplicate membership
returns 409. The API will not enumerate tenant users or create accounts.

Change role:

```json
{ "role": "viewer" }
```

Delete returns HTTP 204 and revokes membership; subsequent project requests
using an existing JWT are no longer authorized because the API checks current
membership on **every request**. It does not rely on stale role claims in
tokens.

List results are ordered and bounded (1–100 per page; default 50), include
`next_offset`, and return email/name **only to authorized member managers**.
The `is_owner` property identifies the protected original project owner
for UI controls. There is no arbitrary user-directory endpoint.

## Workflow in the web UI

On a project where your account has `project:manage_members`, select
**Members & Roles** from the left navigation. Add an existing user's email
and choose Viewer, Reviewer or Project Manager. The member list supports
pagination, role changes and confirmed removals.

The Next.js BFF routes `/api/members` and `/api/members/{memberId}`
derive the selected project and signed token from the HttpOnly session; the
browser cannot submit a project ID. State-changing BFF routes enforce
same-origin checks and limit request payload size. The backend independently
enforces each permission and tenant boundary.

## Governance and audit safeguards

- Every add, role change and removal produces an `AuditLogORM` record with
  actor, project, member ID and role transition. No passwords, access tokens,
  account emails or credential values are copied into the audit payload.
- The membership write and its audit entry are in the **same transaction**.
  An audit failure rolls back the membership change.
- The original project owner (stored in `project_manager_id`) cannot be
  demoted or removed through these endpoints. Managers also cannot modify
  or remove their **own** membership. This prevents accidental owner lockout.
  An owner handover/reassignment workflow is left for a later PR.
- This policy intentionally allows an authorized manager to assign another
  project manager on the same project, who can then manage membership. It is
  not a tenant administrator role.
- Existing accounts with custom legacy roles/permission arrays are not
  rewritten automatically. Selecting a template during an explicit role
  update replaces the target member's permissions with that template.
- Read-only project members and human reviewers cannot inspect the full
  member list or update membership. Users from another tenant, inactive
  accounts, and nonmembers do not gain access.
- Membership changes are picked up on the next API request without issuing
  a new access token. A browser may need to reload its project selector to
  reflect removals.

## Verification

```bash
pytest -q tests/test_project_members.py tests/test_project_onboarding.py tests/test_local_demo.py
pytest -q
```

CI also runs Python 3.11/3.12, Next.js lint/build and a full Docker demo
smoke test. No new database tables or schema migration are required.

## Verified email delivery (PR #30)

Managers can now send a new-user invitation directly to the specified
email address when HTTPS + verified SMTP delivery are configured. The
recipient's mailbox is marked verified on successful link redemption.
Manual links remain unverified; strict email-only deployments can disable
manual issuance and acceptance. See
[`VERIFIED_EMAIL_INVITATIONS.md`](VERIFIED_EMAIL_INVITATIONS.md).

## Invitation-only new-account onboarding (PR #29)

If the intended colleague does not yet have an account in the tenant, use
the **New-user invitations** section in Members & Roles. The one-time
link permits creation of the named account and a project membership with
the selected role; it must be shared manually and does not verify mailbox
ownership. See [`PROJECT_INVITATIONS.md`](PROJECT_INVITATIONS.md).

## Not yet production-ready

Full tenant-wide administrator roles, user invitations, secure account
registration, password recovery, organization-wide policies, team ownership
transfers, SCIM/SSO, multi-stage approval, and enterprise compliance controls
remain future milestones. Deploying for actual external customers requires
production-grade infrastructure, identity governance and access reviews
separate from this MVP.

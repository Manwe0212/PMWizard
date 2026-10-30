# Authenticated Project Onboarding V0 — PR #27

This PR lets an **existing authenticated PMWizard user** create a new,
initially empty project in **their own tenant**, then open it directly
in the UI. It replaces the need to add every new project with an operator seed
or SQL command. This does not add tenant creation, public signup or invitation
workflows.

## User experience

After logging in, select **+ New project** from the project picker or the
current project workspace. Supply a required project name (3–120 characters)
and optionally its description, objective, methodology and dates.

On successful creation PMWizard:
1. Saves the project within the user's authenticated tenant.
2. Assigns the creator as its project manager.
3. Grants **only** `project:read` and `project:review` permissions on the
   new project (not on other projects, and not on all tenant projects).
4. Adds a `project_created` audit record visible in Activity Timeline.
5. Switches the browser to the newly created project after membership
   validation, and refreshes the project picker.

Fresh projects have `status=planning`, `lifecycle_phase=initiation`.
Health may report insufficient data until real Action Items, sources and
decisions are added; PMWizard never invents activity for new projects.

## API

```http
POST /v1/projects
Authorization: Bearer <valid-user-access-token>
Content-Type: application/json

{
  "name": "Customer Enablement Launch",
  "description": "Customer onboarding improvements",
  "objective": "Reduce handoff delays",
  "methodology": "hybrid",
  "start_date": "2026-11-01",
  "planned_end_date": "2027-01-31"
}
```

Returns `201 Created`, using the existing `ProjectAccess` response:

```json
{
  "project_id": "<uuid>",
  "name": "Customer Enablement Launch",
  "status": "planning",
  "role": "project_manager",
  "permissions": ["project:read", "project:review"]
}
```

All fields besides `name` are optional. Strings are length-limited and
trimmed; `methodology` is one of `agile`, `waterfall`, `hybrid`, `other`.
When both dates are provided, the planned end cannot precede the start.

The server **rejects unknown keys**. The caller cannot set `tenant_id`,
`project_manager_id`, `status`, `role`, `permissions`, source credentials
or evidence. The tenant and creator are derived from the authenticated token
and validated against an active user in the tenant.

Trusted `X-PMWizard-*` development headers **cannot** create projects,
even if trusted-header mode is enabled. Only Bearer authentication is allowed.
Unauthorized callers receive 401 or 403, and invalid fields return 422.

The Next.js BFF `POST /api/projects` reads the session token from an
HTTP-only cookie, never accepts an arbitrary tenant ID, checks cross-origin
requests and JSON shape, limits the request size, forwards only to the
backend and suppresses internal backend diagnostic details.

## Transaction guarantees

The project, membership and the project-created audit log are committed in
**one database transaction**. Failures roll back all three records, leaving
no orphaned projects or default-open access.

The browser separately requests normal, existing project selection, which
revalidates membership. A network failure after successful creation can
leave the project created but not yet selected; the project can be selected
from the picker after reloading. In V0, POST is **not idempotent** and
retries after uncertain network failures should check the list first.

## Tests

```bash
pytest -q tests/test_project_onboarding.py
pytest -q
```

Included cases:
- Signed-in user with zero previous projects can create a project
- Project fields persist and the new project is accessible by its creator
- Only the creator gains membership; other users/tenants cannot discover it
- Audit history records a creator-attributed `project_created` entry
- Invalid date/name values and client-supplied privilege fields are rejected
- Unauthenticated calls and trusted-header impersonation are rejected
- Forced membership failures roll back the project and audit atomically

CI uses Python 3.11/3.12, Next.js lint/build and the Docker demo smoke test.

## Remaining work toward shared/team projects

This V0 assumes users already have accounts bootstrapped by an operator.
It does not invite colleagues, manage enterprise SSO, delegate membership
administration, implement tenant-wide roles, or onboard external sources.
Those require separate access governance before multi-user rollout.

Because project creation is available to any active authenticated user in
their existing tenant, organizations requiring centrally approved creation
should put additional tenant-level policy controls in place before allowing
end users onto a production installation. This is an authenticated MVP,
not a complete production administration or compliance model.

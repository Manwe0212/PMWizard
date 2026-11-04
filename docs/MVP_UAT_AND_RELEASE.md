# PMWizard MVP — PR #33 UAT & Release Candidate

**Scope:** PMWizard Project Memory + Action/Decision Intelligence with human
review, governed Project Inbox, project/portfolio dashboards, activity/audit,
roles, project onboarding and invitation-only access. These are candidate
features, not a claim of a public production launch.

**Candidate designation:** `v0.1.0-rc.1` (PROPOSED; no release tag is created
by this PR, and no external customer rollout is authorized).

## What CI actually demonstrates

CI starts the dedicated **local synthetic Docker demo**, with PostgreSQL
migrations and Next.js, then executes 18 real HTTP flows against the
running browser backend-for-frontend and Python API. This is **API+BFF
integration acceptance**, not an automated cross-browser graphical UI test.
The suite uses only generated demo credentials and fictional data, and
records a sanitized JSON artifact. It changes the ephemeral demo database
(including rejecting one synthetic suggestion), then Docker removes the
containers and disposable volume.

| ID | Acceptance criterion |
| --- | --- |
| UAT-01 | API health and Next.js respond successfully |
| UAT-02 | Anonymous session/member access and bad login fail |
| UAT-03 | Web login uses HttpOnly SameSite session; JWT not returned to JS |
| UAT-04 | Project picker selects existing project; memory and health accessible |
| UAT-05 | AI suggestion has traceable evidence and governed action target |
| UAT-06 | Human rejection persists without applying unapproved status change |
| UAT-07 | Audit export is non-cacheable and SHA-256 checksum matches payload |
| UAT-08 | A new project creates a manager-scoped membership |
| UAT-09 | Manual one-time invite created; secret absent from listing |
| UAT-10 | New user activates via web and enters invited project |
| UAT-11 | Replay of consumed invitation is rejected |
| UAT-12 | Viewer reads project but cannot manage members or export audit |
| UAT-13 | Explicit promotion grants reviewer permissions on next request |
| UAT-14 | Explicit demotion removes reviewer permissions on next request |
| UAT-15 | Original owner membership cannot be removed |
| UAT-16 | Revoked viewer immediately loses project access |
| UAT-17 | Revoked user cannot reselect the restricted project |
| UAT-18 | Owner sign-out-all removes access to browser session |

Evidence is the CI artifact `pmwizard-synthetic-uat-<run_id>` containing
`reports/uat/automated.json`. It records test IDs, outcome and CI commit
only; **no tokens, passwords, email addresses, project/user IDs, raw API
responses or evidence excerpts**.

CI validates that all 18 automated checks pass and that the report's
manual status is **not_executed** and release decision is
**no_go_pending_manual_approval**. CI cannot mark human UAT complete.

## Mandatory manual UAT on private synthetic-data staging

Run against a real but isolated staging installation configured according to
[`SECURITY_DEPLOYMENT_READINESS.md`](SECURITY_DEPLOYMENT_READINESS.md).
The UAT environment must have a trusted TLS reverse proxy, test-only SMTP
inboxes, a sandbox Microsoft Graph account and **no customer data**.

| ID | Manual scenario and concrete evidence expected |
| --- | --- |
| MAN-01 | DNS, HTTPS certificate, blocked direct API/DB access; firewall and proxy checks |
| MAN-02 | Chrome/Edge and mobile viewport login, project navigation, error states, accessibility basics |
| MAN-03 | Email invitation actually received, expired/revoked link refused, email verified after acceptance |
| MAN-04 | Real SMTP password reset receipt, wrong/expired link handling, previous sessions invalidated |
| MAN-05 | UI inspection of evidence/AI rationale; accept/edit/reject/defer user flows; independent truth verification |
| MAN-06 | Sandbox Outlook/SharePoint connector authorization, secret handling and failure/retry paths |
| MAN-07 | Viewer/reviewer/manager permission matrix, cross-tenant denial, revocation and audit export |
| MAN-08 | AI model grounding, hallucination/unsafe suggestion cases, human accountability, cost/latency |
| MAN-09 | Staging backup + tested restore, migration rollback/forward and recovery point verification |
| MAN-10 | Monitoring, abuse alert, incident tabletop, log scrubbing and operational ownership |

Each manual case must be **passed** and link to its actual verification
record (GitHub issue, review or approved internal evidence URL). Do not
invent screenshots, success rates or approvals. A real signed-off UAT
record must be prepared separately from the repository template.

## Release criteria — all mandatory

1. All PR #33 required CI jobs green **at the current head commit**,
   including Python 3.11/3.12, Next.js lint/build, staging isolation,
   Docker smoke and all 18 synthetic UAT checks.
2. A private staging environment actually exists, no leaked secrets or
   exposed API/DB ports, with HTTPS, controlled email and access logging.
3. All ten MAN-01..MAN-10 scenarios completed and evidence-linked on the
   tested revision. Critical/high-severity defects = **0 unresolved**.
4. Threat review and known limitations acknowledged, and a documented
   incident response plus rollback/backup restore plan accepted.
5. Product owner and technical owner each approve independently, in the
   protected GitHub PR/release process, with linkable evidence.
6. Final manual UAT record must contain exact tested commit SHA, reference
   a risk register, a GO decision, no blockers, and two distinct owner
   roles. The release gate script checks the structure, but **cannot
   authenticate the identity of reviewers**; use repository branch
   protection and organizational approval as the authority.

### Test/release commands

Run the Docker synthetic test locally **only with disposable demo data**:

```bash
python scripts/init_demo_env.py
docker compose --env-file .env.demo -f compose.demo.yml up --build -d --wait
python scripts/smoke_demo_stack.py
python scripts/uat_demo_stack.py --output reports/uat/automated.json
python scripts/evaluate_mvp_release.py --automated reports/uat/automated.json --automated-only
docker compose --env-file .env.demo -f compose.demo.yml down --volumes
```

The `--automated-only` flag means **CI evidence passed** only. It is
intentionally NOT permission to deploy.

A private pilot GO requires an independently completed
`manual-uat.json` record (see `docs/templates/mvp_manual_uat.template.json`,
which ships with **pending** statuses and blank proof links):

```bash
python scripts/evaluate_mvp_release.py \
  --automated reports/uat/automated.json \
  --manual /secure/path/manual-uat.json
```

The script fails unless all mandatory automated and manual evidence is
consistent; even a GO permits **a private, synthetic-data pilot only**,
not unrestricted production deployment.

## Defect triage and versioning

- **P0 blocker:** credential leakage, account takeover, unauthorized
  cross-tenant access, lost project records or unreviewed AI changes.
  Halt pilot; remediate and rerun UAT.
- **P1 high:** broken core onboarding/project/review flow, unrecoverable
  backup, failure of email ownership/expiry/revocation, missing audit.
  Halt pilot.
- **P2 medium:** degraded secondary workflow with a documented workaround;
  product and technical owners must explicitly accept in risk register.
- **P3 low:** cosmetic issue; may be scheduled for a later sprint with owner.

Every issue must include a reproducible path, expected vs actual behavior,
severity, owner, fix PR, regression test and re-test evidence. Record
issues in GitHub (or approved issue tracker) and link them in the manual
UAT record. This PR does **not** create fake defect closures.

Proposed GitHub tag **after** manual GO: `v0.1.0-rc.1`, or a later
candidate if fixes were needed. Publishing tags, deploying staging,
contacting users and approving release are explicitly manual steps.

## Known limitations, not waived by CI

- No public load testing, real SMTP delivery, real browser/device
  accessibility study, Microsoft Graph sandbox validation or penetration
  test was performed by the synthetic CI.
- Some operations remain gated behind broad `project:review`
  permissions, rather than dedicated granular permissions.
- No validated commercial multi-tenant compliance, MFA/SSO, WAF,
  credential stuffing resistance or complete data retention policy.
- No production deployment, domain, verified email sender,
  business continuity or customer support process is provisioned.
- No evidence that end users find AI suggestions accurate or valuable
  until actual pilot feedback is collected and recorded.

**Current release status at PR creation:** RC code and synthetic UAT
in development. Manual UAT **pending**. Pilot GO **not authorized**.

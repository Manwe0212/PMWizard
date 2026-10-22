# Authentication + Project Selection V0

Authentication V0 replaces the fixed demo identity used by the first Project Inbox Web release.

Flow:
Email + password + workspace ID → Argon2id verification → short-lived signed token → HttpOnly web cookie → authorized ProjectMembership → selected project → Project Inbox.

## Password storage

Passwords are never stored in plaintext. V0 uses Argon2id with 19 MiB memory, 2 iterations, and parallelism 1. The encoded hash stores salt and parameters.

## Access tokens

JWT access tokens contain user ID, tenant ID, issuer, audience, issued-at, expiration, and a unique token ID. Default lifetime is 30 minutes.

Tokens deliberately do not contain project permissions. Authorization is resolved from the database on every project request.

## Project membership

A user can have different permissions in every Project. Permissions from one project never carry into another.

## API

New endpoints:
- POST /v1/auth/login
- GET /v1/auth/me
- GET /v1/projects

Existing Inbox routes now accept Bearer authentication and resolve ProjectMembership before exposing Evidence or allowing review.

## Web session

The browser does not store the JWT in localStorage. Next.js stores it in the HttpOnly, SameSite=Lax cookie pmwizard_access_token.

The selected authorized project is stored separately in pmwizard_project_id. The project-selection route validates it against /v1/projects before setting the cookie.

## Bootstrap

There is intentionally no public self-registration endpoint in V0.

Operators create the first local account with:
python -m pmwizard.auth.bootstrap

Required environment variables:
- PMWIZARD_DATABASE_URL
- PMWIZARD_AUTH_SECRET
- PMWIZARD_BOOTSTRAP_TENANT_ID
- PMWIZARD_BOOTSTRAP_EMAIL
- PMWIZARD_BOOTSTRAP_DISPLAY_NAME
- PMWIZARD_BOOTSTRAP_PASSWORD
- PMWIZARD_BOOTSTRAP_PROJECT_IDS

Optional:
- PMWIZARD_BOOTSTRAP_ROLE
- PMWIZARD_BOOTSTRAP_PERMISSIONS

Never commit bootstrap passwords or the auth secret. PMWIZARD_AUTH_SECRET must contain at least 32 characters and should come from a secrets manager in production.

## Legacy trusted headers

The earlier trusted headers remain available only when create_app(..., allow_trusted_headers=True) is explicitly enabled. create_default_app() disables them.

## Project selection

After login the Web calls /v1/projects and shows only memberships belonging to the authenticated user/tenant. Changing project remounts the Inbox client so state from one project is not reused in another.

## Deferred

OIDC/Microsoft Entra ID, refresh-token rotation, login rate limiting, password reset, MFA through an identity provider, tenant aliases, administrator membership UI, and account-revocation UX are deferred.

> Identity authenticates the person. Membership authorizes the project. Evidence permissions authorize the source.
# Project Inbox Web V0

PMWizard Web is the first browser UI for human-governed Project Intelligence.

It is a Next.js App Router application in `web/` and sits in front of the FastAPI Project Inbox API.

Flow:

```text
Browser
  ↓
Next.js BFF routes
  ↓
FastAPI Project Inbox
  ↓
ProjectMemoryService.review_suggestion()
  ↓
HumanReview + Audit + governed Project Memory
```

## Why a BFF

The FastAPI V0 expects trusted tenant/user/permission headers. The browser must not be allowed to forge them directly.

Next.js therefore proxies requests server-side. Runtime identity comes from server environment variables:

```text
PMWIZARD_API_URL
PMWIZARD_PROJECT_ID
PMWIZARD_TENANT_ID
PMWIZARD_USER_ID
PMWIZARD_PERMISSIONS
```

This is still a local/demo identity model, not production authentication. OIDC/OAuth middleware is deferred.

## UI capabilities

- review queue for pending/deferred suggestions;
- confidence and source visibility;
- current vs proposed Action Item state;
- authorized Evidence excerpts;
- source links;
- Accept;
- Edit;
- Reject;
- Defer;
- responsive desktop/mobile layout.

Edit V0 exposes status and progress summary because those are the primary Progress Intelligence fields.

## Local run

Run FastAPI first, then:

```bash
cd web
cp .env.local.example .env.local
npm install
npm run dev
```

Next.js requires Node.js 20.9 or newer; PMWizard CI uses Node 22.

Open http://localhost:3000.

## Production boundary

The current environment identity must be replaced by real authenticated session claims before exposing the UI to untrusted users.

The browser should never receive Microsoft Graph tokens or PMWizard trusted gateway credentials.

## Deferred

- OIDC/OAuth login;
- organization/project selector;
- Project Memory views;
- source administration;
- terminal-review history screen;
- batch review;
- comments and assignments;
- notifications;
- live updates;
- accessibility audit and design-system extraction.

> The UI surfaces intelligence; the API enforces governance.

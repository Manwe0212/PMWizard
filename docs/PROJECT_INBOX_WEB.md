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

Authentication + Project Selection V0 replaces fixed runtime identity. Next.js now stores the short-lived API token in an HttpOnly cookie and proxies authenticated Bearer requests server-side. Only PMWIZARD_API_URL remains in the Web environment. OIDC/OAuth remains a future identity-provider option.

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

Local password authentication is suitable for V0 development and controlled deployments. Enterprise deployments should replace it with OIDC/Entra-backed identity while preserving the same project-membership authorization boundary.

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

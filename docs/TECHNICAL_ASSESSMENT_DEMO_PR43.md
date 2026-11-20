# PR #43 — Technical Assessment Demo Reliability & Presentation Readiness

## Scope

This increment hardens **read-only local synthetic-demo** behavior. It neither
activates Railway billing resources nor adds an OpenAI API key or fabricates
a live integration.

### Recovery when read-model refresh fails

Executive Dashboard, Delivery Intelligence and Project Memory now preserve
their last successfully loaded snapshot during an explicit refresh. If that
refresh fails, the UI shows a warning explaining **the figures may be stale**,
with a Retry refresh action. It does not silently present old data as current.

- The initial load continues to show an appropriate loader or error/retry screen.
- Existing authorized data remains on screen during a repeat request.
- Refresh is disabled while loading to avoid duplicate-click requests.
- Recovery never changes Action Items, Decisions, RAID records or permissions.
- Navigating to another project still remounts the selected workspace, so a
  previous project's stale snapshot is not reused across project selection.
- A browser reload does not create a persistent offline cache: no data is
  stored outside the current UI component.

### Read-only presenter preflight

Use `scripts/check_demo_readiness.py` before screen sharing. It verifies:

| Check | Expected |
|---|---|
| Loopback Python API `/health/live` | HTTP 200 |
| Loopback Python API `/health/ready` | HTTP 200 |
| Loopback Next.js home `/` | HTTP 200 |
| Loopback Next.js unauthenticated `/api/session` | HTTP 401, non-cacheable |

The checker never authenticates, creates records, performs migrations,
touches PostgreSQL volumes, or sends requests to external services.
It prints only status outcomes; never login secrets or record contents.
It is **not** a substitute for authenticated end-to-end UAT.

## Windows presenter checklist

From PowerShell, with Docker Desktop running:

```powershell
cd C:\Users\Usuario\PMWizard
git pull origin main
docker compose --env-file .env.demo -f compose.demo.yml up -d --build --force-recreate --no-deps demo-web
docker compose --env-file .env.demo -f compose.demo.yml ps
python scripts/check_demo_readiness.py
```

If `python` is not on PATH, use `py -3` for the last command.
**Never** use `docker compose down --volumes` on the local demo.

### Live walkthrough and fallback (approx. 6 minutes)

1. Open localhost in a clean browser, sign into the private synthetic demo.
2. **Executive Dashboard**: explain 67/100 is only an example, read the live
   score rather than memorizing it; distinguish coverage from risk.
3. **Delivery Intelligence**: inspect overdue actions, blocked dependency
   and pending decision. Explain missing forecast is not a prediction.
4. **Project Memory**: open RAID / Decisions via the guided inspect buttons,
   then return to Delivery using the contextual Back action.
5. **Attention Center**: explain personal receipts vs governed project truth.
6. **Status Reports**: explain optional AI API integration honestly; no
   generation when an API provider is absent.
7. Close with architecture (Next.js, FastAPI, PostgreSQL, Docker), human
   authorization and current limits. Railway exists only as an
   **unprovisioned project**, not a running cloud deployment.

If a refresh fails **after prior success**, clearly identify the amber
stale-data warning; click Retry once after checking Docker. If initial
loads fail, use the existing retry button. If the local stack is
unavailable, use privately saved screenshots from the **same synthetic
dataset** and explicitly identify them as offline captures. Never claim
a frozen screenshot or stale snapshot is live data.

## Verification

CI includes Python 3.11 and 3.12, web lint/build, Docker demo smoke/UAT,
and staging configuration. PR #43 adds regression checks for the
read-only preflight and UI recovery contracts. These source-level UI
tests do **not** substitute for browser-interaction testing.

No deployment or billable Railway resources are created by this PR.

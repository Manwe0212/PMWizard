# PR #41 — Technical Assessment Demo Hardening

## Scope

This PR improves read-only navigation and verifies that the three main
technical-assessment read models work together in the synthetic Docker demo.
It does not add AI API usage, trigger cloud deployments, or provision
Railway services.

## Product changes

- **Delivery Intelligence** now offers an explicit Inspect in Project
  Memory action on each follow-up flag. It opens the section matching
  the record's category:
  - Overdue / blocked Action Items → Action Items
  - Blocked Dependencies, open Issues and high-impact Risks → RAID
  - Pending / proposed Decisions → Decisions
- Delivery also includes explicit links to Project Memory and
  Attention Center, without changing any governed record.
- Project Memory accepts a requested initial section when opened from
  Delivery. The navigation resets the view for a fresh read of the
  currently authorized project's memory. Project switching still
  follows the existing signed-in session and authorization rules.

**Limitation:** navigation targets a section, **not a specific row**.
The underlying record can be inspected by title in that section.
No automatic update, AI recommendation, deep-link record lookup, or
unapproved state change is introduced.

## Acceptance and CI

The existing synthetic `UAT-04-project-selection-and-memory` scenario
now also verifies the governed collections used by Delivery Intelligence
and the authenticated `/api/executive/dashboard` and `/api/attention`
read models. This preserves the established UAT step count and report
format. It is a backend/BFF contract check, not a real browser-click
test; the Next.js lint/build and manual UI check complement it.

Run the existing workflow:
```bash
# CI executes these automatically:
pytest -q
npm --prefix web run lint
npm --prefix web run build
# CI also rebuilds the disposable Docker demo and runs UAT.
```

## Suggested presentation walkthrough (synthetic Atlas Delivery)

1. **Executive Dashboard** — show grounded cross-project priorities and
   explain that metrics come from authorized records.
2. **Delivery Intelligence** — show overdue actions, blockers and
   pending decisions, including date and status limitations.
3. **Inspect in Project Memory** — use a flag's button to open its
   Action Items / RAID / Decisions section. Confirm the visible record
   and return to Delivery Intelligence with the sidebar.
4. **Attention Center** — distinguish personal acknowledgement/snooze
   from governed project truth.
5. **Project Inbox** — explain human approval, evidence and auditability.
6. **Status Reports** — show the optional-provider state accurately:
   AI generation requires separately configured API credentials.
7. **Security / Deployment** — explain private Docker demo, CI
   acceptance tests and cloud staging preparation. Do not claim that
   Railway services or public URLs have been deployed.

## Local validation after merge

On Windows:
```powershell
cd C:\Users\Usuario\PMWizard
git pull origin main
docker compose --env-file .env.demo -f compose.demo.yml up -d --build --force-recreate --no-deps demo-web
```

Then open `http://localhost:3000`, select the synthetic Atlas Delivery
project, go to Delivery Intelligence, click **Inspect in Project Memory**
on an action, dependency and decision, and confirm the expected tab
opens. Reload Delivery and verify existing governed state is unchanged.

No `down --volumes` or seed reset is necessary. **Railway remains
unprovisioned** under the owner's no-billable-resources instruction.

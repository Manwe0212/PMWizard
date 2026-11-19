# Technical Assessment — Next.js Security Stabilization (PR #35)

## Reason for change

The local PMWizard demo displayed a Next.js development Security Insight
for the pinned framework version 16.4.2. The November 3, 2026 security
release includes fixes in 16.4.5; 16.4.6 is the current stable 16.4
patch release as of November 19, 2026.

## Scope

- Pin `next` to `16.4.6` in `web/package.json`.
- Pin `eslint-config-next` to the matching `16.4.6` version.
- Keep `react`, `react-dom` and the Docker architecture unchanged.
- Do not alter authentication, Project Memory, report generation or seeded data.
- Do not add a paid API provider or credentials.

The web Dockerfile currently installs npm dependencies through
`npm install` and the repo does not have a checked-in `web/package-lock.json`.
For this narrow hotfix we retain existing dependency installation behavior.
A deterministic dependency lockfile should be considered in a separate,
tested reproducibility change, not claimed as part of this PR.

## Evidence to verify

- Web lint/build CI pass on the patch.
- Python test matrix and local Docker smoke CI pass.
- `Status Reports` still shows the optional English AI integration overview.
- `Project Health`, `Project Inbox`, `Executive Dashboard` and project
  authentication continue working.
- After merging to main, rebuild the local `demo-web` image; a Git pull
  alone does not replace the running Next.js container.

## Local update (PowerShell)

```powershell
cd C:\Users\Usuario\PMWizard
git pull origin main
docker compose --env-file .env.demo -f compose.demo.yml up -d --build --force-recreate --no-deps demo-web
docker compose --env-file .env.demo -f compose.demo.yml ps -a
```

Then open `http://localhost:3000/`, refresh the browser with
`Ctrl+Shift+R`, and manually verify the screens. Do not run
`docker compose down --volumes`, which would remove synthetic demo data.

## Boundaries

Passing build and smoke tests establishes compatibility for the covered
flows, not a comprehensive penetration test. Security patch status still
depends on the resolved transitive dependency versions and ongoing advisories.
The local development server is not intended as a public production host.

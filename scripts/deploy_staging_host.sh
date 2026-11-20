#!/usr/bin/env bash
# PR #39 — operator-controlled private staging deployment.
# NEVER targets the local demo stack or starts public networking.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
umask 077

usage() {
  cat <<'HELP'
Usage: bash scripts/deploy_staging_host.sh --check | --apply

--check  Validate host prerequisites, secret file permissions and Compose config.
--apply  Perform the same checks, then build and start the PRIVATE staging stack.
         Requires checked-out clean main, an independently verified database
         backup and explicit operator acknowledgement:
           PMWIZARD_BACKUP_VERIFIED=yes
           PMWIZARD_STAGING_ACCESS_APPROVED=yes

No public URL is created. Configure DNS, TLS Caddy reverse proxy, SMTP and
firewall separately. Run only on a trusted Linux staging host. Do not run
this deployment script on the local Windows Docker demo.
HELP
}

case "${1:---help}" in
  --help|-h) usage; exit 0;;
  --check) APPLY=false;;
  --apply) APPLY=true;;
  *) usage >&2; exit 2;;
esac
if [[ $# -ne 1 ]]; then usage >&2; exit 2; fi

fail() { printf 'STAGING PREFLIGHT FAILED: %s\n' "$1" >&2; exit 1; }
command -v docker >/dev/null || fail "Docker is not installed."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."
command -v git >/dev/null || fail "Git is not installed."
[[ -f .env.staging ]] || fail "Missing .env.staging; populate from .env.staging.example on the trusted host."
[[ -f compose.staging.yml ]] || fail "Missing compose.staging.yml."

# Linux-only permission check. File content and expanded Compose config
# must NEVER be printed to build logs because they include credentials.
if [[ "$(uname -s)" != Linux ]]; then fail "Run this on a Linux staging host."; fi
permissions="$(stat -c '%a' .env.staging)"
# Owner-read/write only, never world/group readable; 400 and 600 accepted.
case "$permissions" in
  400|600) ;;
  *) fail ".env.staging must be owner-only (chmod 600 .env.staging).";;
esac

# Compose checks reference the existing fail-closed staging-only services.
docker compose --env-file .env.staging -f compose.staging.yml config --quiet >/dev/null   || fail "Staging Compose validation failed. Inspect required values privately."
printf 'Staging Compose and credential-file checks passed.\n'

if [[ "$APPLY" == false ]]; then
  printf 'CHECK ONLY: No containers modified and no deployment attempted.\n'
  exit 0
fi

[[ "${PMWIZARD_BACKUP_VERIFIED:-}" == yes ]]   || fail "Set PMWIZARD_BACKUP_VERIFIED=yes only AFTER independently verifying an off-host backup and restore process."
[[ "${PMWIZARD_STAGING_ACCESS_APPROVED:-}" == yes ]]   || fail "Set PMWIZARD_STAGING_ACCESS_APPROVED=yes only AFTER checking host firewall/DNS/TLS access policy."
[[ "$(git branch --show-current)" == main ]]   || fail "Deployment requires a checked-out main branch."
[[ -z "$(git status --porcelain --untracked-files=no)" ]]   || fail "Tracked files have local changes. Deploy a clean, reviewed commit."

sha="$(git rev-parse --short=12 HEAD)"
printf 'Starting private staging containers from reviewed main commit %s.\n' "$sha"
docker compose --env-file .env.staging -f compose.staging.yml up -d --build --wait
docker compose --env-file .env.staging -f compose.staging.yml ps
printf 'Staging containers started; this does NOT certify Internet access, TLS, backup restoration or UAT.\n'
printf 'Next: verify Caddy, HTTPS, SMTP, restricted access, and run the anonymous cloud smoke test.\n'

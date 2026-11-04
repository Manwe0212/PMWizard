"""MVP release decision gate; automated CI success is NOT a human GO.

Synthetic Docker HTTP evidence alone can only produce AUTOMATED_READY.
To produce GO, provide a separately reviewed, evidence-linked manual UAT
record. This script checks structure and consistency; it cannot attest
authenticity of signers or replace GitHub branch-protected approvals.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

AUTOMATED_IDS = tuple(f"UAT-{i:02d}-{name}" for i, name in enumerate((
    "stack-ready",
    "anonymous-access-denied",
    "httponly-login-and-session",
    "project-selection-and-memory",
    "evidence-backed-ai-suggestion",
    "human-review-does-not-auto-apply",
    "audit-export-integrity",
    "create-project-and-owner-access",
    "one-time-invitation",
    "activate-invited-account",
    "deny-invite-replay",
    "viewer-permission-boundaries",
    "reviewer-promotion-live",
    "reviewer-demotion-live",
    "original-owner-protected",
    "revoke-project-access-immediately",
    "no-cross-session-project-selection",
    "revoke-all-owner-sessions",
), start=1))

MANUAL_IDS = (
    "MAN-01-staging-dns-https-and-access",
    "MAN-02-browser-login-project-navigation",
    "MAN-03-invitation-email-and-inbox-proof",
    "MAN-04-password-recovery-real-email",
    "MAN-05-human-review-and-evidence-ux",
    "MAN-06-connector-sandbox-authorizations",
    "MAN-07-roles-revocation-and-audit-export",
    "MAN-08-ai-guardrails-and-human-governance",
    "MAN-09-backup-restore-and-rollback",
    "MAN-10-security-monitoring-and-incident-response",
)
APPROVERS = frozenset({"product_owner", "technical_owner"})


class ReleaseGateError(ValueError):
    pass


def safe_reference(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("https://"):
        return False
    parsed = urlparse(value)
    return bool(
        parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and not parsed.query
        and parsed.path.strip("/")
    )


def validate_automated(report: dict) -> str:
    if report.get("schema_version") != "pmwizard-mvp-uat-v0":
        raise ReleaseGateError("Automated UAT schema mismatch")
    if report.get("suite") != "docker-loopback-synthetic-http":
        raise ReleaseGateError("Wrong automated suite")
    if report.get("mode") != "synthetic_demo_only":
        raise ReleaseGateError("Only synthetic Docker UAT evidence is accepted")
    sha = report.get("commit_sha")
    if not isinstance(sha, str) or not (
        re.fullmatch(r"[0-9a-f]{40}", sha) or sha == "local-uncommitted"
    ):
        raise ReleaseGateError("Automated evidence has no valid revision")
    if report.get("automated_status") != "passed":
        raise ReleaseGateError("Automated UAT is not green")
    if report.get("manual_uat_status") != "not_executed":
        raise ReleaseGateError("Automated CI cannot assert manual UAT")
    if report.get("release_decision") != "no_go_pending_manual_approval":
        raise ReleaseGateError("Automated CI cannot assert release approval")
    checks = report.get("checks")
    if not isinstance(checks, list) or len(checks) != len(AUTOMATED_IDS):
        raise ReleaseGateError("Required automated acceptance cases are missing")
    ids = [check.get("id") for check in checks if isinstance(check, dict)]
    if len(ids) != len(AUTOMATED_IDS) or set(ids) != set(AUTOMATED_IDS):
        raise ReleaseGateError("Automated acceptance case mismatch")
    if any(check.get("status") != "passed" for check in checks):
        raise ReleaseGateError("At least one automated case failed")
    return sha


def validate_manual(record: dict, *, automated_sha: str) -> None:
    if record.get("schema_version") != "pmwizard-mvp-human-uat-v0":
        raise ReleaseGateError("Manual UAT schema mismatch")
    if record.get("environment") != "private-staging-synthetic":
        raise ReleaseGateError("Wrong manual acceptance environment")
    if record.get("tested_commit_sha") != automated_sha:
        raise ReleaseGateError("Manual tests must refer to the tested revision")
    if automated_sha == "local-uncommitted":
        raise ReleaseGateError("Release cannot use uncommitted test evidence")
    if record.get("decision") != "go":
        raise ReleaseGateError("Product GO has not been approved")
    if record.get("blockers") != []:
        raise ReleaseGateError("Unresolved release blockers remain")
    if not safe_reference(record.get("risk_register_ref")):
        raise ReleaseGateError("Approved risk register evidence is missing")
    items = record.get("manual_scenarios")
    if not isinstance(items, list) or len(items) != len(MANUAL_IDS):
        raise ReleaseGateError("Manual UAT coverage is incomplete")
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    if len(ids) != len(MANUAL_IDS) or set(ids) != set(MANUAL_IDS):
        raise ReleaseGateError("Manual UAT case identifiers mismatch")
    for item in items:
        if item.get("status") != "passed" or not safe_reference(item.get("evidence_ref")):
            raise ReleaseGateError("Manual UAT case lacks PASS or linked evidence")

    approvals = record.get("approvals")
    if not isinstance(approvals, list) or len(approvals) < 2:
        raise ReleaseGateError("Two accountable owners must approve")
    roles = set()
    for item in approvals:
        if not isinstance(item, dict):
            raise ReleaseGateError("Invalid approval")
        if (
            item.get("role") not in APPROVERS
            or not isinstance(item.get("name"), str)
            or len(item["name"].strip()) < 3
            or not isinstance(item.get("approved_at_utc"), str)
            or not item["approved_at_utc"].endswith("Z")
            or not safe_reference(item.get("evidence_ref"))
        ):
            raise ReleaseGateError("Approval is missing owner, date or evidence")
        roles.add(item["role"])
    if roles != APPROVERS:
        raise ReleaseGateError("Product and technical ownership approval required")


def evaluate(automated: dict, manual: dict | None = None) -> str:
    sha = validate_automated(automated)
    if manual is None:
        return "AUTOMATED_READY_MANUAL_UAT_PENDING_NO_GO"
    validate_manual(manual, automated_sha=sha)
    return "GO_FOR_PRIVATE_PILOT_ONLY"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--automated", type=Path, required=True)
    parser.add_argument("--manual", type=Path)
    parser.add_argument(
        "--automated-only", action="store_true",
        help="CI gate: validate only the synthetic test evidence, never issue GO",
    )
    args = parser.parse_args()
    if args.automated_only and args.manual:
        parser.error("--manual and --automated-only cannot be combined")
    try:
        automated = json.loads(args.automated.read_text(encoding="utf-8"))
        manual = (
            json.loads(args.manual.read_text(encoding="utf-8"))
            if args.manual is not None else None
        )
        if not args.automated_only and manual is None:
            raise ReleaseGateError(
                "GO requires a separately completed and reviewed manual UAT record"
            )
        print(evaluate(automated, manual))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print("NO_GO: release evidence is missing, invalid or incomplete.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

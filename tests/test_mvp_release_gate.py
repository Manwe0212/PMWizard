"""Static release gate verification without fabricating human acceptance."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
gate = runpy.run_path(str(ROOT / "scripts" / "evaluate_mvp_release.py"))
auto_ids = gate["AUTOMATED_IDS"]
manual_ids = gate["MANUAL_IDS"]
evaluate = gate["evaluate"]
validate_automated = gate["validate_automated"]
validate_manual = gate["validate_manual"]
ReleaseGateError = gate["ReleaseGateError"]


def automated_report():
    return {
        "schema_version": "pmwizard-mvp-uat-v0",
        "suite": "docker-loopback-synthetic-http",
        "mode": "synthetic_demo_only",
        "commit_sha": "a" * 40,
        "executed_at_utc": "2026-11-04T12:00:00+00:00",
        "checks": [{"id": key, "status": "passed"} for key in auto_ids],
        "automated_status": "passed",
        "manual_uat_status": "not_executed",
        "release_decision": "no_go_pending_manual_approval",
    }


def manual_report():
    return {
        "schema_version": "pmwizard-mvp-human-uat-v0",
        "environment": "private-staging-synthetic",
        "tested_commit_sha": "a" * 40,
        "decision": "go",
        "blockers": [],
        "risk_register_ref": "https://github.com/example/repo/issues/101",
        "manual_scenarios": [
            {
                "id": key, "status": "passed",
                "evidence_ref": f"https://github.com/example/repo/issues/{i + 10}",
            }
            for i, key in enumerate(manual_ids)
        ],
        "approvals": [
            {
                "role": "product_owner", "name": "Example Product Owner",
                "approved_at_utc": "2026-11-04T14:00:00Z",
                "evidence_ref": "https://github.com/example/repo/pull/33",
            },
            {
                "role": "technical_owner", "name": "Example Technical Owner",
                "approved_at_utc": "2026-11-04T14:10:00Z",
                "evidence_ref": "https://github.com/example/repo/pull/33",
            },
        ],
    }


def test_passed_ci_does_not_produce_go():
    report = automated_report()
    assert validate_automated(report) == "a" * 40
    assert evaluate(report) == "AUTOMATED_READY_MANUAL_UAT_PENDING_NO_GO"


@pytest.mark.parametrize("field,value", [
    ("automated_status", "failed"),
    ("manual_uat_status", "passed"),
    ("release_decision", "go"),
    ("commit_sha", ""),
    ("mode", "production"),
    ("suite", "test-only-unit-tests"),
])
def test_automated_evidence_is_fail_closed(field, value):
    report = automated_report()
    report[field] = value
    with pytest.raises(ReleaseGateError):
        evaluate(report)


def test_missing_or_failed_acceptance_cases_reject():
    report = automated_report()
    report["checks"][3]["status"] = "failed"
    with pytest.raises(ReleaseGateError):
        evaluate(report)
    report = automated_report()
    report["checks"].pop()
    with pytest.raises(ReleaseGateError):
        evaluate(report)
    report = automated_report()
    report["checks"].append(report["checks"][0])
    with pytest.raises(ReleaseGateError):
        evaluate(report)


def test_manual_go_requires_exact_scenarios_and_both_owners():
    report = automated_report()
    manual = manual_report()
    assert evaluate(report, manual) == "GO_FOR_PRIVATE_PILOT_ONLY"
    manual["approvals"] = manual["approvals"][:1]
    with pytest.raises(ReleaseGateError, match="Two accountable"):
        evaluate(report, manual)


@pytest.mark.parametrize("mutation", [
    lambda m: m.update({"decision": "no_go"}),
    lambda m: m.update({"blockers": ["Open critical defect"]}),
    lambda m: m.update({"tested_commit_sha": "b" * 40}),
    lambda m: m.update({"environment": "public-production"}),
    lambda m: m.update({"risk_register_ref": "http://unsafe.example"}),
    lambda m: m["manual_scenarios"][0].update({"status": "pending"}),
    lambda m: m["manual_scenarios"][1].update({"evidence_ref": ""}),
    lambda m: m["approvals"][0].update({"evidence_ref": "https://example.org/?token=secret"}),
])
def test_manual_go_rejects_unsafe_or_incomplete_records(mutation):
    manual = manual_report()
    mutation(manual)
    with pytest.raises(ReleaseGateError):
        evaluate(automated_report(), manual)


def test_missing_manual_evidence_does_not_allow_cli_go(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "ci.json"
    path.write_text(json.dumps(automated_report()), encoding="utf-8")
    process = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_mvp_release.py"),
         "--automated", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert process.returncode != 0
    assert "NO_GO" in process.stderr
    ci = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate_mvp_release.py"),
         "--automated", str(path), "--automated-only"],
        capture_output=True, text=True, check=False,
    )
    assert ci.returncode == 0
    assert "PENDING_NO_GO" in ci.stdout


def test_manual_go_cannot_use_uncommitted_automated_evidence():
    automated = automated_report()
    automated["commit_sha"] = "local-uncommitted"
    manual = manual_report()
    manual["tested_commit_sha"] = "local-uncommitted"
    with pytest.raises(ReleaseGateError, match="uncommitted"):
        evaluate(automated, manual)

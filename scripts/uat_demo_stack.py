"""Synthetic end-to-end MVP acceptance against the private Docker demo stack.

Exercises actual Next.js BFF and PostgreSQL-backed API over loopback HTTP.
The report intentionally contains NO account emails, user/project IDs,
passwords, JWTs, invitation tokens, or raw API response bodies.

Usage:
    docker compose --env-file .env.demo -f compose.demo.yml up --build -d --wait
    python scripts/uat_demo_stack.py --output reports/uat/automated.json
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:3000"
TENANT = "269ba0ba-35e4-4e86-bd2e-7d43f09d2550"


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: object
    raw: bytes

    def json(self) -> dict:
        data = json.loads(self.raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise AssertionError("Expected JSON object response")
        return data


class LocalClient:
    def __init__(self, *, base: str) -> None:
        if base not in {API, WEB}:
            raise ValueError("UAT only permits the loopback demo services")
        self.base = base
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(
        self, path: str, *, method: str = "GET",
        body: dict | None = None,
    ) -> HttpResult:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("UAT path must remain local")
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if method not in {"GET", "HEAD"}:
            headers["Origin"] = self.base
        req = Request(self.base + path, data=data, method=method, headers=headers)
        try:
            response = self.opener.open(req, timeout=40)
        except HTTPError as error:
            response = error
        with response:
            # Never print raw bodies; these can contain tokens and PII.
            return HttpResult(response.status, response.headers, response.read())


def assert_status(result: HttpResult, expected: int) -> None:
    if result.status != expected:
        raise AssertionError(f"HTTP status {result.status}, expected {expected}")


def demo_password() -> str:
    path = ROOT / ".env.demo"
    if not path.is_file():
        raise RuntimeError("Synthetic demo credentials unavailable")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("PMWIZARD_DEMO_PASSWORD="):
            password = line.partition("=")[2]
            if len(password) >= 12:
                return password
    raise RuntimeError("Synthetic demo password unavailable")


def run_suite(checks: list[dict[str, str]]) -> None:
    api, owner, viewer, attacker = (
        LocalClient(base=API),
        LocalClient(base=WEB),
        LocalClient(base=WEB),
        LocalClient(base=WEB),
    )

    def step(label: str, callback) -> None:
        try:
            callback()
            checks.append({"id": label, "status": "passed"})
            print(f"PASS {label}", flush=True)
        except Exception as error:
            # Error bodies are intentionally excluded. Never expose test data.
            checks.append({"id": label, "status": "failed"})
            # Safe diagnostics: only HTTP status codes, never raw responses.
            message = str(error)
            reason = (
                message
                if isinstance(error, AssertionError)
                and message.startswith("HTTP status ")
                and len(message) < 65
                else type(error).__name__
            )
            print(f"FAIL {label}: {reason}", flush=True)
            raise

    def service_health() -> None:
        assert_status(api.request("/health/live"), 200)
        assert_status(api.request("/health/ready"), 200)
        assert_status(owner.request("/"), 200)

    step("UAT-01-stack-ready", service_health)

    def anonymous_denied() -> None:
        assert_status(attacker.request("/api/session"), 401)
        assert_status(attacker.request("/api/members"), 401)
        wrong = owner.request("/api/auth/login", method="POST", body={
            "tenant_id": TENANT, "email": "demo@example.com",
            "password": "incorrect synthetic password",
        })
        assert_status(wrong, 401)

    step("UAT-02-anonymous-access-denied", anonymous_denied)

    def owner_login() -> None:
        response = owner.request("/api/auth/login", method="POST", body={
            "tenant_id": TENANT,
            "email": "demo@example.com",
            "password": demo_password(),
        })
        assert_status(response, 200)
        if "access_token" in response.json():
            raise AssertionError("BFF must not return JWT to browser JS")
        cookies = " ".join(response.headers.get_all("Set-Cookie") or [])
        if "httponly" not in cookies.lower() or "samesite=lax" not in cookies.lower():
            raise AssertionError("Auth cookie must be HttpOnly and SameSite")
        session = owner.request("/api/session")
        assert_status(session, 200)
        data = session.json()
        if len(data["projects"]) != 1:
            raise AssertionError("Expected one seeded synthetic project")

    step("UAT-03-httponly-login-and-session", owner_login)

    seeded_id = owner.request("/api/session").json()["projects"][0]["project_id"]

    def select_seeded() -> None:
        response = owner.request("/api/project-selection", method="POST", body={
            "project_id": seeded_id,
        })
        assert_status(response, 200)
        session = owner.request("/api/session").json()
        if session["selected_project_id"] != seeded_id:
            raise AssertionError("Project picker did not persist")
        assert_status(owner.request("/api/memory"), 200)
        assert_status(owner.request("/api/health"), 200)

    step("UAT-04-project-selection-and-memory", select_seeded)

    suggestion_id: str | None = None
    original_action_status: str | None = None

    def inspect_suggestion() -> None:
        nonlocal suggestion_id, original_action_status
        response = owner.request("/api/inbox")
        assert_status(response, 200)
        items = response.json()["items"]
        pending = next((x for x in items if x["review_status"] == "pending"), None)
        if not pending:
            raise AssertionError("Synthetic pending AI suggestion not available")
        suggestion_id = pending["id"]
        detail = owner.request(f"/api/inbox/{suggestion_id}")
        assert_status(detail, 200)
        content = detail.json()
        if not content["evidence"]:
            raise AssertionError("Review lacks traceable evidence")
        action = content.get("target_action_item")
        if not action:
            raise AssertionError("Review lacks governed target entity")
        original_action_status = action["status"]

    step("UAT-05-evidence-backed-ai-suggestion", inspect_suggestion)

    def review_human() -> None:
        assert suggestion_id is not None
        response = owner.request(
            f"/api/inbox/{suggestion_id}/review",
            method="POST",
            body={
                "status": "rejected",
                "reviewer_note": "Synthetic UAT rejection: preserve governed state.",
            },
        )
        assert_status(response, 200)
        if response.json()["review_status"] != "rejected":
            raise AssertionError("Human review transition not persisted")
        detail = owner.request(f"/api/inbox/{suggestion_id}")
        assert_status(detail, 200)
        if detail.json()["target_action_item"]["status"] != original_action_status:
            raise AssertionError("Rejected AI proposal changed project truth")
        activity = owner.request("/api/activity")
        assert_status(activity, 200)
        if activity.json()["count"] < 1:
            raise AssertionError("Missing governed activity trace")

    step("UAT-06-human-review-does-not-auto-apply", review_human)

    def audited_export() -> None:
        response = owner.request("/api/activity/export?format=json")
        assert_status(response, 200)
        digest = response.headers.get("X-PMWizard-Export-SHA256")
        if digest != hashlib.sha256(response.raw).hexdigest():
            raise AssertionError("Activity export hash mismatch")
        if "no-store" not in response.headers.get("Cache-Control", ""):
            raise AssertionError("Audit export cannot be cached")
        report = response.json()
        if report["row_count"] < 1:
            raise AssertionError("Audit export unexpectedly empty")

    step("UAT-07-audit-export-integrity", audited_export)

    created_id: str | None = None

    def create_project() -> None:
        nonlocal created_id
        response = owner.request("/api/projects", method="POST", body={
            "name": "UAT Sandbox " + secrets.token_hex(4),
            "description": "Synthetic E2E acceptance; no customer data.",
        })
        assert_status(response, 201)
        project = response.json()
        created_id = project["project_id"]
        if "project:manage_members" not in project["permissions"]:
            raise AssertionError("Project creator lacks scoped manager access")
        picker = owner.request("/api/project-selection", method="POST", body={
            "project_id": created_id,
        })
        assert_status(picker, 200)
        assert_status(owner.request("/api/members"), 200)

    step("UAT-08-create-project-and-owner-access", create_project)

    invitation_token: str | None = None
    synthetic_email = f"uat-{secrets.token_hex(8)}@example.com"
    synthetic_password = secrets.token_urlsafe(24)

    def invite_viewer() -> None:
        nonlocal invitation_token
        response = owner.request("/api/invitations", method="POST", body={
            "email": synthetic_email,
            "role": "viewer",
            "delivery_method": "manual",
        })
        assert_status(response, 201)
        invitation_token = response.json().get("token")
        if not invitation_token:
            raise AssertionError("Local demo must produce one-time manual invite")
        listing = owner.request("/api/invitations")
        assert_status(listing, 200)
        if invitation_token.encode() in listing.raw:
            raise AssertionError("Invitation secret leaked in listing")
        if "no-store" not in response.headers.get("Cache-Control", ""):
            raise AssertionError("Invitations response cannot be cached")

    step("UAT-09-one-time-invitation", invite_viewer)

    viewer_id: str | None = None

    def viewer_activation() -> None:
        nonlocal viewer_id
        assert invitation_token is not None
        result = viewer.request("/api/invitations/accept", method="POST", body={
            "token": invitation_token,
            "display_name": "Synthetic UAT Viewer",
            "password": synthetic_password,
        })
        assert_status(result, 200)
        if "access_token" in result.json():
            raise AssertionError("BFF exposed JWT after account onboarding")
        session = viewer.request("/api/session")
        assert_status(session, 200)
        viewer_id = session.json()["user"]["id"]
        if session.json()["selected_project_id"] != created_id:
            raise AssertionError("Invitation did not select intended project")

    step("UAT-10-activate-invited-account", viewer_activation)

    def block_invitation_replay() -> None:
        assert invitation_token is not None
        retry = attacker.request("/api/invitations/accept", method="POST", body={
            "token": invitation_token, "display_name": "Replay",
            "password": secrets.token_urlsafe(24),
        })
        assert_status(retry, 400)

    step("UAT-11-deny-invite-replay", block_invitation_replay)

    def viewer_least_privilege() -> None:
        assert_status(viewer.request("/api/memory"), 200)
        assert_status(viewer.request("/api/activity"), 200)
        assert_status(viewer.request("/api/members"), 403)
        assert_status(viewer.request("/api/invitations"), 403)
        assert_status(viewer.request("/api/activity/export?format=json"), 403)

    step("UAT-12-viewer-permission-boundaries", viewer_least_privilege)

    def promotion_applies_live() -> None:
        assert viewer_id is not None
        res = owner.request(f"/api/members/{viewer_id}", method="PATCH", body={
            "role": "reviewer",
        })
        assert_status(res, 200)
        assert_status(viewer.request("/api/activity/export?format=json"), 200)

    step("UAT-13-reviewer-promotion-live", promotion_applies_live)

    def demotion_applies_live() -> None:
        assert viewer_id is not None
        res = owner.request(f"/api/members/{viewer_id}", method="PATCH", body={
            "role": "viewer",
        })
        assert_status(res, 200)
        assert_status(viewer.request("/api/activity/export?format=json"), 403)

    step("UAT-14-reviewer-demotion-live", demotion_applies_live)

    def prevent_owner_lockout() -> None:
        owner_id = owner.request("/api/session").json()["user"]["id"]
        assert_status(owner.request(f"/api/members/{owner_id}", method="DELETE"), 409)

    step("UAT-15-original-owner-protected", prevent_owner_lockout)

    def revoke_viewer() -> None:
        assert viewer_id is not None
        res = owner.request(f"/api/members/{viewer_id}", method="DELETE")
        assert_status(res, 204)
        assert_status(viewer.request("/api/memory"), 404)
        session = viewer.request("/api/session")
        assert_status(session, 200)
        if session.json()["selected_project_id"] is not None:
            raise AssertionError("Revoked project remains selected")

    step("UAT-16-revoke-project-access-immediately", revoke_viewer)

    def deny_project_enumeration() -> None:
        assert created_id is not None
        attempt = viewer.request("/api/project-selection", method="POST", body={
            "project_id": created_id,
        })
        assert_status(attempt, 404)
        assert_status(attacker.request("/api/session"), 401)

    step("UAT-17-no-cross-session-project-selection", deny_project_enumeration)

    def owner_logout() -> None:
        res = owner.request("/api/auth/logout-all", method="POST")
        assert_status(res, 200)
        assert_status(owner.request("/api/session"), 401)

    step("UAT-18-revoke-all-owner-sessions", owner_logout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default="reports/uat/automated.json",
        help="Synthetic-only, sanitized UAT report path",
    )
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT):
        raise SystemExit("UAT evidence must be written inside this repository")

    report = {
        "schema_version": "pmwizard-mvp-uat-v0",
        "suite": "docker-loopback-synthetic-http",
        "mode": "synthetic_demo_only",
        "commit_sha": os.environ.get("GITHUB_SHA") or "local-uncommitted",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": [],
        "automated_status": "failed",
        "manual_uat_status": "not_executed",
        "release_decision": "no_go_pending_manual_approval",
    }
    checks: list[dict[str, str]] = []
    try:
        run_suite(checks)
        report["checks"] = checks
        report["automated_status"] = "passed"
        result = 0
    except Exception:
        # Preserve passed steps and the failing step, without sensitive responses.
        report["checks"] = checks or [{"id": "UAT-bootstrap", "status": "failed"}]
        result = 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result:
        print("Synthetic UAT failed. See CI job diagnostics and redacted report.", flush=True)
    else:
        print("Synthetic automated UAT passed; manual UAT and release approval remain PENDING.", flush=True)
    return result


if __name__ == "__main__":
    sys.exit(main())

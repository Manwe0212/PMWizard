"""Smoke test the explicitly selected Docker demo stack.

Requires: docker compose --env-file .env.demo -f compose.demo.yml up --build -d --wait
Python standard library only. Never print secrets or access tokens.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:3000"
TENANT_ID = "269ba0ba-35e4-4e86-bd2e-7d43f09d2550"


def read_demo_password() -> str:
    path = ROOT / ".env.demo"
    if not path.is_file():
        raise RuntimeError("Missing private .env.demo: initialize the demo environment first")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("PMWIZARD_DEMO_PASSWORD="):
            password = line.partition("=")[2].strip()
            if password:
                return password
    raise RuntimeError("Missing PMWIZARD_DEMO_PASSWORD in .env.demo")


def get_json(path: str, *, token: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with urlopen(Request(API + path, headers=headers), timeout=30) as response:
        return json.loads(response.read())


def main() -> None:
    assert get_json("/health/live") == {"status": "ok"}
    assert get_json("/health/ready") == {"status": "ok"}
    with urlopen(WEB, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError("Web UI did not respond successfully")

    data = json.dumps({
        "tenant_id": TENANT_ID,
        "email": "demo@example.com",
        "password": read_demo_password(),
    }).encode()
    with urlopen(
        Request(
            API + "/v1/auth/login", data=data, method="POST",
            headers={"Content-Type": "application/json"},
        ),
        timeout=30,
    ) as response:
        token = json.loads(response.read())["access_token"]

    projects = get_json("/v1/projects", token=token)
    if projects["count"] != 1:
        raise RuntimeError("Expected one synthetic demo project")
    project_id = projects["items"][0]["project_id"]
    inbox = get_json(f"/v1/projects/{project_id}/inbox", token=token)
    if inbox["count"] < 1:
        raise RuntimeError("Expected one reviewable synthetic suggestion")
    activity = get_json(f"/v1/projects/{project_id}/activity", token=token)
    if activity["count"] < 1:
        raise RuntimeError("Expected a synthetic activity event")

    print("Local demo stack smoke test passed.")
    print("Verified: DB migrations, API readiness, web, login, projects, inbox, activity.")
    print("No real customer data or external connectors were used.")


if __name__ == "__main__":
    main()

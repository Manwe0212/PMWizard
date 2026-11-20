"""PR #43 — read-only pre-demo availability check for the local Docker stack.

No credentials, user IDs or project data are printed or requested.
This does not mutate data, run migrations or recreate containers.
Only loopback endpoints are contacted.
"""

from __future__ import annotations

import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


CHECKS = (
    ("API live", "http://127.0.0.1:8000/health/live", 200),
    ("API ready", "http://127.0.0.1:8000/health/ready", 200),
    ("Web UI", "http://127.0.0.1:3000/", 200),
    ("Anonymous session rejected", "http://127.0.0.1:3000/api/session", 401),
)


def run_check(opener, name: str, url: str, expected: int) -> tuple[bool, str]:
    request = Request(url, headers={"Accept": "application/json, text/html"})
    try:
        response = opener.open(request, timeout=8)
    except HTTPError as exc:
        response = exc
    except (URLError, TimeoutError, OSError) as exc:
        return False, f"{name}: unavailable ({type(exc).__name__})"
    with response:
        if response.status != expected:
            return False, f"{name}: HTTP {response.status}, expected {expected}"
        if name == "Anonymous session rejected":
            cache = response.headers.get("Cache-Control", "").lower()
            if "no-store" not in cache:
                return False, f"{name}: Cache-Control must prevent storage"
        return True, f"{name}: HTTP {expected}"


def main() -> int:
    opener = build_opener(NoRedirect())
    failed = 0
    for name, url, expected in CHECKS:
        ok, message = run_check(opener, name, url, expected)
        print(("PASS " if ok else "FAIL ") + message, file=sys.stdout if ok else sys.stderr)
        failed += not ok
    if failed:
        print("Demo is not ready. Check Docker Desktop, containers and local ports.", file=sys.stderr)
        return 1
    print("Local availability checks passed (does not replace authenticated UAT).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

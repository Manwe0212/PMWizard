"""Non-destructive, anonymous HTTPS smoke checks for a private staging URL.

Only run against a PMWizard endpoint that you administer. Does not log in,
send credentials, mutate data or require an OpenAI API key.
"""

from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validated_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Supply a canonical non-local HTTPS origin, without paths or credentials.")
    return origin.rstrip("/")


def check_headers(headers) -> list[str]:
    failures = []
    for name in ("x-content-type-options", "x-frame-options", "strict-transport-security"):
        if not headers.get(name):
            failures.append(f"Missing required response header: {name}")
    if "frame-ancestors" not in headers.get("content-security-policy", ""):
        failures.append("Missing frame-ancestors CSP")
    return failures


def run_checks(origin: str, timeout: float = 10.0) -> list[str]:
    failures = []
    opener = build_opener(NoRedirect())
    for path, expected in (("/", 200), ("/api/session", 401)):
        request = Request(origin + path, headers={"Accept": "text/html, application/json"})
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        except (URLError, TimeoutError, OSError) as exc:
            failures.append(f"{path}: HTTPS connection failed ({type(exc).__name__})")
            continue
        with response:
            if response.status != expected:
                failures.append(f"{path}: expected HTTP {expected}, got {response.status}")
            failures.extend(f"{path}: {issue}" for issue in check_headers(response.headers))
            if path == "/api/session":
                control = response.headers.get("cache-control", "").lower()
                if "no-store" not in control:
                    failures.append("/api/session: response must be non-cacheable")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="Canonical HTTPS staging URL")
    parser.add_argument("--timeout", type=float, default=10, help="Timeout per request, seconds")
    args = parser.parse_args(argv)
    try:
        origin = validated_origin(args.origin)
    except ValueError as exc:
        parser.error(str(exc))
    if args.timeout <= 0 or args.timeout > 60:
        parser.error("--timeout must be between 0 and 60 seconds")
    failures = run_checks(origin, args.timeout)
    if failures:
        for failure in failures:
            print("FAIL:", failure, file=sys.stderr)
        return 1
    print("Cloud staging anonymous HTTPS smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

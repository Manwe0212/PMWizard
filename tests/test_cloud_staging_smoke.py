"""PR #38 — test non-destructive cloud smoke validation without network calls."""

from email.message import Message
from pathlib import Path
from runpy import run_path

import pytest

# The operator script is standalone, not part of the installed Python package.
# Load it by its checked-in path so pytest works in isolated CI environments.
_smoke = run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "smoke_cloud_staging.py"))
check_headers = _smoke["check_headers"]
validated_origin = _smoke["validated_origin"]


@pytest.mark.parametrize("origin", [
    "http://staging.example.org",
    "https://localhost",
    "https://127.0.0.1",
    "https://user:password@staging.example.org",
    "https://staging.example.org/path",
    "https://staging.example.org?token=private",
    "https://staging.example.org/#fragment",
])
def test_reject_unsafe_or_noncanonical_origin(origin):
    with pytest.raises(ValueError):
        validated_origin(origin)


def test_accept_canonical_https_staging_origin():
    assert validated_origin("https://staging.example.org/") == "https://staging.example.org"


def test_require_security_headers():
    headers = Message()
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Strict-Transport-Security"] = "max-age=31536000"
    headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    assert check_headers(headers) == []


def test_reject_missing_security_headers():
    headers = Message()
    problems = check_headers(headers)
    assert len(problems) == 4

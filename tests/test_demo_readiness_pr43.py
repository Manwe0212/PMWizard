"""PR #43 — presentation recovery checks, with no live-network testing."""

from email.message import Message
from pathlib import Path
from runpy import run_path
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
CHECKER = run_path(str(ROOT / "scripts" / "check_demo_readiness.py"))


def source(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


def test_all_three_workspaces_warn_when_refresh_fails_with_existing_data():
    for name in ("executive-dashboard", "delivery-workspace", "memory-workspace"):
        script = source(f"components/{name}.tsx")
        assert 'className="demoStaleNotice" role="alert"' in script
        assert "Showing the last successfully loaded snapshot" in script
        assert "Retry refresh" in script
        assert "aria-busy={loading}" in script
    assert "if (loading && !dashboard)" in source("components/executive-dashboard.tsx")
    assert "if (loading && !snapshot)" in source("components/delivery-workspace.tsx")
    assert "if (loading && !snapshot)" in source("components/memory-workspace.tsx")


def test_demo_readiness_checks_only_anonymous_loopback_endpoints():
    checks = CHECKER["CHECKS"]
    assert len(checks) == 4
    assert all(url.startswith("http://127.0.0.1:") for _, url, _ in checks)
    assert ("Anonymous session rejected", "http://127.0.0.1:3000/api/session", 401) in checks


class StubResponse:
    def __init__(self, status: int, cache: str = "") -> None:
        self.status = status
        self.headers = Message()
        if cache:
            self.headers["Cache-Control"] = cache

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeOpener:
    def __init__(self, *, status: int, cache: str = "") -> None:
        self.response = StubResponse(status, cache)

    def open(self, request, timeout):
        assert request.full_url.startswith("http://127.0.0.1:")
        assert timeout == 8
        return self.response


def test_readiness_passes_expected_status_and_uncached_anonymous_rejection():
    run = CHECKER["run_check"]
    assert run(FakeOpener(status=200), "Web UI", "http://127.0.0.1:3000/", 200)[0]
    assert run(FakeOpener(status=401, cache="private, no-store"),
               "Anonymous session rejected", "http://127.0.0.1:3000/api/session", 401)[0]


def test_readiness_fails_unexpected_status_or_cacheable_anonymous_response():
    run = CHECKER["run_check"]
    assert not run(FakeOpener(status=500), "API ready", "http://127.0.0.1:8000/health/ready", 200)[0]
    assert not run(FakeOpener(status=401, cache="public, max-age=300"),
                   "Anonymous session rejected", "http://127.0.0.1:3000/api/session", 401)[0]


def test_session_responses_explicitly_prevent_caching():
    route = source("app/api/session/route.ts")
    assert route.count('"Cache-Control": "private, no-store"') >= 5

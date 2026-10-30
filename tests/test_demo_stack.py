"""Checks for public liveness/readiness and private demo credential setup."""

from __future__ import annotations

import runpy
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pmwizard.api import create_app
from pmwizard.persistence import Base


def _app_factory(*, migrated: bool):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    if migrated:
        Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    return create_app(factory), engine


def test_health_probes_are_public_minimal_and_schema_aware():
    app, engine = _app_factory(migrated=True)
    try:
        with TestClient(app) as client:
            live = client.get("/health/live")
            ready = client.get("/health/ready")
        assert live.status_code == 200
        assert ready.status_code == 200
        assert live.json() == {"status": "ok"}
        assert ready.json() == {"status": "ok"}
    finally:
        engine.dispose()


def test_unmigrated_database_is_not_ready_but_process_is_live():
    app, engine = _app_factory(migrated=False)
    try:
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database is not ready."}
        assert "sql" not in response.text.lower()
    finally:
        engine.dispose()


def test_private_demo_credentials_are_random_no_overwrite_and_not_logged(
    tmp_path, capsys
):
    source = Path(__file__).resolve().parents[1] / "scripts" / "init_demo_env.py"
    namespace = runpy.run_path(str(source))
    initialize = namespace["initialize"]
    target = tmp_path / ".env.demo"
    initialize.__globals__["OUTPUT"] = target

    assert initialize() == target
    contents = target.read_text(encoding="utf-8")
    entries = dict(
        line.split("=", 1)
        for line in contents.splitlines()
        if line and not line.startswith("#")
    )
    assert set(entries) == {
        "PMWIZARD_DEMO_DB_PASSWORD",
        "PMWIZARD_AUTH_SECRET",
        "PMWIZARD_DEMO_PASSWORD",
    }
    assert len(entries["PMWIZARD_DEMO_DB_PASSWORD"]) >= 40
    assert len(entries["PMWIZARD_AUTH_SECRET"]) >= 32
    assert len(entries["PMWIZARD_DEMO_PASSWORD"]) >= 20
    assert len(set(entries.values())) == 3
    output = capsys.readouterr().out
    assert "demo@example.com" in output
    assert entries["PMWIZARD_DEMO_PASSWORD"] in output
    assert entries["PMWIZARD_AUTH_SECRET"] not in output
    assert entries["PMWIZARD_DEMO_DB_PASSWORD"] not in output

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        initialize()
    assert target.read_text(encoding="utf-8") == contents

    if hasattr(stat, "S_IMODE"):
        assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0

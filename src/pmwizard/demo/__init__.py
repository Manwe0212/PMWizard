"""Explicitly gated synthetic local demo, never a production registration path."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from pmwizard.auth import AuthRepository, PasswordService
from pmwizard.persistence.orm import (
    AISuggestionORM,
    ActionItemORM,
    AppUserORM,
    AuditLogORM,
    DecisionORM,
    DependencyORM,
    EventORM,
    EvidenceORM,
    IssueORM,
    ProjectMembershipORM,
    ProjectORM,
    RiskORM,
)

# Public, deterministic LOCAL DEMO identifiers, not authentication credentials.
DEMO_TENANT_ID = UUID("269ba0ba-35e4-4e86-bd2e-7d43f09d2550")
DEMO_EMAIL = "demo@example.com"
DEMO_DISPLAY_NAME = "PMWizard Demo Project Manager"
DEMO_PROJECT_NAME = "Atlas Delivery — Synthetic Demo"
DEMO_SOURCE = "pmwizard_local_demo_v0"
DEMO_PERMISSIONS = ("project:read", "project:review")


def demo_id(label: str) -> UUID:
    return uuid5(DEMO_TENANT_ID, f"pmwizard-demo-v0:{label}")


DEMO_USER_ID = demo_id("user")
DEMO_PROJECT_ID = demo_id("project")


@dataclass(frozen=True)
class DemoSeedResult:
    tenant_id: UUID
    user_id: UUID
    project_id: UUID
    email: str
    created: int
    existing: int


def assert_local_demo_allowed(
    database_url: str,
    env: Mapping[str, str] | None = None,
) -> None:
    """Guard both the command entry point and direct service invocations."""
    values = os.environ if env is None else env
    if values.get("PMWIZARD_ENV", "").strip().lower() != "development":
        raise RuntimeError("Local demo requires PMWIZARD_ENV=development")
    if values.get("PMWIZARD_ENABLE_LOCAL_DEMO", "").strip().lower() != "true":
        raise RuntimeError("Set PMWIZARD_ENABLE_LOCAL_DEMO=true to opt in")
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise RuntimeError("Invalid local database URL") from exc
    backend = url.get_backend_name()
    if backend == "sqlite":
        # SQLite is process-local or filesystem-backed; it has no network host.
        if url.host is not None:
            raise RuntimeError("SQLite demo URL must not declare a host")
    elif backend == "postgresql":
        if url.host not in {"localhost", "127.0.0.1", "::1"}:
            raise RuntimeError("Local demo refuses non-loopback PostgreSQL hosts")
    else:
        raise RuntimeError("Local demo supports only SQLite or local PostgreSQL")


def seed_local_demo(
    session: Session,
    *,
    password: str,
    now: datetime | None = None,
) -> DemoSeedResult:
    """Create demo rows in caller-owned transaction; never alter existing rows.

    This function enforces the local database and explicit opt-in guard itself,
    even when invoked programmatically rather than via the CLI.
    """
    bind = session.get_bind()
    assert_local_demo_allowed(bind.url.render_as_string(hide_password=False))
    PasswordService._validate_password(password)
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("Demo timestamp must be timezone-aware")
    timestamp = timestamp.astimezone(timezone.utc)
    today = timestamp.date()
    created = 0
    existing = 0
    provenance = {"origin": "human", "source_system": DEMO_SOURCE,
                  "source_type": "synthetic", "source_id": "local-demo-v0",
                  "evidence_ids": [], "confidence": None, "human_verified": False}

    def ensure(model: type, key: str, **attributes: object) -> None:
        nonlocal created, existing
        row_id = demo_id(key)
        row = session.get(model, row_id)
        if row is not None:
            if row.tenant_id != DEMO_TENANT_ID:
                raise RuntimeError(f"Demo identity collision: {key}")
            if hasattr(row, "project_id") and row.project_id != DEMO_PROJECT_ID:
                raise RuntimeError(f"Demo project identity collision: {key}")
            existing += 1
            return
        session.add(model(
            id=row_id,
            tenant_id=DEMO_TENANT_ID,
            **attributes,
        ))
        session.flush()
        created += 1

    user = session.get(AppUserORM, DEMO_USER_ID)
    password_service = PasswordService()
    if user is None:
        claimed = AuthRepository(session).get_user_by_email(
            DEMO_TENANT_ID, DEMO_EMAIL
        )
        if claimed is not None:
            raise RuntimeError("Demo email is already in use by another account")
        ensure(
            AppUserORM,
            "user",
            email=DEMO_EMAIL,
            display_name=DEMO_DISPLAY_NAME,
            password_hash=password_service.hash(password),
            is_active=True,
        )
    else:
        if (
            user.tenant_id != DEMO_TENANT_ID
            or user.email != DEMO_EMAIL
            or user.display_name != DEMO_DISPLAY_NAME
            or not user.is_active
        ):
            raise RuntimeError("Demo user identity collision or inactive account")
        if not password_service.verify(user.password_hash, password):
            raise RuntimeError(
                "Existing demo user password differs; demo seeding never resets passwords"
            )
        existing += 1

    project = session.get(ProjectORM, DEMO_PROJECT_ID)
    if project is not None and (
        project.tenant_id != DEMO_TENANT_ID
        or project.source_system != DEMO_SOURCE
        or project.external_id != "atlas-demo-v0"
    ):
        raise RuntimeError("Demo project identity collision")
    ensure(
        ProjectORM,
        "project",
        name=DEMO_PROJECT_NAME,
        description="Fully synthetic project for local PMWizard evaluation.",
        objective="Demonstrate traceable delivery management and human review.",
        project_manager_id=DEMO_USER_ID,
        methodology="hybrid",
        industry="technology",
        lifecycle_phase="execution",
        status="active",
        priority="high",
        start_date=today - timedelta(days=30),
        planned_end_date=today + timedelta(days=90),
        source_system=DEMO_SOURCE,
        external_id="atlas-demo-v0",
        provenance=provenance,
    )

    ensure(
        ProjectMembershipORM,
        "membership",
        user_id=DEMO_USER_ID,
        project_id=DEMO_PROJECT_ID,
        role="project_manager",
        permissions=list(DEMO_PERMISSIONS),
    )

    evidence_id = demo_id("evidence:standup")
    ensure(
        EvidenceORM,
        "evidence:standup",
        project_id=DEMO_PROJECT_ID,
        source_type="meeting",
        source_system=DEMO_SOURCE,
        source_reference="synthetic://atlas/standup/01",
        external_id="atlas-standup-01",
        author="Synthetic delivery team",
        captured_at=timestamp - timedelta(hours=4),
        effective_at=timestamp - timedelta(hours=4),
        content_excerpt=(
            "Synthetic standup: vendor review is pending; integration tests "
            "cannot proceed until approval. No customer data."
        ),
        content_hash=None,
        permission_scope=["project:read"],
        provenance=provenance,
    )
    for name, title, status, due, priority, details in (
        (
            "blocked", "Unblock vendor integration review", "blocked",
            today - timedelta(days=2), "high",
            "Synthetic dependency requires an approval before testing proceeds.",
        ),
        (
            "progress", "Complete integration test plan", "in_progress",
            today + timedelta(days=5), "medium",
            "Draft test cases are ready for technical review.",
        ),
        (
            "done", "Confirm project kickoff scope", "completed",
            today - timedelta(days=15), "medium",
            "Scope was agreed by fictional stakeholders.",
        ),
    ):
        ensure(
            ActionItemORM,
            f"action:{name}",
            project_id=DEMO_PROJECT_ID,
            title=title,
            description=details,
            owner_id=DEMO_USER_ID,
            due_date=due,
            status=status,
            priority=priority,
            progress_summary=details,
            latest_evidence_id=evidence_id if name == "blocked" else None,
            provenance=provenance,
        )

    ensure(
        RiskORM,
        "risk:vendor",
        project_id=DEMO_PROJECT_ID,
        title="Vendor response may delay milestone",
        description="Fictional supplier response time is uncertain.",
        category="schedule",
        probability=0.65,
        impact="high",
        exposure=0.65,
        impact_type="schedule",
        trigger="Approval remains pending near test execution date.",
        mitigation="Prepare fallback integration test sequence.",
        owner_id=DEMO_USER_ID,
        status="mitigating",
        due_date=today + timedelta(days=5),
        identified_at=timestamp - timedelta(days=6),
        provenance=provenance,
    )
    ensure(
        IssueORM,
        "issue:qa",
        project_id=DEMO_PROJECT_ID,
        title="QA environment not yet provisioned",
        description="Synthetic test environment provisioning is delayed.",
        category="technical",
        severity="high",
        impact_type="schedule",
        owner_id=DEMO_USER_ID,
        status="in_progress",
        due_date=today + timedelta(days=3),
        identified_at=timestamp - timedelta(days=2),
        provenance=provenance,
    )
    ensure(
        DependencyORM,
        "dependency:vendor",
        project_id=DEMO_PROJECT_ID,
        title="Receive vendor integration sign-off",
        description="Required before the testing milestone.",
        dependency_type="external",
        owner_id=DEMO_USER_ID,
        provider="Fictional integration vendor",
        required_by=today + timedelta(days=2),
        status="blocked",
        criticality="high",
        provenance=provenance,
    )
    ensure(
        DecisionORM,
        "decision:rollout",
        project_id=DEMO_PROJECT_ID,
        title="Select staged rollout strategy",
        description="Review fictional pilot versus broad rollout.",
        status="pending",
        context="Team needs an evidence-based go/no-go choice.",
        alternatives_considered=["Pilot", "Full rollout"],
        review_date=today - timedelta(days=3),
        decision_maker_id=DEMO_USER_ID,
        provenance=provenance,
    )

    ensure(
        AISuggestionORM,
        "suggestion:blocked",
        project_id=DEMO_PROJECT_ID,
        suggestion_type="action_progress",
        target_entity_type="ActionItem",
        target_entity_id=demo_id("action:blocked"),
        proposed_changes={"status": "pending_external"},
        reason=(
            "Synthetic standup suggests the blocked action is waiting for "
            "vendor approval. A human must review before changing project truth."
        ),
        evidence_ids=[str(evidence_id)],
        confidence=0.87,
        review_status="pending",
        model_provider="synthetic",
        model_name="local-demo-v0",
        provenance=provenance,
    )
    ensure(
        EventORM,
        "event:review",
        project_id=DEMO_PROJECT_ID,
        event_type="synthetic_standup_recorded",
        occurred_at=timestamp - timedelta(hours=4),
        actor_id=DEMO_USER_ID,
        entity_type="ActionItem",
        entity_id=demo_id("action:blocked"),
        previous_value={"status": "in_progress"},
        new_value={"status": "blocked"},
        source_evidence_id=evidence_id,
        provenance=provenance,
    )

    return DemoSeedResult(
        tenant_id=DEMO_TENANT_ID,
        user_id=DEMO_USER_ID,
        project_id=DEMO_PROJECT_ID,
        email=DEMO_EMAIL,
        created=created,
        existing=existing,
    )

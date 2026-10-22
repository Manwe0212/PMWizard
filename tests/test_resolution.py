"""Tests for explainable Entity Resolution V0."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from pmwizard.models import ActionItem, Evidence, Project
from pmwizard.models.enums import ActionItemStatus
from pmwizard.persistence import Base, ProjectMemoryService, create_engine_from_url, create_session_factory
from pmwizard.resolution import (
    ActionItemResolver,
    ProjectMemoryResolutionService,
    ResolutionContext,
    ResolutionOutcome,
)


NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)


def _evidence(project_id, text: str) -> Evidence:
    return Evidence(
        project_id=project_id,
        source_type="meeting_note",
        source_system="synthetic",
        captured_at=NOW,
        content_excerpt=text,
        permission_scope=["project:read"],
    )


def test_exact_title_phrase_can_be_deterministically_matched() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        created_at=NOW,
        title="Verify API access",
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "The team completed Verify API access today.",
    )

    result = ActionItemResolver().resolve(evidence, [action])

    assert result.outcome == ResolutionOutcome.MATCHED
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == action.id
    assert result.best_candidate.breakdown.phrase_match == 1.0
    assert result.best_candidate.breakdown.title_coverage == 1.0


def test_semantically_plausible_but_non_exact_update_requires_review() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        created_at=NOW,
        title="Verify API access",
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "API access has been verified and is working.",
    )

    result = ActionItemResolver().resolve(evidence, [action])

    assert result.outcome == ResolutionOutcome.NEEDS_REVIEW
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == action.id
    assert result.best_candidate.breakdown.title_coverage >= 0.66


def test_similar_candidates_are_not_auto_linked_when_ambiguous() -> None:
    project_id = uuid4()
    actions = [
        ActionItem(
            project_id=project_id,
            created_at=NOW,
            title="Review API configuration",
            status=ActionItemStatus.IN_PROGRESS,
        ),
        ActionItem(
            project_id=project_id,
            created_at=NOW,
            title="Review API credentials",
            status=ActionItemStatus.IN_PROGRESS,
        ),
    ]
    evidence = _evidence(
        project_id,
        "The API review is still in progress.",
    )

    result = ActionItemResolver().resolve(evidence, actions)

    assert result.outcome == ResolutionOutcome.NEEDS_REVIEW
    assert len(result.candidates) == 2


def test_unrelated_evidence_returns_no_match() -> None:
    project_id = uuid4()
    action = ActionItem(
        project_id=project_id,
        created_at=NOW,
        title="Review contract",
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "Marketing campaign assets were approved.",
    )

    result = ActionItemResolver().resolve(evidence, [action])

    assert result.outcome == ResolutionOutcome.NO_MATCH


def test_owner_context_can_disambiguate_identical_titles() -> None:
    project_id = uuid4()
    owner_a = uuid4()
    owner_b = uuid4()
    action_a = ActionItem(
        project_id=project_id,
        created_at=NOW,
        title="Confirm access",
        owner_id=owner_a,
        status=ActionItemStatus.IN_PROGRESS,
    )
    action_b = ActionItem(
        project_id=project_id,
        created_at=NOW,
        title="Confirm access",
        owner_id=owner_b,
        status=ActionItemStatus.IN_PROGRESS,
    )
    evidence = _evidence(
        project_id,
        "Confirm access was completed.",
    )

    result = ActionItemResolver().resolve(
        evidence,
        [action_a, action_b],
        context=ResolutionContext(owner_id=owner_b),
    )

    assert result.outcome == ResolutionOutcome.MATCHED
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == action_b.id
    assert result.best_candidate.breakdown.owner_match == 1.0


@pytest.fixture()
def session():
    engine = create_engine_from_url("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


def test_resolution_service_uses_only_open_items_in_authorized_project(session) -> None:
    tenant_id = uuid4()
    project_memory = ProjectMemoryService(session)
    project = project_memory.create_project(
        tenant_id,
        Project(name="Resolution Service Test"),
    )

    open_action = project_memory.add_action_item(
        tenant_id,
        ActionItem(
            project_id=project.id,
            created_at=NOW,
            title="Confirm vendor access",
            status=ActionItemStatus.IN_PROGRESS,
        ),
    )
    for status in (ActionItemStatus.COMPLETED, ActionItemStatus.CANCELLED):
        project_memory.add_action_item(
            tenant_id,
            ActionItem(
                project_id=project.id,
                created_at=NOW,
                title="Confirm vendor access",
                status=status,
            ),
        )

    evidence = _evidence(
        project.id,
        "Confirm vendor access was completed today.",
    )

    resolution = ProjectMemoryResolutionService(session)
    result = resolution.resolve_evidence_to_action_items(
        tenant_id,
        evidence,
    )

    assert result.outcome == ResolutionOutcome.MATCHED
    assert result.best_candidate is not None
    assert result.best_candidate.entity_id == open_action.id
    assert len(result.candidates) == 1


def test_resolution_service_blocks_cross_tenant_project_access(session) -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    project_memory = ProjectMemoryService(session)
    project = project_memory.create_project(
        tenant_a,
        Project(name="Private Tenant Project"),
    )

    evidence = _evidence(project.id, "Review contract is complete.")
    resolution = ProjectMemoryResolutionService(session)

    with pytest.raises(LookupError):
        resolution.resolve_evidence_to_action_items(
            tenant_b,
            evidence,
        )


@pytest.mark.parametrize("limit", [1, 2, 5])
def test_high_scoring_ties_require_review_regardless_of_return_limit(limit) -> None:
    project_id = uuid4()
    actions = [
        ActionItem(id=UUID(int=i), project_id=project_id, title="Confirm access", created_at=NOW)
        for i in (2, 1)
    ]
    evidence = _evidence(project_id, "Confirm access")
    result = ActionItemResolver().resolve(evidence, actions, max_candidates=limit)
    reversed_result = ActionItemResolver().resolve(evidence, list(reversed(actions)), max_candidates=limit)

    assert result.outcome == ResolutionOutcome.NEEDS_REVIEW
    assert result.best_candidate.score >= 0.78
    assert result.best_candidate.entity_id == UUID(int=1)
    assert result == reversed_result
    assert len(result.candidates) == min(limit, 2)


@pytest.mark.parametrize("status", [ActionItemStatus.COMPLETED, ActionItemStatus.CANCELLED])
def test_direct_resolver_excludes_closed_items(status) -> None:
    project_id = uuid4()
    action = ActionItem(project_id=project_id, title="Confirm access", created_at=NOW, status=status)
    result = ActionItemResolver().resolve(_evidence(project_id, "Confirm access"), [action])
    assert result.outcome == ResolutionOutcome.NO_MATCH
    assert result.candidates == []


@pytest.mark.parametrize("limit", [0, -1, 1.5, True, None])
def test_invalid_candidate_limit_is_rejected_even_for_empty_evidence(limit) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ActionItemResolver().resolve(_evidence(uuid4(), ""), [], max_candidates=limit)


@pytest.mark.parametrize("margin", [-0.1, 1.1, float("nan"), float("inf"), -float("inf")])
def test_invalid_ambiguity_margin_is_rejected(margin) -> None:
    with pytest.raises(ValueError, match="Ambiguity margin"):
        ActionItemResolver(ambiguity_margin=margin)


@pytest.mark.parametrize("match,review", [(0.2, 0.3), (1.1, 0.3), (0.78, -0.1), (float("nan"), 0.3)])
def test_invalid_score_thresholds_are_rejected(match, review) -> None:
    with pytest.raises(ValueError, match="Thresholds"):
        ActionItemResolver(match_threshold=match, review_threshold=review)


@pytest.mark.parametrize(
    "best,second,expected",
    [
        (0.2999, None, ResolutionOutcome.NO_MATCH),
        (0.30, None, ResolutionOutcome.NEEDS_REVIEW),
        (0.7799, None, ResolutionOutcome.NEEDS_REVIEW),
        (0.78, None, ResolutionOutcome.MATCHED),
        (0.90, 0.8201, ResolutionOutcome.NEEDS_REVIEW),
        (0.90, 0.82, ResolutionOutcome.MATCHED),
        (0.90, 0.8199, ResolutionOutcome.MATCHED),
    ],
)
def test_decision_threshold_boundaries(monkeypatch, best, second, expected) -> None:
    project_id = uuid4()
    actions = [ActionItem(project_id=project_id, title="Confirm access", created_at=NOW)]
    if second is not None:
        actions.append(ActionItem(project_id=project_id, title="Confirm access", created_at=NOW))
    scores = dict(zip([action.id for action in actions], [best, second]))
    resolver = ActionItemResolver()
    original = resolver._score_candidate

    def score_candidate(evidence, action, context):
        return original(evidence, action, context).model_copy(update={"score": scores[action.id]})

    monkeypatch.setattr(resolver, "_score_candidate", score_candidate)
    result = resolver.resolve(_evidence(project_id, "Confirm access"), actions)
    assert result.outcome == expected


@pytest.mark.parametrize("text,phrase", [("Review contract", 1.0), ("Review contracts", 0.0), ("Preview contract", 0.0), ("Please REVIEW: contract!", 1.0)])
def test_exact_phrase_requires_complete_normalized_tokens(text, phrase) -> None:
    project_id = uuid4()
    action = ActionItem(project_id=project_id, title="Review contract", created_at=NOW)
    result = ActionItemResolver().resolve(_evidence(project_id, text), [action])
    assert result.candidates[0].breakdown.phrase_match == phrase


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_evidence_returns_no_match(text) -> None:
    result = ActionItemResolver().resolve(_evidence(uuid4(), text), [])
    assert result.outcome == ResolutionOutcome.NO_MATCH
    assert result.candidates == []


def test_resolution_isolates_projects_with_identical_titles(session) -> None:
    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    projects = [memory.create_project(tenant_id, Project(name=name)) for name in ("A", "B")]
    actions = [memory.add_action_item(tenant_id, ActionItem(project_id=p.id, title="Confirm access", created_at=NOW)) for p in projects]
    evidence = _evidence(projects[0].id, "Confirm access")
    result = ProjectMemoryResolutionService(session).resolve_evidence_to_action_items(tenant_id, evidence)
    assert result.outcome == ResolutionOutcome.MATCHED
    assert [c.entity_id for c in result.candidates] == [actions[0].id]
    direct = ActionItemResolver().resolve(evidence, actions)
    assert [c.entity_id for c in direct.candidates] == [actions[0].id]


@pytest.mark.parametrize("text,expected", [
    ("Confirm access", ResolutionOutcome.MATCHED),
    ("Access is working", ResolutionOutcome.NEEDS_REVIEW),
    ("Marketing campaign approved", ResolutionOutcome.NO_MATCH),
])
def test_resolution_does_not_mutate_inputs_or_persist_changes(session, text, expected) -> None:
    from sqlalchemy import select

    tenant_id = uuid4()
    memory = ProjectMemoryService(session)
    project = memory.create_project(tenant_id, Project(name="Read only resolution"))
    action = memory.add_action_item(tenant_id, ActionItem(project_id=project.id, title="Confirm access", created_at=NOW))
    evidence = _evidence(project.id, text)
    memory.add_evidence(tenant_id, evidence)
    session.commit()

    def snapshot():
        return {table.name: [dict(row) for row in session.execute(select(table)).mappings()] for table in Base.metadata.sorted_tables}

    before_db = snapshot()
    before_action = action.model_dump()
    before_evidence = evidence.model_dump()
    result = ProjectMemoryResolutionService(session).resolve_evidence_to_action_items(tenant_id, evidence)
    direct = ActionItemResolver().resolve(evidence, [action])
    session.commit()

    assert result.outcome == direct.outcome == expected
    assert action.model_dump() == before_action
    assert evidence.model_dump() == before_evidence
    assert snapshot() == before_db

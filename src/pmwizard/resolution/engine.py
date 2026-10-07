"""Deterministic Action Item entity resolution for PMWizard V0.

V0 intentionally avoids embeddings and LLM calls. It provides transparent
candidate scoring that can later be complemented by semantic retrieval and
model-assisted classification.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher

from pmwizard.models import ActionItem, Evidence

from .models import (
    ResolutionCandidate,
    ResolutionContext,
    ResolutionOutcome,
    ResolutionResult,
    ScoreBreakdown,
)


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "de",
    "del",
    "el",
    "en",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "la",
    "las",
    "los",
    "of",
    "on",
    "para",
    "por",
    "the",
    "to",
    "un",
    "una",
    "with",
    "y",
}


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _stem_token(token: str) -> str:
    """Very small language-agnostic reducer for obvious inflection noise."""
    if token.endswith("ied") and len(token) > 5:
        return token[:-3] + "y"
    for suffix in ("ing", "mente", "ados", "adas", "ido", "ida", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _tokens(value: str) -> set[str]:
    return {
        _stem_token(token)
        for token in _normalize_text(value).split()
        if token not in _STOPWORDS and len(token) > 1
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _temporal_proximity(action: ActionItem, evidence: Evidence) -> float:
    reference = evidence.effective_at or evidence.captured_at
    candidates: list[datetime] = [action.created_at]
    if action.last_progress_date is not None:
        candidates.append(action.last_progress_date)

    reference = _as_aware(reference)
    delta_days = min(
        abs((_as_aware(candidate) - reference).total_seconds()) / 86400
        for candidate in candidates
    )

    if delta_days <= 7:
        return 1.0
    if delta_days <= 30:
        return 0.7
    if delta_days <= 90:
        return 0.4
    return 0.1


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ActionItemResolver:
    """Resolve new evidence against existing open Action Items."""

    def __init__(
        self,
        *,
        match_threshold: float = 0.78,
        review_threshold: float = 0.30,
        ambiguity_margin: float = 0.08,
    ) -> None:
        if not 0 <= review_threshold <= match_threshold <= 1:
            raise ValueError("Thresholds must satisfy 0 <= review <= match <= 1")
        self.match_threshold = match_threshold
        self.review_threshold = review_threshold
        self.ambiguity_margin = ambiguity_margin

    def resolve(
        self,
        evidence: Evidence,
        action_items: list[ActionItem],
        *,
        context: ResolutionContext | None = None,
        max_candidates: int = 5,
    ) -> ResolutionResult:
        query_text = (evidence.content_excerpt or "").strip()
        if not query_text:
            return ResolutionResult(
                outcome=ResolutionOutcome.NO_MATCH,
                query_text="",
                explanation="Evidence contains no text that can be resolved.",
            )

        context = context or ResolutionContext()
        scored = [
            self._score_candidate(evidence, action, context)
            for action in action_items
            if action.project_id == evidence.project_id
        ]
        scored.sort(key=lambda candidate: candidate.score, reverse=True)
        candidates = scored[:max_candidates]

        if not candidates or candidates[0].score < self.review_threshold:
            return ResolutionResult(
                outcome=ResolutionOutcome.NO_MATCH,
                query_text=query_text,
                candidates=candidates,
                explanation=(
                    "No existing Action Item reached the minimum review threshold; "
                    "treat the evidence as a possible new entity or unrelated update."
                ),
            )

        best = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0.0
        margin = best.score - second_score

        if best.score >= self.match_threshold and margin >= self.ambiguity_margin:
            return ResolutionResult(
                outcome=ResolutionOutcome.MATCHED,
                query_text=query_text,
                best_candidate=best,
                candidates=candidates,
                explanation=(
                    "One existing Action Item has a high, sufficiently distinct "
                    "deterministic score. Linking evidence is safe enough for V0; "
                    "this does not change governed Action Item status."
                ),
            )

        return ResolutionResult(
            outcome=ResolutionOutcome.NEEDS_REVIEW,
            query_text=query_text,
            best_candidate=best,
            candidates=candidates,
            explanation=(
                "At least one plausible Action Item exists, but confidence or "
                "separation from other candidates is insufficient for deterministic linking."
            ),
        )

    def _score_candidate(
        self,
        evidence: Evidence,
        action: ActionItem,
        context: ResolutionContext,
    ) -> ResolutionCandidate:
        query = _normalize_text(evidence.content_excerpt or "")
        title = _normalize_text(action.title)
        description = _normalize_text(action.description or "")
        candidate_text = " ".join(part for part in (title, description) if part)

        phrase_match = 1.0 if title and title in query else 0.0
        text_similarity = SequenceMatcher(None, title, query).ratio() if title else 0.0
        query_tokens = _tokens(query)
        title_tokens = _tokens(title)
        candidate_tokens = _tokens(candidate_text)
        token_overlap = _jaccard(query_tokens, candidate_tokens)
        title_coverage = (
            len(query_tokens & title_tokens) / len(title_tokens)
            if title_tokens
            else 0.0
        )

        owner_match = 0.0
        if context.owner_id is not None and action.owner_id is not None:
            owner_match = 1.0 if context.owner_id == action.owner_id else 0.0

        temporal_proximity = _temporal_proximity(action, evidence)

        # Lexical evidence intentionally dominates V0. Owner/time are supporting hints.
        score = (
            0.25 * phrase_match
            + 0.35 * title_coverage
            + 0.10 * text_similarity
            + 0.15 * token_overlap
            + 0.10 * owner_match
            + 0.05 * temporal_proximity
        )
        score = round(min(max(score, 0.0), 1.0), 4)

        reasons: list[str] = []
        if phrase_match:
            reasons.append("action title appears in evidence")
        if title_coverage >= 0.75:
            reasons.append("most Action Item keywords appear in evidence")
        if token_overlap >= 0.5:
            reasons.append("strong keyword overlap")
        elif token_overlap >= 0.25:
            reasons.append("moderate keyword overlap")
        if owner_match:
            reasons.append("owner matches structured context")
        if temporal_proximity >= 0.7:
            reasons.append("evidence is temporally close to the Action Item")

        return ResolutionCandidate(
            entity_type="ActionItem",
            entity_id=action.id,
            title=action.title,
            score=score,
            breakdown=ScoreBreakdown(
                phrase_match=phrase_match,
                title_coverage=round(title_coverage, 4),
                text_similarity=round(text_similarity, 4),
                token_overlap=round(token_overlap, 4),
                owner_match=owner_match,
                temporal_proximity=temporal_proximity,
            ),
            reasons=reasons,
        )

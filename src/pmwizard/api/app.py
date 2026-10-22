"""FastAPI application for Project Inbox V0."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from pmwizard.inbox import (
    InboxListResponse,
    InboxSuggestionDetail,
    ProjectInboxService,
    ReviewCommand,
    ReviewResponse,
)
from pmwizard.models.enums import ReviewStatus
from pmwizard.persistence import create_engine_from_url, create_session_factory

from .context import ApiPrincipal, get_api_principal


SessionFactory = Callable[[], Session]


def create_app(session_factory: SessionFactory) -> FastAPI:
    app = FastAPI(
        title="PMWizard API",
        version="0.1.0",
        description=(
            "Human-governed Project Intelligence API. "
            "V0 exposes the Project Inbox review workflow."
        ),
    )

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def require_permission(principal: ApiPrincipal, permission: str) -> None:
        if permission not in principal.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/v1/projects/{project_id}/inbox",
        response_model=InboxListResponse,
    )
    def list_project_inbox(
        project_id: UUID,
        review_status: list[ReviewStatus] | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        principal: ApiPrincipal = Depends(get_api_principal),
        session: Session = Depends(get_session),
    ) -> InboxListResponse:
        require_permission(principal, "project:read")
        service = ProjectInboxService(session)
        try:
            return service.list_items(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                permissions=principal.permissions,
                statuses=review_status,
                limit=limit,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/projects/{project_id}/inbox/{suggestion_id}",
        response_model=InboxSuggestionDetail,
    )
    def get_project_inbox_item(
        project_id: UUID,
        suggestion_id: UUID,
        principal: ApiPrincipal = Depends(get_api_principal),
        session: Session = Depends(get_session),
    ) -> InboxSuggestionDetail:
        require_permission(principal, "project:read")
        service = ProjectInboxService(session)
        try:
            item = service.get_item(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                suggestion_id=suggestion_id,
                permissions=principal.permissions,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inbox item not found or not authorized.",
            )
        return item

    @app.post(
        "/v1/projects/{project_id}/inbox/{suggestion_id}/review",
        response_model=ReviewResponse,
    )
    def review_project_inbox_item(
        project_id: UUID,
        suggestion_id: UUID,
        command: ReviewCommand,
        principal: ApiPrincipal = Depends(get_api_principal),
        session: Session = Depends(get_session),
    ) -> ReviewResponse:
        require_permission(principal, "project:read")
        require_permission(principal, "project:review")
        service = ProjectInboxService(session)
        try:
            result = service.review_item(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                suggestion_id=suggestion_id,
                reviewer_id=principal.user_id,
                permissions=principal.permissions,
                command=command,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inbox item not found or not authorized.",
            )
        return result

    return app


def create_default_app() -> FastAPI:
    database_url = os.getenv("PMWIZARD_DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "PMWIZARD_DATABASE_URL is required to create the default API app."
        )
    engine = create_engine_from_url(database_url)
    return create_app(create_session_factory(engine))

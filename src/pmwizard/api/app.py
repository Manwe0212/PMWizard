"""FastAPI application for authenticated Project Inbox V0."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from pmwizard.auth import (
    AccessTokenService,
    AuthenticationError,
    AuthRepository,
    AuthService,
    AuthSettings,
)
from pmwizard.auth.schemas import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    ProjectsResponse,
)
from pmwizard.executive import ExecutiveDashboardService, ExecutiveDashboardSnapshot
from pmwizard.health import (
    HealthSnapshotCaptureResponse,
    ProjectHealthHistory,
    ProjectHealthHistoryService,
    ProjectHealthService,
    ProjectHealthSnapshot,
)
from pmwizard.inbox import (
    InboxListResponse,
    InboxSuggestionDetail,
    ProjectInboxService,
    ReviewCommand,
    ReviewResponse,
)
from pmwizard.memory import (
    ProjectMemoryQueryService,
    ProjectMemorySnapshot,
)
from pmwizard.models.enums import ReviewStatus
from pmwizard.persistence import create_engine_from_url, create_session_factory
from pmwizard.portfolio import (
    ProgramPortfolioIntelligenceService,
    ProgramPortfolioOverview,
)
from pmwizard.sources import SourcesWorkspaceService, SourcesWorkspaceSnapshot

from .context import ApiPrincipal


SessionFactory = Callable[[], Session]


def create_app(
    session_factory: SessionFactory,
    *,
    auth_settings: AuthSettings | None = None,
    allow_trusted_headers: bool = False,
) -> FastAPI:
    app = FastAPI(
        title="PMWizard API",
        version="0.1.0",
        description=(
            "Authenticated, human-governed Project Intelligence API. "
            "V0 exposes login, project selection, and Project Inbox review."
        ),
    )
    token_service = (
        AccessTokenService(auth_settings) if auth_settings is not None else None
    )

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def unauthorized(detail: str) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    def get_principal(
        authorization: str | None = Header(default=None, alias="Authorization"),
        tenant_id: UUID | None = Header(
            default=None,
            alias="X-PMWizard-Tenant-ID",
        ),
        user_id: UUID | None = Header(
            default=None,
            alias="X-PMWizard-User-ID",
        ),
        permissions_header: str = Header(
            default="",
            alias="X-PMWizard-Permissions",
        ),
        session: Session = Depends(get_session),
    ) -> ApiPrincipal:
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.casefold() != "bearer" or not token.strip():
                raise unauthorized("Authorization must use Bearer token")
            if token_service is None:
                raise unauthorized("Bearer authentication is not configured")

            try:
                user = AuthService(
                    session,
                    token_service,
                ).authenticate_token(token.strip())
            except AuthenticationError as exc:
                raise unauthorized(str(exc)) from exc

            return ApiPrincipal(
                tenant_id=user.tenant_id,
                user_id=user.id,
                auth_method="bearer",
            )

        if allow_trusted_headers and tenant_id is not None and user_id is not None:
            permissions = {
                item.strip()
                for item in permissions_header.split(",")
                if item.strip()
            }
            return ApiPrincipal(
                tenant_id=tenant_id,
                user_id=user_id,
                permissions=permissions,
                auth_method="trusted_headers",
            )

        raise unauthorized("Authentication required")

    def require_permission(permissions: set[str], permission: str) -> None:
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}",
            )

    def project_permissions(
        principal: ApiPrincipal,
        project_id: UUID,
        session: Session,
    ) -> set[str]:
        if principal.auth_method == "trusted_headers":
            return principal.permissions

        membership = AuthRepository(session).get_project_membership(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            project_id=project_id,
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or not authorized.",
            )
        return set(membership.permissions)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/auth/login", response_model=LoginResponse)
    def login(
        command: LoginRequest,
        session: Session = Depends(get_session),
    ) -> LoginResponse:
        if token_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is not configured.",
            )
        try:
            authenticated = AuthService(session, token_service).login(
                tenant_id=command.tenant_id,
                email=str(command.email),
                password=command.password,
            )
        except AuthenticationError as exc:
            raise unauthorized(str(exc)) from exc

        return LoginResponse(
            access_token=authenticated.access_token,
            expires_in=authenticated.expires_in,
            user=authenticated.user,
        )

    @app.get("/v1/auth/me", response_model=MeResponse)
    def me(
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> MeResponse:
        user = AuthRepository(session).get_user(
            principal.tenant_id,
            principal.user_id,
        )
        if user is None:
            raise unauthorized("Authenticated user is no longer available")
        return MeResponse(user=user)

    @app.get("/v1/projects", response_model=ProjectsResponse)
    def list_projects(
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ProjectsResponse:
        if principal.auth_method == "trusted_headers":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project selection requires Bearer authentication.",
            )
        items = AuthRepository(session).list_project_access(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        return ProjectsResponse(count=len(items), items=items)

    @app.get(
        "/v1/executive/dashboard",
        response_model=ExecutiveDashboardSnapshot,
    )
    def get_executive_dashboard(
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ExecutiveDashboardSnapshot:
        if principal.auth_method == "trusted_headers":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Executive Dashboard requires Bearer authentication so "
                    "project memberships and evidence permissions can be resolved."
                ),
            )

        project_access = AuthRepository(session).list_project_access(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        project_permissions_map = {
            item.project_id: set(item.permissions)
            for item in project_access
        }
        project_names = {
            item.project_id: item.name
            for item in project_access
        }

        return ExecutiveDashboardService(session).snapshot(
            tenant_id=principal.tenant_id,
            project_permissions=project_permissions_map,
            project_names=project_names,
        )

    @app.get(
        "/v1/intelligence/overview",
        response_model=ProgramPortfolioOverview,
    )
    def get_program_portfolio_intelligence(
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ProgramPortfolioOverview:
        if principal.auth_method == "trusted_headers":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Program and Portfolio Intelligence requires Bearer "
                    "authentication so project memberships can be resolved."
                ),
            )

        project_access = AuthRepository(session).list_project_access(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        authorized_project_ids = {
            item.project_id
            for item in project_access
            if "project:read" in item.permissions
        }
        return ProgramPortfolioIntelligenceService(session).overview(
            tenant_id=principal.tenant_id,
            authorized_project_ids=authorized_project_ids,
        )

    @app.get(
        "/v1/projects/{project_id}/health/history",
        response_model=ProjectHealthHistory,
    )
    def get_project_health_history(
        project_id: UUID,
        limit: int = Query(default=90, ge=2, le=365),
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ProjectHealthHistory:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return ProjectHealthHistoryService(session).history(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                limit=limit,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.post(
        "/v1/projects/{project_id}/health/snapshots",
        response_model=HealthSnapshotCaptureResponse,
    )
    def capture_project_health_snapshot(
        project_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> HealthSnapshotCaptureResponse:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return ProjectHealthHistoryService(session).capture(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                captured_by=principal.user_id,
                capture_source="manual",
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/projects/{project_id}/health",
        response_model=ProjectHealthSnapshot,
    )
    def get_project_health(
        project_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ProjectHealthSnapshot:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return ProjectHealthService(session).snapshot(
                tenant_id=principal.tenant_id,
                project_id=project_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/projects/{project_id}/sources",
        response_model=SourcesWorkspaceSnapshot,
    )
    def get_project_sources(
        project_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> SourcesWorkspaceSnapshot:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return SourcesWorkspaceService(session).snapshot(
                tenant_id=principal.tenant_id,
                project_id=project_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/projects/{project_id}/memory",
        response_model=ProjectMemorySnapshot,
    )
    def get_project_memory(
        project_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ProjectMemorySnapshot:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return ProjectMemoryQueryService(session).snapshot(
                tenant_id=principal.tenant_id,
                project_id=project_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/projects/{project_id}/inbox",
        response_model=InboxListResponse,
    )
    def list_project_inbox(
        project_id: UUID,
        review_status: list[ReviewStatus] | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> InboxListResponse:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        service = ProjectInboxService(session)
        try:
            return service.list_items(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                permissions=permissions,
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
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> InboxSuggestionDetail:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        service = ProjectInboxService(session)
        try:
            item = service.get_item(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                suggestion_id=suggestion_id,
                permissions=permissions,
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
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ReviewResponse:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        service = ProjectInboxService(session)
        try:
            result = service.review_item(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                suggestion_id=suggestion_id,
                reviewer_id=principal.user_id,
                permissions=permissions,
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

    secret = os.getenv("PMWIZARD_AUTH_SECRET")
    if not secret:
        raise RuntimeError(
            "PMWIZARD_AUTH_SECRET is required to create the default API app."
        )

    auth_settings = AuthSettings(
        secret_key=secret,
        issuer=os.getenv("PMWIZARD_AUTH_ISSUER", "pmwizard"),
        audience=os.getenv("PMWIZARD_AUTH_AUDIENCE", "pmwizard-api"),
        access_token_minutes=int(
            os.getenv("PMWIZARD_ACCESS_TOKEN_MINUTES", "30")
        ),
    )

    engine = create_engine_from_url(database_url)
    return create_app(
        create_session_factory(engine),
        auth_settings=auth_settings,
        allow_trusted_headers=False,
    )

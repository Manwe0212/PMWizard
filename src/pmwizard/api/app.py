"""FastAPI application for authenticated Project Inbox V0."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Literal
from collections.abc import Callable, Iterator
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import text as sql_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pmwizard.auth import (
    AccessTokenService,
    AuthenticationError,
    AuthRepository,
    AuthService,
    ProjectAccess,
    AuthSettings,
)
from pmwizard.ai import (
    AIProviderError,
    OpenAIResponsesProvider,
    StructuredGenerationProvider,
)
from pmwizard.automation import (
    AutomationScheduleService,
    AutomationScheduleView,
    AutomationsWorkspaceSnapshot,
    CreateAutomationScheduleRequest,
    RunNowResponse,
    UpdateAutomationScheduleRequest,
)
from pmwizard.activity import (
    ActivityCategory,
    ActivityTimeline,
    ProjectActivityExportService,
    ProjectActivityService,
)
from pmwizard.attention import (
    AttentionCenterService,
    AttentionCenterSnapshot,
    AttentionStateCommand,
    AttentionStateResponse,
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
from pmwizard.onboarding import CreateProjectRequest, ProjectOnboardingService
from pmwizard.notifications import (
    NotificationPreferenceCommand,
    NotificationPreferenceService,
    NotificationWorkspaceSnapshot,
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
from pmwizard.reports import (
    StatusReportDraft,
    StatusReportGeneratorService,
    StatusReportRequest,
    UngroundedStatusReportError,
)
from pmwizard.sources import (
    BindSourceCredentialRequest,
    CreateSourceConnectionRequest,
    SourceConnectionAdminService,
    SourceConnectionTestResponse,
    SourceConnectionView,
    SourceCredentialService,
    SourceCredentialStatus,
    SourcesWorkspaceService,
    SourcesWorkspaceSnapshot,
    UpdateSourceConnectionRequest,
)

from .context import ApiPrincipal


SessionFactory = Callable[[], Session]


def create_app(
    session_factory: SessionFactory,
    *,
    auth_settings: AuthSettings | None = None,
    allow_trusted_headers: bool = False,
    status_report_provider: StructuredGenerationProvider | None = None,
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

    @app.get("/health/live", include_in_schema=False)
    def health_live() -> dict[str, str]:
        """Process liveness; no user data, credentials or integration checks."""
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def health_ready(session: Session = Depends(get_session)) -> dict[str, str]:
        """Readiness requires a reachable, migrated project database."""
        try:
            session.execute(sql_text("SELECT 1 FROM projects LIMIT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not ready.",
            ) from exc
        return {"status": "ok"}

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

    @app.post(
        "/v1/projects",
        response_model=ProjectAccess,
        status_code=status.HTTP_201_CREATED,
    )
    def create_project(
        command: CreateProjectRequest,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ProjectAccess:
        # Only authenticated, active accounts can open their own project.
        # Trusted development headers must never create arbitrary tenant data.
        if principal.auth_method != "bearer":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Project creation requires Bearer authentication.",
            )
        try:
            return ProjectOnboardingService(session).create(
                tenant_id=principal.tenant_id,
                actor_id=principal.user_id,
                command=command,
            )
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc

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
        "/v1/projects/{project_id}/activity",
        response_model=ActivityTimeline,
    )
    def get_project_activity(
        project_id: UUID,
        category: list[ActivityCategory] | None = Query(default=None),
        actor_id: UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: str | None = Query(default=None, max_length=256),
        limit: int = Query(default=40, ge=1, le=100),
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> ActivityTimeline:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return ProjectActivityService(session).timeline(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                permissions=permissions,
                categories=category,
                actor_id=actor_id,
                since=since,
                until=until,
                cursor=cursor,
                limit=limit,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @app.get("/v1/projects/{project_id}/activity/export")
    def export_project_activity(
        project_id: UUID,
        export_format: Literal["csv", "json"] = Query(default="csv", alias="format"),
        category: list[ActivityCategory] | None = Query(default=None),
        actor_id: UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> Response:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            export = ProjectActivityExportService(session).export(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                permissions=permissions,
                export_format=export_format,
                categories=category,
                actor_id=actor_id,
                since=since,
                until=until,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        return Response(
            content=export.body,
            media_type=export.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{export.filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "X-PMWizard-Export-SHA256": export.sha256,
                "X-PMWizard-Export-Count": str(export.count),
                "X-PMWizard-Export-Truncated": str(export.truncated).lower(),
            },
        )

    @app.get(
        "/v1/projects/{project_id}/notifications",
        response_model=NotificationWorkspaceSnapshot,
    )
    def get_project_notifications(
        project_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> NotificationWorkspaceSnapshot:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return NotificationPreferenceService(session).snapshot(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                project_id=project_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.put(
        "/v1/projects/{project_id}/notifications",
        response_model=NotificationWorkspaceSnapshot,
    )
    def update_project_notifications(
        project_id: UUID,
        command: NotificationPreferenceCommand,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> NotificationWorkspaceSnapshot:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return NotificationPreferenceService(session).save(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                project_id=project_id,
                command=command,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/projects/{project_id}/attention",
        response_model=AttentionCenterSnapshot,
    )
    def get_project_attention(
        project_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> AttentionCenterSnapshot:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return AttentionCenterService(session).snapshot(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                project_id=project_id,
                permissions=permissions,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.post(
        "/v1/projects/{project_id}/attention/{signal_id}/state",
        response_model=AttentionStateResponse,
    )
    def update_project_attention_state(
        project_id: UUID,
        signal_id: str,
        command: AttentionStateCommand,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> AttentionStateResponse:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return AttentionCenterService(session).update_state(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                project_id=project_id,
                permissions=permissions,
                signal_id=signal_id,
                command=command,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @app.get(
        "/v1/projects/{project_id}/automations",
        response_model=AutomationsWorkspaceSnapshot,
    )
    def get_project_automations(
        project_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> AutomationsWorkspaceSnapshot:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        try:
            return AutomationScheduleService(session).snapshot(
                tenant_id=principal.tenant_id,
                project_id=project_id,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.post(
        "/v1/projects/{project_id}/automations",
        response_model=AutomationScheduleView,
        status_code=status.HTTP_201_CREATED,
    )
    def create_project_automation(
        project_id: UUID,
        command: CreateAutomationScheduleRequest,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> AutomationScheduleView:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return AutomationScheduleService(session).create(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                created_by=principal.user_id,
                command=command,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.patch(
        "/v1/projects/{project_id}/automations/{schedule_id}",
        response_model=AutomationScheduleView,
    )
    def update_project_automation(
        project_id: UUID,
        schedule_id: UUID,
        command: UpdateAutomationScheduleRequest,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> AutomationScheduleView:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return AutomationScheduleService(session).update(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                schedule_id=schedule_id,
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

    @app.post(
        "/v1/projects/{project_id}/automations/{schedule_id}/run-now",
        response_model=RunNowResponse,
    )
    def run_project_automation_now(
        project_id: UUID,
        schedule_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> RunNowResponse:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return AutomationScheduleService(session).run_now(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                schedule_id=schedule_id,
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

    @app.post(
        "/v1/projects/{project_id}/status-report/draft",
        response_model=StatusReportDraft,
    )
    def generate_project_status_report(
        project_id: UUID,
        command: StatusReportRequest,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> StatusReportDraft:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")

        if status_report_provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI status-report provider is not configured.",
            )

        try:
            return StatusReportGeneratorService(
                session,
                status_report_provider,
            ).generate(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                command=command,
                permissions=permissions,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except UngroundedStatusReportError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "AI status-report output failed grounding validation: "
                    f"{exc}"
                ),
            ) from exc
        except AIProviderError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI status-report provider failed: {exc}",
            ) from exc

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

    @app.post(
        "/v1/projects/{project_id}/sources",
        response_model=SourceConnectionView,
        status_code=status.HTTP_201_CREATED,
    )
    def create_project_source(
        project_id: UUID,
        command: CreateSourceConnectionRequest,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> SourceConnectionView:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return SourceConnectionAdminService(session).create(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                command=command,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @app.patch(
        "/v1/projects/{project_id}/sources/{source_connection_id}",
        response_model=SourceConnectionView,
    )
    def update_project_source(
        project_id: UUID,
        source_connection_id: UUID,
        command: UpdateSourceConnectionRequest,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> SourceConnectionView:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return SourceConnectionAdminService(session).update(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                source_connection_id=source_connection_id,
                command=command,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    @app.post(
        "/v1/projects/{project_id}/sources/{source_connection_id}/test",
        response_model=SourceConnectionTestResponse,
    )
    def test_project_source(
        project_id: UUID,
        source_connection_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> SourceConnectionTestResponse:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return SourceConnectionAdminService(session).queue_test(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                source_connection_id=source_connection_id,
                requested_by=principal.user_id,
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

    @app.put(
        "/v1/projects/{project_id}/sources/{source_connection_id}/credential",
        response_model=SourceCredentialStatus,
    )
    def bind_project_source_credential(
        project_id: UUID,
        source_connection_id: UUID,
        command: BindSourceCredentialRequest,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> SourceCredentialStatus:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return SourceCredentialService(session).bind(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                source_connection_id=source_connection_id,
                command=command,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc

    @app.delete(
        "/v1/projects/{project_id}/sources/{source_connection_id}/credential",
        response_model=SourceCredentialStatus,
    )
    def clear_project_source_credential(
        project_id: UUID,
        source_connection_id: UUID,
        principal: ApiPrincipal = Depends(get_principal),
        session: Session = Depends(get_session),
    ) -> SourceCredentialStatus:
        permissions = project_permissions(principal, project_id, session)
        require_permission(permissions, "project:read")
        require_permission(permissions, "project:review")
        try:
            return SourceCredentialService(session).clear(
                tenant_id=principal.tenant_id,
                project_id=project_id,
                source_connection_id=source_connection_id,
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

    status_report_provider: StructuredGenerationProvider | None = None
    ai_provider = os.getenv("PMWIZARD_AI_PROVIDER", "").strip().casefold()
    if ai_provider:
        if ai_provider != "openai":
            raise RuntimeError(
                "PMWIZARD_AI_PROVIDER must be 'openai' when configured."
            )
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("PMWIZARD_AI_MODEL", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when PMWIZARD_AI_PROVIDER=openai."
            )
        if not model:
            raise RuntimeError(
                "PMWIZARD_AI_MODEL is required when PMWIZARD_AI_PROVIDER=openai."
            )
        status_report_provider = OpenAIResponsesProvider(
            api_key=api_key,
            model=model,
        )

    engine = create_engine_from_url(database_url)
    return create_app(
        create_session_factory(engine),
        auth_settings=auth_settings,
        allow_trusted_headers=False,
        status_report_provider=status_report_provider,
    )

"""Bootstrap the first local PMWizard user and project memberships.

This is an operator utility, not a public registration endpoint.
"""

from __future__ import annotations

import os
from uuid import UUID

from pmwizard.persistence import create_engine_from_url, create_session_factory

from .repository import AuthRepository
from .security import AccessTokenService, AuthSettings
from .service import AuthService


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    database_url = required("PMWIZARD_DATABASE_URL")
    tenant_id = UUID(required("PMWIZARD_BOOTSTRAP_TENANT_ID"))
    email = required("PMWIZARD_BOOTSTRAP_EMAIL")
    display_name = required("PMWIZARD_BOOTSTRAP_DISPLAY_NAME")
    password = required("PMWIZARD_BOOTSTRAP_PASSWORD")
    project_ids = [
        UUID(value.strip())
        for value in required("PMWIZARD_BOOTSTRAP_PROJECT_IDS").split(",")
        if value.strip()
    ]
    permissions = [
        value.strip()
        for value in os.getenv(
            "PMWIZARD_BOOTSTRAP_PERMISSIONS",
            (
                "project:read,project:review,"
                "microsoft-graph:mail:read,"
                "microsoft-graph:sharepoint:read"
            ),
        ).split(",")
        if value.strip()
    ]
    role = os.getenv(
        "PMWIZARD_BOOTSTRAP_ROLE",
        "project_manager",
    ).strip() or "project_manager"

    auth_settings = AuthSettings(
        secret_key=required("PMWIZARD_AUTH_SECRET"),
    )
    engine = create_engine_from_url(database_url)
    factory = create_session_factory(engine)

    with factory() as session:
        repository = AuthRepository(session)
        existing = repository.get_user_by_email(tenant_id, email)
        auth = AuthService(
            session,
            AccessTokenService(auth_settings),
        )

        if existing is None:
            user = auth.create_user(
                tenant_id=tenant_id,
                email=email,
                display_name=display_name,
                password=password,
            )
            print(f"Created PMWizard user {user.email} ({user.id})")
        else:
            user = existing
            print(f"Using existing PMWizard user {user.email} ({user.id})")

        for project_id in project_ids:
            membership = repository.get_project_membership(
                tenant_id=tenant_id,
                user_id=user.id,
                project_id=project_id,
            )
            if membership is not None:
                print(f"Membership already exists for project {project_id}")
                continue

            auth.grant_project_access(
                tenant_id=tenant_id,
                user_id=user.id,
                project_id=project_id,
                role=role,
                permissions=permissions,
            )
            print(f"Granted {role} access to project {project_id}")


if __name__ == "__main__":
    main()
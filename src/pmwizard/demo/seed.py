"""Operator-only CLI for synthetic local PMWizard onboarding.

Usage (never pass the password on a shell command line):
    PMWIZARD_ENV=development PMWIZARD_ENABLE_LOCAL_DEMO=true \
    PMWIZARD_DEMO_PASSWORD=<password-from-secure-env> \
    python -m pmwizard.demo.seed
"""

from __future__ import annotations

import os

from pmwizard.persistence import create_engine_from_url, create_session_factory

from . import assert_local_demo_allowed, seed_local_demo


def main() -> None:
    database_url = os.environ.get("PMWIZARD_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("PMWIZARD_DATABASE_URL is required")
    assert_local_demo_allowed(database_url)
    password = os.environ.get("PMWIZARD_DEMO_PASSWORD", "")
    if not password:
        raise RuntimeError("PMWIZARD_DEMO_PASSWORD is required (never use CLI arguments)")
    engine = create_engine_from_url(database_url)
    try:
        factory = create_session_factory(engine)
        with factory.begin() as session:
            result = seed_local_demo(session, password=password)
        print("Synthetic local PMWizard demo prepared.")
        print(f"Workspace ID: {result.tenant_id}")
        print(f"Project ID:   {result.project_id}")
        print(f"Login email:  {result.email}")
        print(f"Seed rows:    {result.created} created, {result.existing} preserved")
        print("Password:     supplied via PMWIZARD_DEMO_PASSWORD (not displayed)")
        print("Use the existing password on repeat runs; seeding never rotates it.")
        print("Demo mode is not a production onboarding or public signup flow.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

"""Database helpers for PMWizard Project Memory."""

from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_from_url(database_url: str, *, echo: bool = False) -> Engine:
    """Create a synchronous SQLAlchemy engine.

    Production uses PostgreSQL. Tests may use SQLite.
    """
    return create_engine(database_url, echo=echo, future=True)


def create_session_factory(engine: Engine) -> Callable[[], Session]:
    """Return a session factory bound to the supplied engine."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

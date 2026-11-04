"""Database-shared fixed-window auth throttles with no plaintext identifiers.

Uses atomic upsert in PostgreSQL and SQLite; no process-local counters, no
trust in unverified X-Forwarded-For, and no client-controlled exemption.
Keys are HMAC digests of the endpoint, identity/source and time window.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from datetime import datetime, timezone, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from pmwizard.persistence.orm import AuthRateLimitORM


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many attempts.")
        self.retry_after = retry_after


class AuthRateLimiter:
    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("Rate-limit key must have at least 32 characters")
        self.secret = secret.encode("utf-8")

    def check(
        self, session: Session, *, route: str, source: str,
        identity: str | None = None,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Rate limit timestamps must be timezone-aware")

        # The per-identity bucket limits targeting of a single account
        # even when attackers rotate IPs. The per-source bucket makes
        # large-scale brute-force attacks more expensive. A reverse proxy
        # needs its OWN edge/WAF limits for accurate client-IP handling.
        limits: list[tuple[str, str, int, int]] = []
        if route == "login":
            limits = [("source", source, 100, 900)]
            if identity:
                limits.append(("identity", identity, 12, 900))
        elif route == "password_reset_request":
            limits = [("source", source, 60, 900)]
            if identity:
                limits.append(("identity", identity, 15, 900))
        elif route in {"password_reset_confirm", "invitation_accept"}:
            limits = [("source", source, 80, 900)]
        else:
            raise ValueError("Unknown rate limit route")

        blocked = 0
        for kind, value, ceiling, window_seconds in limits:
            window = int(current.timestamp()) // window_seconds
            key = hmac.new(
                self.secret,
                f"{route}|{kind}|{value}|{window}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            expires_at = datetime.fromtimestamp(
                (window + 1) * window_seconds, tz=timezone.utc,
            )
            hits = self._bump(session, key=key, expires_at=expires_at)
            if hits > ceiling:
                blocked = max(
                    blocked,
                    max(1, math.ceil(expires_at.timestamp() - current.timestamp())),
                )
        # Commit *before* raising 429 so rejected attempts are counted.
        session.commit()
        if blocked:
            raise RateLimitExceeded(blocked)

    @staticmethod
    def _bump(session: Session, *, key: str, expires_at: datetime) -> int:
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise RuntimeError("Rate limits require PostgreSQL or SQLite")

        table = AuthRateLimitORM.__table__
        statement = insert(table).values(
            key_hash=key,
            hits=1,
            expires_at=expires_at,
        ).on_conflict_do_update(
            index_elements=[table.c.key_hash],
            set_={"hits": table.c.hits + 1},
        ).returning(table.c.hits)
        hits = session.execute(statement).scalar_one()
        return int(hits)

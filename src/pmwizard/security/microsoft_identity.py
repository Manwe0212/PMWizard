"""Microsoft Entra token acquisition for secure source runtime."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .secrets import EntraClientCredentials, SecretResolutionError


TokenExchange = Callable[[str, bytes], dict]


class MicrosoftEntraClientCredentialsTokenProvider:
    """Acquire and cache Graph application tokens without persisting them."""

    def __init__(
        self,
        credential: EntraClientCredentials,
        *,
        exchange: TokenExchange | None = None,
    ) -> None:
        self.credential = credential
        self.exchange = exchange or self._exchange
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def __call__(self) -> str:
        now = datetime.now(timezone.utc)
        if (
            self._token is not None
            and self._expires_at is not None
            and now < self._expires_at
        ):
            return self._token

        tenant = quote(self.credential.tenant_id.strip(), safe="")
        url = (
            f"https://login.microsoftonline.com/{tenant}/"
            "oauth2/v2.0/token"
        )
        body = urlencode(
            {
                "client_id": self.credential.client_id,
                "client_secret": self.credential.client_secret,
                "scope": self.credential.scope,
                "grant_type": "client_credentials",
            }
        ).encode("utf-8")
        payload = self.exchange(url, body)

        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(token, str) or not token.strip():
            raise SecretResolutionError(
                "Microsoft Entra returned no usable access token."
            )
        if not isinstance(expires_in, (int, float)) or expires_in <= 0:
            raise SecretResolutionError(
                "Microsoft Entra returned no usable token expiry."
            )

        self._token = token.strip()
        # Refresh before expiry; keep a small floor for short-lived test tokens.
        lifetime = max(1, int(expires_in) - 60)
        self._expires_at = now + timedelta(seconds=lifetime)
        return self._token

    @staticmethod
    def _exchange(url: str, body: bytes) -> dict:
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urlopen(request, timeout=30.0) as response:
                raw = response.read()
        except HTTPError as exc:
            raise SecretResolutionError(
                f"Microsoft Entra token endpoint returned HTTP {exc.code}."
            ) from exc
        except URLError as exc:
            raise SecretResolutionError(
                "Microsoft Entra token endpoint is unavailable."
            ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SecretResolutionError(
                "Microsoft Entra returned invalid token JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise SecretResolutionError(
                "Microsoft Entra returned an invalid token payload."
            )
        return payload

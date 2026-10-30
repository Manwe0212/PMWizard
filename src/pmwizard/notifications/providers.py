"""Runtime-only notification delivery providers."""

from __future__ import annotations

from email.message import EmailMessage
import json
import os
import smtplib
from urllib import request
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from pmwizard.security import SecretProvider


class NotificationDeliveryError(RuntimeError):
    """Safe provider failure suitable for sanitized operational history."""


class SmtpCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SmtpEmailNotificationProvider:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_email: str,
        starttls: bool,
        secret_provider: SecretProvider | None = None,
        credential_ref: str | None = None,
        smtp_factory=smtplib.SMTP,
    ) -> None:
        self.host = host
        self.port = port
        self.from_email = from_email
        self.starttls = starttls
        self.secret_provider = secret_provider
        self.credential_ref = credential_ref
        self.smtp_factory = smtp_factory

    @classmethod
    def from_environment(
        cls,
        secret_provider: SecretProvider,
        *,
        smtp_factory=smtplib.SMTP,
    ) -> "SmtpEmailNotificationProvider | None":
        host = os.getenv("PMWIZARD_NOTIFICATION_SMTP_HOST", "").strip()
        from_email = os.getenv(
            "PMWIZARD_NOTIFICATION_EMAIL_FROM",
            "",
        ).strip()
        if not host or not from_email:
            return None

        port = int(os.getenv("PMWIZARD_NOTIFICATION_SMTP_PORT", "587"))
        starttls = os.getenv(
            "PMWIZARD_NOTIFICATION_SMTP_STARTTLS",
            "true",
        ).strip().casefold() not in {"0", "false", "no"}
        credential_ref = os.getenv(
            "PMWIZARD_NOTIFICATION_SMTP_CREDENTIAL_REF",
            "",
        ).strip() or None
        return cls(
            host=host,
            port=port,
            from_email=from_email,
            starttls=starttls,
            secret_provider=secret_provider,
            credential_ref=credential_ref,
            smtp_factory=smtp_factory,
        )

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> None:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text)

        credential = self._credential()
        try:
            with self.smtp_factory(self.host, self.port, timeout=15) as client:
                if self.starttls:
                    client.starttls()
                if credential is not None:
                    client.login(credential.username, credential.password)
                client.send_message(message)
        except Exception as exc:
            raise NotificationDeliveryError(
                "Email notification delivery failed."
            ) from exc

    def _credential(self) -> SmtpCredential | None:
        if self.credential_ref is None:
            return None
        if self.secret_provider is None:
            raise NotificationDeliveryError(
                "Email notification credential provider is unavailable."
            )
        try:
            payload = json.loads(self.secret_provider.resolve(self.credential_ref))
            return SmtpCredential.model_validate(payload)
        except Exception as exc:
            raise NotificationDeliveryError(
                "Email notification credential is invalid or unavailable."
            ) from exc


class TeamsWebhookNotificationProvider:
    def __init__(
        self,
        secret_provider: SecretProvider,
        *,
        opener=request.urlopen,
    ) -> None:
        self.secret_provider = secret_provider
        self.opener = opener

    def send(
        self,
        *,
        webhook_reference: str,
        title: str,
        text: str,
    ) -> None:
        try:
            webhook_url = self.secret_provider.resolve(webhook_reference).strip()
            parsed = urlparse(webhook_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("Teams webhook must be HTTPS.")
            body = json.dumps(
                {"text": f"**{title}**\n\n{text}"}
            ).encode("utf-8")
            req = request.Request(
                webhook_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.opener(req, timeout=15) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise RuntimeError("Non-success Teams response.")
        except Exception as exc:
            raise NotificationDeliveryError(
                "Microsoft Teams notification delivery failed."
            ) from exc

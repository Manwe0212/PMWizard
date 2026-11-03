"""Secure SMTP delivery of one-time invitation links.

Opt-in only. No public SMTP setup is inferred, and verified TLS is required.
The raw token is never sent through a URL query string or saved in storage.
"""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from urllib.parse import urlparse
from typing import Protocol

from pmwizard.notifications import SmtpEmailNotificationProvider
from pmwizard.security import EnvironmentSecretProvider


class InvitationDeliveryUnavailable(RuntimeError):
    """Sanitized failure; invitation must not be committed."""


class VerifiedTlsSmtpProvider(SmtpEmailNotificationProvider):
    """Reuse existing SMTP config / secret references but require verified TLS."""

    def send(self, *, to_email: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text)

        try:
            credential = self._credential()
            with self.smtp_factory(self.host, self.port, timeout=15) as client:
                client.ehlo()
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
                if credential is not None:
                    client.login(credential.username, credential.password)
                client.send_message(message)
        except Exception as exc:
            raise InvitationDeliveryUnavailable(
                "Invitation email could not be sent."
            ) from exc


class InvitationMailer(Protocol):
    def send(self, *, to_email: str, subject: str, text: str) -> None: ...


@dataclass(frozen=True)
class InvitationEmailDelivery:
    provider: InvitationMailer
    public_base_url: str

    def send(self, *, email: str, token: str, role: str) -> None:
        link = f"{self.public_base_url}/invite#token={token}"
        message = (
            "You have been invited to join a PMWizard project.\n\n"
            f"Role: {role.replace('_', ' ')}\n"
            f"To confirm access to your email inbox and create an account, "
            f"open this single-use link:\n{link}\n\n"
            "The invitation expires after seven days.\n"
            "If you did not expect this message, do not use the link.\n"
            "Please do not forward it to anyone else."
        )
        try:
            self.provider.send(
                to_email=email,
                subject="[PMWizard] Confirm your project invitation",
                text=message,
            )
        except Exception as exc:
            raise InvitationDeliveryUnavailable(
                "Invitation email could not be sent."
            ) from exc


def delivery_from_environment() -> InvitationEmailDelivery | None:
    enabled = os.getenv("PMWIZARD_INVITATION_EMAIL_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes"}:
        return None

    raw_url = os.getenv("PMWIZARD_PUBLIC_BASE_URL", "").strip().rstrip("/")
    parsed = urlparse(raw_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeError(
            "Verified invitations require PMWIZARD_PUBLIC_BASE_URL to be a public HTTPS origin."
        )

    provider = VerifiedTlsSmtpProvider.from_environment(EnvironmentSecretProvider())
    if provider is None or not provider.starttls:
        raise RuntimeError(
            "Verified invitations require SMTP host, sender and STARTTLS to be configured."
        )
    return InvitationEmailDelivery(provider=provider, public_base_url=raw_url)

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger

_settings = get_settings()
_logger = get_logger(__name__)


class ConsoleEmailProvider:
    """Logs emails instead of sending — default for development."""

    async def send(self, to: str, subject: str, html: str, text: str) -> None:
        _logger.info("EMAIL (console) to=%s subject=%r\n%s", to, subject, text)


class SMTPEmailProvider:
    async def send(self, to: str, subject: str, html: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"] = _settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        # smtplib is blocking — run in a thread to keep the event loop free
        await asyncio.to_thread(self._send_sync, msg)

    def _send_sync(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(_settings.smtp_host, _settings.smtp_port, timeout=30) as server:
            if _settings.smtp_use_tls:
                server.starttls()
            if _settings.smtp_username:
                server.login(_settings.smtp_username, _settings.smtp_password)
            server.send_message(msg)


def get_email_provider() -> ConsoleEmailProvider | SMTPEmailProvider:
    if _settings.email_provider == "smtp" and _settings.smtp_host:
        return SMTPEmailProvider()
    return ConsoleEmailProvider()


def _layout(title: str, body_html: str) -> str:
    return f"""\
<div style="font-family:Inter,Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;">
  <h2 style="color:#0f172a;margin-bottom:8px;">AmMeeting</h2>
  <h3 style="color:#1e293b;">{title}</h3>
  {body_html}
  <p style="color:#94a3b8;font-size:12px;margin-top:32px;">
    If you didn't request this, you can safely ignore this email.
  </p>
</div>"""


async def send_verification_email(to: str, token: str) -> None:
    url = f"{_settings.frontend_url}/auth/verify-email?token={token}"
    html = _layout(
        "Verify your email",
        f'<p>Welcome to AmMeeting! Confirm your email to activate your account.</p>'
        f'<p><a href="{url}" style="background:#2563eb;color:#fff;padding:10px 20px;'
        f'border-radius:6px;text-decoration:none;">Verify email</a></p>'
        f'<p style="color:#64748b;font-size:13px;">Or open this link: {url}</p>',
    )
    text = f"Welcome to AmMeeting! Verify your email: {url}"
    await get_email_provider().send(to, "Verify your AmMeeting email", html, text)


async def send_password_reset_email(to: str, token: str) -> None:
    url = f"{_settings.frontend_url}/auth/reset-password?token={token}"
    html = _layout(
        "Reset your password",
        f'<p>We received a request to reset your AmMeeting password. This link expires in 1 hour.</p>'
        f'<p><a href="{url}" style="background:#2563eb;color:#fff;padding:10px 20px;'
        f'border-radius:6px;text-decoration:none;">Reset password</a></p>'
        f'<p style="color:#64748b;font-size:13px;">Or open this link: {url}</p>',
    )
    text = f"Reset your AmMeeting password (expires in 1 hour): {url}"
    await get_email_provider().send(to, "Reset your AmMeeting password", html, text)

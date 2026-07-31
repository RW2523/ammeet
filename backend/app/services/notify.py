from __future__ import annotations

"""
Approval notifiers — push "your delegate needs a decision" to the owner's phone.

Notification delivery is best-effort: send() NEVER raises, because a failed push
must not break the live delegate (the web approvals list is always there and the
no-decision default is silence).
"""

from abc import ABC, abstractmethod

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

_logger = get_logger(__name__)


class ApprovalNotifier(ABC):
    @abstractmethod
    async def send(self, title: str, body: str, click_url: str) -> None:
        """Deliver one approval notification. Must never raise."""
        ...


class LogNotifier(ApprovalNotifier):
    """Default notifier — just logs (the web approvals list is the real channel)."""

    async def send(self, title: str, body: str, click_url: str) -> None:
        _logger.info("Approval notification: %s — %s (%s)", title, body, click_url)


class NtfyNotifier(ApprovalNotifier):
    """Push via an ntfy.sh-compatible server: POST {base}/{topic} with Title and
    Click headers (https://docs.ntfy.sh/publish/)."""

    async def send(self, title: str, body: str, click_url: str) -> None:
        settings = get_settings()
        url = f"{settings.ntfy_base_url.rstrip('/')}/{settings.ntfy_topic}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    content=body.encode("utf-8"),
                    headers={"Title": title, "Click": click_url},
                )
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("ntfy notification failed (non-fatal): %s", exc)


def get_notifier() -> ApprovalNotifier:
    settings = get_settings()
    if settings.approval_notify_provider == "ntfy" and settings.ntfy_topic:
        return NtfyNotifier()
    return LogNotifier()

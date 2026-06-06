from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BotStatus(str, Enum):
    CREATED = "created"
    JOINING = "joining"
    IN_MEETING = "in_meeting"
    LEAVING = "leaving"
    DONE = "done"
    ERROR = "error"


class MeetingBot(Base):
    """
    Tracks a meeting bot session (e.g. a Recall.ai bot).
    One bot can be created per live meeting session.
    """

    __tablename__ = "meeting_bots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    meeting_id: Mapped[str] = mapped_column(String(36), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # External provider bot ID (e.g. Recall.ai bot UUID)
    external_bot_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="mock")
    status: Mapped[str] = mapped_column(String(32), default=BotStatus.CREATED)
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who triggered the bot
    created_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Lifecycle timestamps
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Accumulated transcript (JSON array of segments)
    transcript_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="bots", lazy="select")  # type: ignore[name-defined]

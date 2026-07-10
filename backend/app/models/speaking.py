from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class PointPriority(str, Enum):
    MUST = "must"      # must cover — glows if missed
    SHOULD = "should"
    NICE = "nice"


class PointStatus(str, Enum):
    PENDING = "pending"
    COVERED = "covered"
    MISSED = "missed"


class SpeakingPoint(Base):
    """One prepared talking point the speaker wants to cover in a session."""

    __tablename__ = "speaking_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(String(80), default="Main")           # section/agenda group
    priority: Mapped[str] = mapped_column(String(10), default=PointPriority.SHOULD.value)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default=PointStatus.PENDING.value)
    covered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    covered_by_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # the sentence that covered it

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SpeakingResponse(Base):
    """A participant response / question / decision captured live and linked to a point."""

    __tablename__ = "speaking_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    point_id: Mapped[str | None] = mapped_column(
        ForeignKey("speaking_points.id", ondelete="SET NULL"), nullable=True
    )
    speaker: Mapped[str] = mapped_column(String(120), default="Participant")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="response")  # response | question | decision

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

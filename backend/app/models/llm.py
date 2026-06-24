from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import _now


class LLMConfig(Base):
    """Instance-wide LLM provider configuration (single 'global' row).

    The API key is encrypted at rest with the same Fernet key as integration tokens.
    """

    __tablename__ = "llm_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default="global")
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="openai")
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="gpt-4o")
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

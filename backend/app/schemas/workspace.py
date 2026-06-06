from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.user import WorkspaceRole


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class WorkspaceOut(BaseModel):
    id: str
    name: str
    description: str | None
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMemberOut(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    role: WorkspaceRole
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteMemberRequest(BaseModel):
    email: str
    role: WorkspaceRole = WorkspaceRole.MEMBER


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str | None = None
    responsibility: str | None = None
    current_work: str | None = None
    decision_authority: str | None = None
    follow_up: str | None = None
    email: str | None = None
    is_external: bool = False


class PersonUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    responsibility: str | None = None
    current_work: str | None = None
    decision_authority: str | None = None
    follow_up: str | None = None
    email: str | None = None
    is_external: bool | None = None


class PersonOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    role: str | None
    responsibility: str | None
    current_work: str | None
    decision_authority: str | None
    follow_up: str | None
    email: str | None
    is_external: bool
    created_at: datetime

    model_config = {"from_attributes": True}

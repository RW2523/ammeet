from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.meeting import Person
from app.models.user import User, WorkspaceRole
from app.schemas.workspace import PersonCreate, PersonOut, PersonUpdate

router = APIRouter()


@router.post("/{workspace_id}/people", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
async def create_person(
    workspace_id: str,
    body: PersonCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Person:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    person = Person(workspace_id=workspace_id, **body.model_dump())
    db.add(person)
    await db.flush()
    return person


@router.get("/{workspace_id}/people", response_model=list[PersonOut])
async def list_people(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Person]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(Person)
        .where(Person.workspace_id == workspace_id)
        .order_by(Person.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{workspace_id}/people/{person_id}", response_model=PersonOut)
async def get_person(
    workspace_id: str,
    person_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Person:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(Person).where(Person.id == person_id, Person.workspace_id == workspace_id)
    )
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.patch("/{workspace_id}/people/{person_id}", response_model=PersonOut)
async def update_person(
    workspace_id: str,
    person_id: str,
    body: PersonUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Person:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Person).where(Person.id == person_id, Person.workspace_id == workspace_id)
    )
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(person, field, value)
    await db.flush()
    return person


@router.delete("/{workspace_id}/people/{person_id}", status_code=204)
async def delete_person(
    workspace_id: str,
    person_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Person).where(Person.id == person_id, Person.workspace_id == workspace_id)
    )
    person = result.scalar_one_or_none()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    await db.delete(person)
    return Response(status_code=204)

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.user import User, WorkspaceRole
from app.schemas.meeting import KnowledgeQueryRequest, KnowledgeQueryResponse
from app.services.knowledge_rag import answer_from_knowledge

router = APIRouter()


@router.post("/{workspace_id}/knowledge/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(
    workspace_id: str,
    body: KnowledgeQueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)

    answer, chunks = await answer_from_knowledge(db, workspace_id, body.query)

    sources = [
        {
            "id": c.id,
            "source_type": c.source_type,
            "meeting_id": c.meeting_id,
            "excerpt": c.chunk_text[:200],
        }
        for c in chunks[: body.limit]
    ]
    return {"answer": answer, "sources": sources}

from __future__ import annotations

import pytest

from app.core.security import hash_password
from app.models.user import User


@pytest.mark.asyncio
async def test_invite_member_returns_valid_member(client, db_session, auth_token, test_workspace):
    """Regression: invite_member must flush so id/created_at are populated before the
    WorkspaceMemberOut response is validated (previously 500'd on every success)."""
    invitee = User(email="invitee@ammeet.io", full_name="Invitee", hashed_password=hash_password("Password123"))
    db_session.add(invitee)
    await db_session.flush()

    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/members",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"email": "invitee@ammeet.io", "role": "member"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"]
    assert body["created_at"]
    assert body["role"] == "member"

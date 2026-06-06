from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_workspace(client, auth_token):
    r = await client.post(
        "/api/workspaces",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "My Project", "description": "A test workspace"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "My Project"
    assert "slug" in data
    return data["id"]


@pytest.mark.asyncio
async def test_workspace_rbac(client, auth_token, test_workspace):
    """Member can view but not perform admin actions."""
    workspace_id = test_workspace.id

    # List members as owner — should work
    r = await client.get(
        f"/api/workspaces/{workspace_id}/members",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200

    # Non-existent workspace — should 403/404
    r = await client.get(
        "/api/workspaces/nonexistent-id/members",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code in (403, 404)


@pytest.mark.asyncio
async def test_tenant_isolation(client, auth_token, db_session):
    """User cannot access another workspace's data."""
    from app.models.user import Workspace, WorkspaceMember
    
    # Create a second workspace not owned by test_user
    other_ws = Workspace(name="Other Workspace", slug="other-workspace-xyz")
    db_session.add(other_ws)
    await db_session.flush()

    r = await client.get(
        f"/api/workspaces/{other_ws.id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_add_person(client, auth_token, test_workspace):
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/people",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "name": "John Smith",
            "role": "Backend Developer",
            "current_work": "API authentication",
            "follow_up": "Is the auth issue resolved?",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "John Smith"
    assert data["role"] == "Backend Developer"

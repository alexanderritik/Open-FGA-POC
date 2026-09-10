"""API-level tests for Project endpoints.

Project's business data (client_id, name, created_at) is in the app DB;
its parent Client is recorded exclusively as an OpenFGA tuple
(`project:<id>#parent@client:<client_id>`) — this is what closes the
project/client inheritance gap that Steps 8-10's tests worked around by
writing that tuple directly (no Project API existed yet).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.check_request import ClientCheckRequest
from openfga_sdk.client.models.tuple import ClientTuple

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models.audit_event import AuditEvent
from app.db.models.client import Client
from app.db.models.project import Project
from app.main import app


@pytest.fixture
def api_client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def fga_cleanup():
    written: list[tuple[str, str, str]] = []
    yield written
    if not written:
        return
    settings = get_settings()
    configuration = ClientConfiguration(
        api_url=settings.fga_api_url, store_id=settings.fga_store_id, authorization_model_id=settings.fga_model_id
    )
    fga_client = OpenFgaClient(configuration)
    try:
        for user, relation, obj in written:
            try:
                await fga_client.delete_tuples([ClientTuple(user=user, relation=relation, object=obj)])
            except Exception:
                pass
    finally:
        await fga_client.close()


@pytest.fixture
def client_id():
    session = SessionLocal()
    client_id_ = f"pt-client-{uuid.uuid4().hex[:8]}"
    session.add(Client(id=client_id_, name=client_id_))
    session.commit()
    try:
        yield client_id_
    finally:
        session.query(AuditEvent).filter(AuditEvent.resource_id == client_id_).delete(synchronize_session=False)
        session.query(Client).filter(Client.id == client_id_).delete(synchronize_session=False)
        session.commit()
        session.close()


@pytest.fixture
def cleanup_project_ids():
    ids: list[str] = []
    yield ids
    if not ids:
        return
    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(AuditEvent.resource_id.in_(ids)).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def pid() -> str:
    return f"pt-{uuid.uuid4().hex[:8]}"


async def test_create_project_returns_201_and_writes_parent_tuple(
    api_client, client_id, cleanup_project_ids, fga_cleanup
):
    project_id = pid()
    cleanup_project_ids.append(project_id)

    response = api_client.post("/projects", json={"id": project_id, "client_id": client_id, "name": "Test Project"})
    fga_cleanup.append((f"client:{client_id}", "parent", f"project:{project_id}"))

    assert response.status_code == 201
    body = response.json()
    assert body == {"id": project_id, "client_id": client_id, "name": "Test Project", "created_at": body["created_at"]}

    settings = get_settings()
    configuration = ClientConfiguration(
        api_url=settings.fga_api_url, store_id=settings.fga_store_id, authorization_model_id=settings.fga_model_id
    )
    fga_client = OpenFgaClient(configuration)
    try:
        result = await fga_client.check(
            ClientCheckRequest(user=f"client:{client_id}", relation="parent", object=f"project:{project_id}")
        )
        assert result.allowed is True
    finally:
        await fga_client.close()


async def test_client_level_grant_inherits_to_project_through_the_new_tuple(
    api_client, client_id, cleanup_project_ids, fga_cleanup
):
    project_id = pid()
    cleanup_project_ids.append(project_id)
    api_client.post("/projects", json={"id": project_id, "client_id": client_id, "name": "P"})
    fga_cleanup.append((f"client:{client_id}", "parent", f"project:{project_id}"))

    user = "user:project-inherit-test"
    api_client.post("/authorization/grant", json={"user": user, "resource_type": "client", "resource_id": client_id})
    fga_cleanup.append((user, "viewer", f"client:{client_id}"))

    response = api_client.get(
        "/authorization/check",
        params={"user": user, "resource_type": "project", "resource_id": project_id, "permission": "viewer"},
    )
    assert response.json()["allowed"] is True


async def test_get_and_list_project(api_client, client_id, cleanup_project_ids, fga_cleanup):
    project_id = pid()
    cleanup_project_ids.append(project_id)
    api_client.post("/projects", json={"id": project_id, "client_id": client_id, "name": "Listed"})
    fga_cleanup.append((f"client:{client_id}", "parent", f"project:{project_id}"))

    get_response = api_client.get(f"/projects/{project_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == project_id

    list_response = api_client.get("/projects")
    assert project_id in [p["id"] for p in list_response.json()]


async def test_create_project_duplicate_id_returns_409(api_client, client_id, cleanup_project_ids, fga_cleanup):
    project_id = pid()
    cleanup_project_ids.append(project_id)
    body = {"id": project_id, "client_id": client_id, "name": "First"}
    first = api_client.post("/projects", json=body)
    fga_cleanup.append((f"client:{client_id}", "parent", f"project:{project_id}"))

    second = api_client.post("/projects", json={**body, "name": "Second"})

    assert first.status_code == 201
    assert second.status_code == 409


async def test_create_project_with_nonexistent_client_returns_404(api_client):
    response = api_client.post(
        "/projects", json={"id": pid(), "client_id": "does-not-exist-client", "name": "X"}
    )
    assert response.status_code == 404


async def test_get_nonexistent_project_returns_404(api_client):
    response = api_client.get(f"/projects/{pid()}")
    assert response.status_code == 404

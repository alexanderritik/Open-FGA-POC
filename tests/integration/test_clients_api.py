import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models.audit_event import AuditEvent
from app.db.models.client import Client
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def cleanup_client_ids():
    ids: list[str] = []
    yield ids
    if ids:
        session = SessionLocal()
        try:
            session.query(AuditEvent).filter(AuditEvent.resource_id.in_(ids)).delete(synchronize_session=False)
            session.query(Client).filter(Client.id.in_(ids)).delete(synchronize_session=False)
            session.commit()
        finally:
            session.close()


def unique_id() -> str:
    return f"api-test-{uuid.uuid4().hex[:8]}"


def test_create_client_returns_201_with_body(client, cleanup_client_ids):
    client_id = unique_id()
    cleanup_client_ids.append(client_id)

    response = client.post("/clients", json={"id": client_id, "name": "API Test Client"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == client_id
    assert body["name"] == "API Test Client"
    assert "created_at" in body


def test_create_client_duplicate_id_returns_409(client, cleanup_client_ids):
    client_id = unique_id()
    cleanup_client_ids.append(client_id)

    client.post("/clients", json={"id": client_id, "name": "First"})
    response = client.post("/clients", json={"id": client_id, "name": "Second"})

    assert response.status_code == 409


def test_create_client_invalid_id_returns_422(client):
    response = client.post("/clients", json={"id": "Not A Valid Slug!", "name": "X"})
    assert response.status_code == 422


def test_create_client_missing_name_returns_422(client):
    response = client.post("/clients", json={"id": unique_id()})
    assert response.status_code == 422


def test_get_client_by_id(client, cleanup_client_ids):
    client_id = unique_id()
    cleanup_client_ids.append(client_id)
    client.post("/clients", json={"id": client_id, "name": "Gettable"})

    response = client.get(f"/clients/{client_id}")

    assert response.status_code == 200
    assert response.json()["id"] == client_id


def test_get_nonexistent_client_returns_404(client):
    response = client.get("/clients/does-not-exist-at-all")
    assert response.status_code == 404


def test_list_clients_includes_created(client, cleanup_client_ids):
    client_id = unique_id()
    cleanup_client_ids.append(client_id)
    client.post("/clients", json={"id": client_id, "name": "Listed Client"})

    response = client.get("/clients")

    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert client_id in ids

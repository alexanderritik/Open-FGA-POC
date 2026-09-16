"""API-level tests for Structure endpoints.

Structure's business data (name, created_at) is in the application DB;
its parent Zone exists only as an OpenFGA tuple. A Client/Project row and
a Zone (created through the real zone API) are the minimum fixture needed
for a structure to have a valid parent.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.tuple import ClientTuple

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models.audit_event import AuditEvent
from app.db.models.client import Client
from app.db.models.project import Project
from app.db.models.structure import Structure
from app.db.models.zone import Zone
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
def zone_id(api_client, fga_cleanup):
    session = SessionLocal()
    client_id = f"st-client-{uuid.uuid4().hex[:8]}"
    project_id = f"st-project-{uuid.uuid4().hex[:8]}"
    zone_id_ = f"st-zone-{uuid.uuid4().hex[:8]}"
    session.add(Client(id=client_id, name=client_id))
    session.add(Project(id=project_id, client_id=client_id, name=project_id))
    session.commit()
    try:
        response = api_client.post("/zones", json={"id": zone_id_, "parent_type": "project", "parent_id": project_id})
        assert response.status_code == 201
        fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{zone_id_}"))
        yield zone_id_
    finally:
        session.query(AuditEvent).filter(
            AuditEvent.resource_id.in_([project_id, client_id, zone_id_])
        ).delete(synchronize_session=False)
        session.query(Zone).filter(Zone.id == zone_id_).delete(synchronize_session=False)
        session.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        session.query(Client).filter(Client.id == client_id).delete(synchronize_session=False)
        session.commit()
        session.close()


@pytest.fixture
def cleanup_structure_ids():
    ids: list[str] = []
    yield ids
    if not ids:
        return
    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(AuditEvent.resource_id.in_(ids)).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def sid() -> str:
    return f"st-{uuid.uuid4().hex[:8]}"


async def test_create_structure_under_zone(api_client, zone_id, cleanup_structure_ids, fga_cleanup):
    structure_id = sid()
    cleanup_structure_ids.append(structure_id)

    response = api_client.post(
        "/structures", json={"id": structure_id, "name": "Yamuna Bridge", "parent_type": "zone", "parent_id": zone_id}
    )
    fga_cleanup.append((f"zone:{zone_id}", "parent", f"structure:{structure_id}"))

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == structure_id
    assert body["name"] == "Yamuna Bridge"
    assert body["parent_type"] == "zone"
    assert body["parent_id"] == zone_id
    assert "created_at" in body


async def test_get_structure_returns_parent_from_openfga(api_client, zone_id, cleanup_structure_ids, fga_cleanup):
    structure_id = sid()
    cleanup_structure_ids.append(structure_id)
    api_client.post(
        "/structures", json={"id": structure_id, "name": "Bridge", "parent_type": "zone", "parent_id": zone_id}
    )
    fga_cleanup.append((f"zone:{zone_id}", "parent", f"structure:{structure_id}"))

    response = api_client.get(f"/structures/{structure_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": structure_id,
        "name": "Bridge",
        "created_at": response.json()["created_at"],
        "parent_type": "zone",
        "parent_id": zone_id,
    }


async def test_list_structures_is_business_data_only(api_client, zone_id, cleanup_structure_ids, fga_cleanup):
    structure_id = sid()
    cleanup_structure_ids.append(structure_id)
    api_client.post(
        "/structures", json={"id": structure_id, "name": "Listed", "parent_type": "zone", "parent_id": zone_id}
    )
    fga_cleanup.append((f"zone:{zone_id}", "parent", f"structure:{structure_id}"))

    response = api_client.get("/structures")

    assert response.status_code == 200
    item = next(s for s in response.json() if s["id"] == structure_id)
    assert set(item.keys()) == {"id", "name", "created_at"}


async def test_create_structure_duplicate_id_returns_409(api_client, zone_id, cleanup_structure_ids, fga_cleanup):
    structure_id = sid()
    cleanup_structure_ids.append(structure_id)
    body = {"id": structure_id, "name": "First", "parent_type": "zone", "parent_id": zone_id}
    first = api_client.post("/structures", json=body)
    fga_cleanup.append((f"zone:{zone_id}", "parent", f"structure:{structure_id}"))

    second = api_client.post("/structures", json={**body, "name": "Second"})

    assert first.status_code == 201
    assert second.status_code == 409


async def test_create_structure_with_nonexistent_zone_returns_404(api_client):
    response = api_client.post(
        "/structures", json={"id": sid(), "name": "X", "parent_type": "zone", "parent_id": "does-not-exist-zone"}
    )
    assert response.status_code == 404


async def test_get_nonexistent_structure_returns_404(api_client):
    response = api_client.get(f"/structures/{sid()}")
    assert response.status_code == 404


async def test_invalid_structure_id_shape_returns_422(api_client, zone_id):
    response = api_client.post(
        "/structures", json={"id": "Not Valid!", "name": "X", "parent_type": "zone", "parent_id": zone_id}
    )
    assert response.status_code == 422

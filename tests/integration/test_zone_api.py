"""API-level tests for the recursive Zone endpoints.

Zone has no table and no ORM model: every assertion here about hierarchy
comes back through the API (which itself reads OpenFGA), never from a
direct database query for zone data. A `Project` and `Client` row are
created directly via the ORM only because Zone creation validates that a
referenced parent project exists (no Project API exists yet).
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
from app.main import app


@pytest.fixture
def api_client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def project_id(fga_cleanup):
    session = SessionLocal()
    client_id = f"zt-client-{uuid.uuid4().hex[:8]}"
    proj_id = f"zt-project-{uuid.uuid4().hex[:8]}"
    session.add(Client(id=client_id, name=client_id))
    session.add(Project(id=proj_id, client_id=client_id, name=proj_id))
    session.commit()
    try:
        yield proj_id
    finally:
        # Every zone created off this project writes a zone.relationship.created
        # audit row keyed by the zone's own id (tracked in fga_cleanup as the
        # tuple's object "zone:<id>"), not by project_id/client_id — clean
        # those up too, not just the project/client rows.
        zone_audit_ids = [
            obj.split(":", 1)[1] for (_, _, obj) in fga_cleanup if obj.startswith("zone:")
        ]
        session.query(AuditEvent).filter(
            AuditEvent.resource_id.in_([proj_id, client_id, *zone_audit_ids])
        ).delete(synchronize_session=False)
        session.query(Project).filter(Project.id == proj_id).delete(synchronize_session=False)
        session.query(Client).filter(Client.id == client_id).delete(synchronize_session=False)
        session.commit()
        session.close()


@pytest.fixture
async def fga_cleanup():
    """Test bodies append (user, relation, object) tuples they wrote
    through the API (directly or indirectly); torn down here so no test
    data lingers in the OpenFGA store. Also consulted by the `project_id`
    fixture to find zone ids needing audit-row cleanup."""
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


def zid() -> str:
    return f"zt-{uuid.uuid4().hex[:8]}"


async def test_create_root_zone_under_project(api_client, project_id, fga_cleanup):
    zone_id = zid()

    response = api_client.post("/zones", json={"id": zone_id, "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{zone_id}"))

    assert response.status_code == 201
    assert response.json() == {"id": zone_id, "parent_type": "project", "parent_id": project_id}


async def test_create_sibling_zones_under_same_project(api_client, project_id, fga_cleanup):
    north, south = zid(), zid()
    for zone_id in (north, south):
        r = api_client.post("/zones", json={"id": zone_id, "parent_type": "project", "parent_id": project_id})
        assert r.status_code == 201
        fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{zone_id}"))

    response = api_client.get(f"/projects/{project_id}/zones")
    assert response.status_code == 200
    ids = {z["id"] for z in response.json()}
    assert ids == {north, south}


async def test_create_nested_zone_under_zone(api_client, project_id, fga_cleanup):
    north = zid()
    api_client.post("/zones", json={"id": north, "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{north}"))

    delhi = zid()
    response = api_client.post("/zones", json={"id": delhi, "parent_type": "zone", "parent_id": north})
    fga_cleanup.append((f"zone:{north}", "parent", f"zone:{delhi}"))

    assert response.status_code == 201
    assert response.json() == {"id": delhi, "parent_type": "zone", "parent_id": north}

    children = api_client.get(f"/zones/{north}/children").json()
    assert children["child_zones"] == [delhi]
    assert children["child_structures"] == []


async def test_deep_nesting_project_to_structure(api_client, project_id, fga_cleanup):
    """project -> zone:north -> zone:delhi -> zone:central -> structure,
    verifying each level purely through OpenFGA-backed API responses."""
    north, delhi, central = zid(), zid(), zid()
    structure_id = zid()

    r1 = api_client.post("/zones", json={"id": north, "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{north}"))
    r2 = api_client.post("/zones", json={"id": delhi, "parent_type": "zone", "parent_id": north})
    fga_cleanup.append((f"zone:{north}", "parent", f"zone:{delhi}"))
    r3 = api_client.post("/zones", json={"id": central, "parent_type": "zone", "parent_id": delhi})
    fga_cleanup.append((f"zone:{delhi}", "parent", f"zone:{central}"))
    assert r1.status_code == r2.status_code == r3.status_code == 201

    # No Structure API exists yet; write the structure-parent tuple directly
    # through the same authorization service the API itself uses, to prove
    # zones/{id}/children reports structure children generically.
    settings = get_settings()
    configuration = ClientConfiguration(
        api_url=settings.fga_api_url, store_id=settings.fga_store_id, authorization_model_id=settings.fga_model_id
    )
    fga_client = OpenFgaClient(configuration)
    await fga_client.write_tuples([ClientTuple(user=f"zone:{central}", relation="parent", object=f"structure:{structure_id}")])
    fga_cleanup.append((f"zone:{central}", "parent", f"structure:{structure_id}"))
    await fga_client.close()

    assert api_client.get(f"/zones/{north}").json() == {"id": north, "parent_type": "project", "parent_id": project_id}
    assert api_client.get(f"/zones/{delhi}").json() == {"id": delhi, "parent_type": "zone", "parent_id": north}
    assert api_client.get(f"/zones/{central}").json() == {"id": central, "parent_type": "zone", "parent_id": delhi}

    central_children = api_client.get(f"/zones/{central}/children").json()
    assert central_children["child_zones"] == []
    assert central_children["child_structures"] == [structure_id]


async def test_create_zone_with_nonexistent_project_parent_returns_404(api_client):
    response = api_client.post(
        "/zones", json={"id": zid(), "parent_type": "project", "parent_id": "does-not-exist-project"}
    )
    assert response.status_code == 404


async def test_create_zone_with_nonexistent_zone_parent_returns_404(api_client):
    response = api_client.post("/zones", json={"id": zid(), "parent_type": "zone", "parent_id": "does-not-exist-zone"})
    assert response.status_code == 404


async def test_create_zone_duplicate_same_parent_is_idempotent(api_client, project_id, fga_cleanup):
    zone_id = zid()
    body = {"id": zone_id, "parent_type": "project", "parent_id": project_id}

    first = api_client.post("/zones", json=body)
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{zone_id}"))
    second = api_client.post("/zones", json=body)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json() == second.json()


async def test_create_zone_duplicate_different_parent_returns_409(api_client, project_id, fga_cleanup):
    zone_id = zid()
    other_zone = zid()

    api_client.post("/zones", json={"id": zone_id, "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{zone_id}"))
    api_client.post("/zones", json={"id": other_zone, "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{other_zone}"))

    response = api_client.post("/zones", json={"id": zone_id, "parent_type": "zone", "parent_id": other_zone})
    assert response.status_code == 409


async def test_create_zone_self_parent_returns_422_circular(api_client):
    zone_id = zid()
    response = api_client.post("/zones", json={"id": zone_id, "parent_type": "zone", "parent_id": zone_id})
    assert response.status_code == 422
    assert "circular" in response.json()["detail"].lower()


async def test_recreating_ancestor_zone_pointed_at_its_own_descendant_is_rejected(api_client, project_id, fga_cleanup):
    """Reproduces the spec's classic cycle: A -> B -> C, then attempting to
    make A's parent be C (its own descendant) — closing the loop. Rejected
    as a 409 (A already exists with a different, established parent),
    which is precisely what prevents the cycle from ever being written."""
    a, b, c = zid(), zid(), zid()

    r_a = api_client.post("/zones", json={"id": a, "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{a}"))
    r_b = api_client.post("/zones", json={"id": b, "parent_type": "zone", "parent_id": a})
    fga_cleanup.append((f"zone:{a}", "parent", f"zone:{b}"))
    r_c = api_client.post("/zones", json={"id": c, "parent_type": "zone", "parent_id": b})
    fga_cleanup.append((f"zone:{b}", "parent", f"zone:{c}"))
    assert r_a.status_code == r_b.status_code == r_c.status_code == 201

    response = api_client.post("/zones", json={"id": a, "parent_type": "zone", "parent_id": c})
    assert response.status_code == 409

    # The cycle must not have been written: A's parent is still the project.
    assert api_client.get(f"/zones/{a}").json()["parent_type"] == "project"


async def test_get_nonexistent_zone_returns_404(api_client):
    response = api_client.get(f"/zones/{zid()}")
    assert response.status_code == 404


async def test_get_children_of_nonexistent_zone_returns_404(api_client):
    response = api_client.get(f"/zones/{zid()}/children")
    assert response.status_code == 404


async def test_invalid_zone_id_shape_returns_422(api_client, project_id):
    response = api_client.post(
        "/zones", json={"id": "Not A Valid Slug!", "parent_type": "project", "parent_id": project_id}
    )
    assert response.status_code == 422

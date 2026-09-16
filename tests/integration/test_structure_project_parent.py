"""Tests for direct Project -> Structure support (Step 12): a Structure's
OpenFGA parent can now be either a Project directly or a Zone, coexisting
in the same system:

    Client -> Project -> Structure                (this file's focus)
    Client -> Project -> Zone -> ... -> Structure  (unchanged, see
                                                     test_structures_api.py,
                                                     test_zone_api.py)

No Zone is ever created or implied for the direct-parent case — the
`zones` table (app/db/models/zone.py) only mirrors a zone's name and is
irrelevant here.
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


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def project_id(fga_cleanup):
    """A bare client/project pair (no Zone) that direct structures attach to."""
    session = SessionLocal()
    client_id = f"dp-client-{uuid.uuid4().hex[:8]}"
    proj_id = f"dp-project-{uuid.uuid4().hex[:8]}"
    session.add(Client(id=client_id, name=f"Direct-parent test client {client_id}"))
    session.add(Project(id=proj_id, client_id=client_id, name=proj_id))
    session.commit()
    try:
        yield proj_id
    finally:
        session.query(AuditEvent).filter(AuditEvent.resource_id.in_([proj_id, client_id])).delete(
            synchronize_session=False
        )
        session.query(Project).filter(Project.id == proj_id).delete(synchronize_session=False)
        session.query(Client).filter(Client.id == client_id).delete(synchronize_session=False)
        session.commit()
        session.close()


def sid() -> str:
    return f"dp-{uuid.uuid4().hex[:8]}"


def grant(api_client, fga_cleanup, user, resource_type, resource_id, permission="viewer"):
    r = api_client.post(
        "/authorization/grant",
        json={"user": user, "resource_type": resource_type, "resource_id": resource_id, "permission": permission},
    )
    fga_cleanup.append((user, permission, f"{resource_type}:{resource_id}"))
    return r


def check(api_client, user, resource_type, resource_id, permission="viewer"):
    r = api_client.get(
        "/authorization/check",
        params={"user": user, "resource_type": resource_type, "resource_id": resource_id, "permission": permission},
    )
    assert r.status_code == 200
    return r.json()["allowed"]


async def test_create_structure_with_project_parent_returns_201(api_client, project_id, fga_cleanup):
    structure_id = sid()
    response = api_client.post(
        "/structures",
        json={"id": structure_id, "name": "Direct Structure", "parent_type": "project", "parent_id": project_id},
    )
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{structure_id}"))

    assert response.status_code == 201
    body = response.json()
    assert body["parent_type"] == "project"
    assert body["parent_id"] == project_id

    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(AuditEvent.resource_id == structure_id).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id == structure_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


async def test_get_structure_reports_project_parent(api_client, project_id, fga_cleanup):
    structure_id = sid()
    api_client.post(
        "/structures", json={"id": structure_id, "name": "X", "parent_type": "project", "parent_id": project_id}
    )
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{structure_id}"))

    response = api_client.get(f"/structures/{structure_id}")
    assert response.status_code == 200
    assert response.json()["parent_type"] == "project"
    assert response.json()["parent_id"] == project_id

    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(AuditEvent.resource_id == structure_id).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id == structure_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


async def test_create_structure_with_nonexistent_project_returns_404(api_client):
    response = api_client.post(
        "/structures",
        json={"id": sid(), "name": "X", "parent_type": "project", "parent_id": "no-such-project-at-all"},
    )
    assert response.status_code == 404


async def test_project_level_grant_reaches_direct_structures(api_client, project_id, fga_cleanup):
    s1, s2 = sid(), sid()
    api_client.post("/structures", json={"id": s1, "name": "S1", "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{s1}"))
    api_client.post("/structures", json={"id": s2, "name": "S2", "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{s2}"))

    user = "user:direct-parent-admin"
    assert grant(api_client, fga_cleanup, user, "project", project_id).status_code == 201

    assert check(api_client, user, "structure", s1) is True
    assert check(api_client, user, "structure", s2) is True

    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(AuditEvent.resource_id.in_([s1, s2])).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id.in_([s1, s2])).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


async def test_structure_only_grant_has_no_upward_access_to_project(api_client, project_id, fga_cleanup):
    structure_id = sid()
    api_client.post(
        "/structures",
        json={"id": structure_id, "name": "X", "parent_type": "project", "parent_id": project_id},
    )
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{structure_id}"))

    user = "user:direct-structure-only"
    assert grant(api_client, fga_cleanup, user, "structure", structure_id).status_code == 201

    assert check(api_client, user, "structure", structure_id) is True
    assert check(api_client, user, "project", project_id) is False

    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(AuditEvent.resource_id == structure_id).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id == structure_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


async def test_direct_structure_isolated_from_other_projects(api_client, project_id, fga_cleanup):
    """A user with access to one project's direct structure must not reach
    a structure under a completely different project."""
    structure_id = sid()
    api_client.post(
        "/structures",
        json={"id": structure_id, "name": "X", "parent_type": "project", "parent_id": project_id},
    )
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{structure_id}"))

    other_session = SessionLocal()
    other_client_id = f"dp-client-{uuid.uuid4().hex[:8]}"
    other_project_id = f"dp-project-{uuid.uuid4().hex[:8]}"
    other_structure_id = sid()
    other_session.add(Client(id=other_client_id, name=f"Other {other_client_id}"))
    other_session.add(Project(id=other_project_id, client_id=other_client_id, name=other_project_id))
    other_session.commit()
    other_session.close()

    api_client.post(
        "/structures",
        json={"id": other_structure_id, "name": "Y", "parent_type": "project", "parent_id": other_project_id},
    )
    fga_cleanup.append((f"project:{other_project_id}", "parent", f"structure:{other_structure_id}"))

    user = "user:direct-isolation-test"
    grant(api_client, fga_cleanup, user, "project", project_id)

    assert check(api_client, user, "structure", structure_id) is True
    assert check(api_client, user, "structure", other_structure_id) is False
    assert check(api_client, user, "project", other_project_id) is False

    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(
            AuditEvent.resource_id.in_([structure_id, other_structure_id, other_project_id, other_client_id])
        ).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id.in_([structure_id, other_structure_id])).delete(
            synchronize_session=False
        )
        session.query(Project).filter(Project.id == other_project_id).delete(synchronize_session=False)
        session.query(Client).filter(Client.id == other_client_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


async def test_tree_shows_direct_structures_under_project_with_no_fake_zone(api_client, project_id, fga_cleanup):
    s1, s2 = sid(), sid()
    api_client.post("/structures", json={"id": s1, "name": "One", "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{s1}"))
    api_client.post("/structures", json={"id": s2, "name": "Two", "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{s2}"))

    client_id = SessionLocal().query(Project).filter(Project.id == project_id).one().client_id

    user = "user:direct-tree-test"
    grant(api_client, fga_cleanup, user, "project", project_id)

    response = api_client.get(f"/clients/{client_id}/tree", params={"user": user})
    assert response.status_code == 200
    tree = response.json()

    assert len(tree["children"]) == 1
    project_node = tree["children"][0]
    assert project_node["type"] == "project"
    assert project_node["id"] == project_id

    child_types = {c["type"] for c in project_node["children"]}
    assert child_types == {"structure"}
    child_ids = {c["id"] for c in project_node["children"]}
    assert child_ids == {s1, s2}

    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(AuditEvent.resource_id.in_([s1, s2])).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id.in_([s1, s2])).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


async def test_mixed_project_with_both_direct_structure_and_zone_branch(api_client, project_id, fga_cleanup):
    """Project
       ├── Structure (direct)
       └── Zone
             └── Structure
    both branches must appear correctly in the same tree."""
    direct_structure = sid()
    zone_id = sid()
    zoned_structure = sid()

    api_client.post(
        "/structures",
        json={"id": direct_structure, "name": "Direct", "parent_type": "project", "parent_id": project_id},
    )
    fga_cleanup.append((f"project:{project_id}", "parent", f"structure:{direct_structure}"))

    api_client.post("/zones", json={"id": zone_id, "parent_type": "project", "parent_id": project_id})
    fga_cleanup.append((f"project:{project_id}", "parent", f"zone:{zone_id}"))

    api_client.post(
        "/structures",
        json={"id": zoned_structure, "name": "Zoned", "parent_type": "zone", "parent_id": zone_id},
    )
    fga_cleanup.append((f"zone:{zone_id}", "parent", f"structure:{zoned_structure}"))

    client_id = SessionLocal().query(Project).filter(Project.id == project_id).one().client_id
    user = "user:direct-mixed-test"
    grant(api_client, fga_cleanup, user, "project", project_id)

    response = api_client.get(f"/clients/{client_id}/tree", params={"user": user})
    assert response.status_code == 200
    project_node = response.json()["children"][0]

    types_by_id = {c["id"]: c["type"] for c in project_node["children"]}
    assert types_by_id[direct_structure] == "structure"
    assert types_by_id[zone_id] == "zone"

    zone_node = next(c for c in project_node["children"] if c["id"] == zone_id)
    assert [c["id"] for c in zone_node["children"]] == [zoned_structure]

    session = SessionLocal()
    try:
        session.query(AuditEvent).filter(
            AuditEvent.resource_id.in_([direct_structure, zoned_structure, zone_id])
        ).delete(synchronize_session=False)
        session.query(Structure).filter(Structure.id.in_([direct_structure, zoned_structure])).delete(
            synchronize_session=False
        )
        session.query(Zone).filter(Zone.id == zone_id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()

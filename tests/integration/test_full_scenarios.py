"""Capstone end-to-end suite: exercises the complete public API surface
(clients -> projects -> zones -> structures -> authorization -> tree) with
no direct DB/OpenFGA fixture shortcuts other than the two things no API
exposes by design: Zone has no business row (there is nothing to insert),
and there is no "list all clients a super-admin can see" endpoint.

This is the one test file where Client -> Project -> Zone -> Structure is
built entirely through HTTP calls, now that the Project API (added this
step) closes the last gap. Covers, in one place, every axis called out for
Step 11: client/project/zone/nested-zone/structure-level access, cross-
client and cross-branch denial, no-upward inheritance, fail-closed,
anti-enumeration, and audit verification. Step-specific edge cases
(duplicates, cycles, invalid input, idempotency) remain in each step's own
test file and are not repeated here.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.tuple import ClientTuple

from app.authorization.exceptions import AuthorizationServiceUnavailableError
from app.authorization.service import AuthorizationService
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
def scenario(api_client, fga_cleanup):
    """Builds two independent client hierarchies entirely through the
    public API:

        client_a (own project/zone/structure branch, deeply nested)
        client_b (separate branch, used only for cross-client checks)
    """
    ids = {k: _uid(f"fs-{k}".replace("_", "-")) for k in ["client_a", "project_a", "client_b", "project_b"]}
    ids.update({k: _uid("fs-zone") for k in ["zone_north", "zone_south", "zone_delhi", "zone_central", "zone_other"]})
    ids.update({k: _uid("fs-structure") for k in ["structure_yamuna", "structure_south", "structure_other"]})

    def post(path, json):
        r = api_client.post(path, json=json)
        assert r.status_code == 201, f"{path} {json}: {r.status_code} {r.text}"
        return r

    # Client.name is globally unique (uq_clients_name); derive it from the
    # per-test random id so concurrent/repeated runs (and any real demo data
    # from scripts/seed_demo.py sitting in the same database) never collide.
    post("/clients", {"id": ids["client_a"], "name": f"Full Scenario Client A {ids['client_a']}"})
    post("/clients", {"id": ids["client_b"], "name": f"Full Scenario Client B {ids['client_b']}"})
    post("/projects", {"id": ids["project_a"], "client_id": ids["client_a"], "name": "Project A"})
    post("/projects", {"id": ids["project_b"], "client_id": ids["client_b"], "name": "Project B"})
    fga_cleanup.append((f"client:{ids['client_a']}", "parent", f"project:{ids['project_a']}"))
    fga_cleanup.append((f"client:{ids['client_b']}", "parent", f"project:{ids['project_b']}"))

    def zone(id_, parent_type, parent_id):
        post("/zones", {"id": id_, "parent_type": parent_type, "parent_id": parent_id})
        fga_cleanup.append((f"{parent_type}:{parent_id}", "parent", f"zone:{id_}"))

    zone(ids["zone_north"], "project", ids["project_a"])
    zone(ids["zone_south"], "project", ids["project_a"])
    zone(ids["zone_delhi"], "zone", ids["zone_north"])
    zone(ids["zone_central"], "zone", ids["zone_delhi"])
    zone(ids["zone_other"], "project", ids["project_b"])

    def structure(id_, name, zone_id):
        post("/structures", {"id": id_, "name": name, "parent_type": "zone", "parent_id": zone_id})
        fga_cleanup.append((f"zone:{zone_id}", "parent", f"structure:{id_}"))

    structure(ids["structure_yamuna"], "Yamuna Bridge", ids["zone_central"])
    structure(ids["structure_south"], "South Bridge", ids["zone_south"])
    structure(ids["structure_other"], "Other Bridge", ids["zone_other"])

    try:
        yield ids
    finally:
        session = SessionLocal()
        try:
            all_ids = list(ids.values())
            session.query(AuditEvent).filter(AuditEvent.resource_id.in_(all_ids)).delete(synchronize_session=False)
            session.query(Structure).filter(
                Structure.id.in_(
                    [ids["structure_yamuna"], ids["structure_south"], ids["structure_other"]]
                )
            ).delete(synchronize_session=False)
            session.query(Zone).filter(
                Zone.id.in_(
                    [
                        ids["zone_north"],
                        ids["zone_south"],
                        ids["zone_delhi"],
                        ids["zone_central"],
                        ids["zone_other"],
                    ]
                )
            ).delete(synchronize_session=False)
            session.query(Project).filter(Project.id.in_([ids["project_a"], ids["project_b"]])).delete(
                synchronize_session=False
            )
            session.query(Client).filter(Client.id.in_([ids["client_a"], ids["client_b"]])).delete(
                synchronize_session=False
            )
            session.commit()
        finally:
            session.close()


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


def flatten_ids(node):
    out = {node["id"]}
    for child in node.get("children", []):
        out |= flatten_ids(child)
    return out


# --- Client/project/zone/nested-zone/structure authorization scenarios ---


async def test_client_level_access_reaches_every_descendant(api_client, scenario, fga_cleanup):
    user = "user:full-client"
    grant(api_client, fga_cleanup, user, "client", scenario["client_a"])

    for resource_type, resource_id in [
        ("client", scenario["client_a"]),
        ("project", scenario["project_a"]),
        ("zone", scenario["zone_north"]),
        ("zone", scenario["zone_delhi"]),
        ("zone", scenario["zone_central"]),
        ("zone", scenario["zone_south"]),
        ("structure", scenario["structure_yamuna"]),
        ("structure", scenario["structure_south"]),
    ]:
        assert check(api_client, user, resource_type, resource_id) is True


async def test_project_level_access_reaches_descendants_not_ancestor(api_client, scenario, fga_cleanup):
    user = "user:full-project"
    grant(api_client, fga_cleanup, user, "project", scenario["project_a"])

    assert check(api_client, user, "zone", scenario["zone_north"]) is True
    assert check(api_client, user, "structure", scenario["structure_yamuna"]) is True
    assert check(api_client, user, "client", scenario["client_a"]) is False  # no upward inheritance


async def test_zone_level_access_reaches_nested_zones_and_structures_not_ancestors(
    api_client, scenario, fga_cleanup
):
    user = "user:full-zone"
    grant(api_client, fga_cleanup, user, "zone", scenario["zone_north"])

    assert check(api_client, user, "zone", scenario["zone_delhi"]) is True  # nested zone
    assert check(api_client, user, "zone", scenario["zone_central"]) is True  # deeply nested zone
    assert check(api_client, user, "structure", scenario["structure_yamuna"]) is True

    assert check(api_client, user, "project", scenario["project_a"]) is False  # no upward inheritance
    assert check(api_client, user, "client", scenario["client_a"]) is False  # no upward inheritance
    assert check(api_client, user, "zone", scenario["zone_south"]) is False  # no cross-branch access


async def test_structure_level_access_is_isolated(api_client, scenario, fga_cleanup):
    user = "user:full-structure"
    grant(api_client, fga_cleanup, user, "structure", scenario["structure_yamuna"])

    assert check(api_client, user, "structure", scenario["structure_yamuna"]) is True
    assert check(api_client, user, "zone", scenario["zone_central"]) is False
    assert check(api_client, user, "zone", scenario["zone_north"]) is False
    assert check(api_client, user, "project", scenario["project_a"]) is False
    assert check(api_client, user, "client", scenario["client_a"]) is False


# --- Cross-client and cross-branch denial ---


async def test_cross_client_denial(api_client, scenario, fga_cleanup):
    user = "user:full-cross-client"
    grant(api_client, fga_cleanup, user, "client", scenario["client_a"])

    assert check(api_client, user, "client", scenario["client_b"]) is False
    assert check(api_client, user, "project", scenario["project_b"]) is False
    assert check(api_client, user, "zone", scenario["zone_other"]) is False
    assert check(api_client, user, "structure", scenario["structure_other"]) is False


async def test_cross_branch_denial_within_same_project(api_client, scenario, fga_cleanup):
    user = "user:full-cross-branch"
    grant(api_client, fga_cleanup, user, "zone", scenario["zone_north"])

    assert check(api_client, user, "zone", scenario["zone_south"]) is False
    assert check(api_client, user, "structure", scenario["structure_south"]) is False


# --- Zero-grant denial ---


async def test_zero_grant_denies_everything(api_client, scenario):
    user = "user:full-nobody"
    assert check(api_client, user, "client", scenario["client_a"]) is False
    assert check(api_client, user, "structure", scenario["structure_yamuna"]) is False


# --- Fail-closed ---


async def test_check_and_tree_fail_closed_when_openfga_unreachable(monkeypatch, api_client, scenario, fga_cleanup):
    user = "user:full-failclosed"
    grant(api_client, fga_cleanup, user, "client", scenario["client_a"])

    async def broken_check(self, *args, **kwargs):
        raise AuthorizationServiceUnavailableError("simulated outage")

    monkeypatch.setattr(AuthorizationService, "check", broken_check)

    check_response = api_client.get(
        "/authorization/check",
        params={"user": user, "resource_type": "client", "resource_id": scenario["client_a"], "permission": "viewer"},
    )
    assert check_response.status_code == 503

    tree_response = api_client.get(f"/clients/{scenario['client_a']}/tree", params={"user": user})
    assert tree_response.status_code == 503


# --- Anti-enumeration ---


async def test_anti_enumeration_nonexistent_vs_unauthorized_client(api_client, scenario):
    unauthorized = api_client.get(f"/clients/{scenario['client_a']}/tree", params={"user": "user:full-intruder"})
    session = SessionLocal()
    try:
        nonexistent_id = "fs-does-not-exist"
        nonexistent = api_client.get(f"/clients/{nonexistent_id}/tree", params={"user": "user:full-intruder"})

        assert unauthorized.status_code == nonexistent.status_code == 404
        assert set(unauthorized.json().keys()) == set(nonexistent.json().keys())
    finally:
        session.query(AuditEvent).filter(AuditEvent.resource_id == "fs-does-not-exist").delete(
            synchronize_session=False
        )
        session.commit()
        session.close()


def test_structure_get_has_no_user_scoped_authorization(api_client, scenario):
    """GET /structures/{id} (like the other CRUD read endpoints) takes no
    `user` parameter and is not access-controlled per caller — only
    /authorization/check and /clients/{id}/tree are user-aware. Documented
    here explicitly so this isn't mistaken for an anti-enumeration gap: a
    real deployment would put a real authentication/authorization layer in
    front of all business-data reads, which is out of scope for this PoC."""
    assert api_client.get(f"/structures/{scenario['structure_yamuna']}").status_code == 200
    assert api_client.get("/structures/fs-does-not-exist-structure").status_code == 404


# --- Tree pruning ---


async def test_tree_is_correctly_pruned_for_a_zone_level_grant(api_client, scenario, fga_cleanup):
    user = "user:full-tree"
    grant(api_client, fga_cleanup, user, "zone", scenario["zone_north"])

    response = api_client.get(f"/clients/{scenario['client_a']}/tree", params={"user": user})
    assert response.status_code == 200
    visible = flatten_ids(response.json())

    assert scenario["zone_north"] in visible
    assert scenario["zone_delhi"] in visible
    assert scenario["zone_central"] in visible
    assert scenario["structure_yamuna"] in visible

    assert scenario["zone_south"] not in visible
    assert scenario["structure_south"] not in visible


# --- Audit verification ---


async def test_audit_trail_covers_creation_grant_and_tree_access(api_client, scenario, fga_cleanup):
    user = "user:full-audit"
    grant(api_client, fga_cleanup, user, "client", scenario["client_a"])
    api_client.get(f"/clients/{scenario['client_a']}/tree", params={"user": user})

    session = SessionLocal()
    try:
        event_types = {
            row[0]
            for row in session.query(AuditEvent.event_type)
            .filter(AuditEvent.resource_id.in_(list(scenario.values())))
            .distinct()
        }
        assert "client.created" in event_types
        assert "project.created" in event_types
        assert "zone.relationship.created" in event_types
        assert "structure.created" in event_types
        assert "authorization.grant.created" in event_types
        assert "tree.access" in event_types
    finally:
        session.close()

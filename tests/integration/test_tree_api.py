"""API-level tests for GET /clients/{client_id}/tree.

Hierarchy built per test (matches the project's canonical example):

    client_a (Govt of India)
      └── project_a (Indian Railway)
            ├── zone_north
            │     └── zone_delhi
            │           └── zone_central
            │                 ├── structure_yamuna
            │                 └── structure_agra
            ├── zone_south
            │     └── structure_south
            └── zone_western
                  └── structure_western

    client_b (isolated second client, for cross-client tests)
      └── project_b
            └── zone_other
                  └── structure_other

No Project-creation API exists yet, so `project:<id>#parent@client:<id>`
is written directly via the authorization service — the one tuple such an
endpoint would produce — exactly as in Step 9's tests. Everything else
(zones, structures) goes through the real APIs.
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
async def hierarchy(api_client, fga_cleanup):
    session = SessionLocal()
    ids = {
        "client_a": _uid("tt-client"),
        "project_a": _uid("tt-project"),
        "client_b": _uid("tt-client"),
        "project_b": _uid("tt-project"),
        "zone_north": _uid("tt-zone"),
        "zone_south": _uid("tt-zone"),
        "zone_western": _uid("tt-zone"),
        "zone_delhi": _uid("tt-zone"),
        "zone_central": _uid("tt-zone"),
        "zone_other": _uid("tt-zone"),
        "structure_yamuna": _uid("tt-structure"),
        "structure_agra": _uid("tt-structure"),
        "structure_south": _uid("tt-structure"),
        "structure_western": _uid("tt-structure"),
        "structure_other": _uid("tt-structure"),
    }

    # Client.name is globally unique (uq_clients_name); derive it from the
    # per-test random id so concurrent/repeated runs (and any real demo data
    # from scripts/seed_demo.py sitting in the same database) never collide.
    session.add(Client(id=ids["client_a"], name=f"Tree Test Client A {ids['client_a']}"))
    session.add(Client(id=ids["client_b"], name=f"Tree Test Client B {ids['client_b']}"))
    session.add(Project(id=ids["project_a"], client_id=ids["client_a"], name="Indian Railway"))
    session.add(Project(id=ids["project_b"], client_id=ids["client_b"], name="Other Railway"))
    session.commit()

    settings = get_settings()
    configuration = ClientConfiguration(
        api_url=settings.fga_api_url, store_id=settings.fga_store_id, authorization_model_id=settings.fga_model_id
    )
    fga_client = OpenFgaClient(configuration)
    await fga_client.write_tuples(
        [
            ClientTuple(user=f"client:{ids['client_a']}", relation="parent", object=f"project:{ids['project_a']}"),
            ClientTuple(user=f"client:{ids['client_b']}", relation="parent", object=f"project:{ids['project_b']}"),
        ]
    )
    await fga_client.close()
    fga_cleanup.append((f"client:{ids['client_a']}", "parent", f"project:{ids['project_a']}"))
    fga_cleanup.append((f"client:{ids['client_b']}", "parent", f"project:{ids['project_b']}"))

    def create_zone(zone_id: str, parent_type: str, parent_id: str) -> None:
        r = api_client.post("/zones", json={"id": zone_id, "parent_type": parent_type, "parent_id": parent_id})
        assert r.status_code == 201, r.text
        fga_cleanup.append((f"{parent_type}:{parent_id}", "parent", f"zone:{zone_id}"))

    def create_structure(structure_id: str, name: str, zone_id: str) -> None:
        r = api_client.post(
            "/structures", json={"id": structure_id, "name": name, "parent_type": "zone", "parent_id": zone_id}
        )
        assert r.status_code == 201, r.text
        fga_cleanup.append((f"zone:{zone_id}", "parent", f"structure:{structure_id}"))

    create_zone(ids["zone_north"], "project", ids["project_a"])
    create_zone(ids["zone_south"], "project", ids["project_a"])
    create_zone(ids["zone_western"], "project", ids["project_a"])
    create_zone(ids["zone_delhi"], "zone", ids["zone_north"])
    create_zone(ids["zone_central"], "zone", ids["zone_delhi"])
    create_zone(ids["zone_other"], "project", ids["project_b"])

    create_structure(ids["structure_yamuna"], "Yamuna Bridge", ids["zone_central"])
    create_structure(ids["structure_agra"], "Agra Bridge", ids["zone_central"])
    create_structure(ids["structure_south"], "South Bridge", ids["zone_south"])
    create_structure(ids["structure_western"], "Western Bridge", ids["zone_western"])
    create_structure(ids["structure_other"], "Other Bridge", ids["zone_other"])

    try:
        yield ids
    finally:
        session.query(AuditEvent).filter(AuditEvent.resource_id.in_(list(ids.values()))).delete(
            synchronize_session=False
        )
        session.query(Structure).filter(
            Structure.id.in_(
                [
                    ids["structure_yamuna"],
                    ids["structure_agra"],
                    ids["structure_south"],
                    ids["structure_western"],
                    ids["structure_other"],
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
        session.close()


def grant(api_client, fga_cleanup, user: str, resource_type: str, resource_id: str, permission: str = "viewer"):
    response = api_client.post(
        "/authorization/grant",
        json={"user": user, "resource_type": resource_type, "resource_id": resource_id, "permission": permission},
    )
    fga_cleanup.append((user, permission, f"{resource_type}:{resource_id}"))
    return response


def get_tree(api_client, client_id: str, user: str):
    return api_client.get(f"/clients/{client_id}/tree", params={"user": user})


def node_ids_by_type(node: dict) -> dict[str, set[str]]:
    """Flattens a tree response into {type: {ids}} for easy membership assertions."""
    result: dict[str, set[str]] = {}

    def walk(n: dict) -> None:
        result.setdefault(n["type"], set()).add(n["id"])
        for child in n["children"]:
            walk(child)

    walk(node)
    return result


async def test_client_level_user_sees_complete_hierarchy(api_client, hierarchy, fga_cleanup):
    user = "user:parth"
    assert grant(api_client, fga_cleanup, user, "client", hierarchy["client_a"]).status_code == 201

    response = get_tree(api_client, hierarchy["client_a"], user)
    assert response.status_code == 200

    ids = node_ids_by_type(response.json())
    assert ids["client"] == {hierarchy["client_a"]}
    assert ids["project"] == {hierarchy["project_a"]}
    assert ids["zone"] == {
        hierarchy["zone_north"],
        hierarchy["zone_south"],
        hierarchy["zone_western"],
        hierarchy["zone_delhi"],
        hierarchy["zone_central"],
    }
    assert ids["structure"] == {
        hierarchy["structure_yamuna"],
        hierarchy["structure_agra"],
        hierarchy["structure_south"],
        hierarchy["structure_western"],
    }


async def test_project_level_user_sees_only_that_project_and_descendants(api_client, hierarchy, fga_cleanup):
    """Second project under the same client (project_b, via client_b in this
    fixture) must not appear for a grant scoped to project_a."""
    user = "user:bob"
    assert grant(api_client, fga_cleanup, user, "project", hierarchy["project_a"]).status_code == 201

    response = get_tree(api_client, hierarchy["client_a"], user)
    assert response.status_code == 200
    ids = node_ids_by_type(response.json())

    assert ids["project"] == {hierarchy["project_a"]}
    assert hierarchy["structure_yamuna"] in ids["structure"]
    assert hierarchy["structure_south"] in ids["structure"]
    assert hierarchy["structure_western"] in ids["structure"]

    # The other client's tree must be completely invisible to this user.
    assert get_tree(api_client, hierarchy["client_b"], user).status_code == 404


async def test_zone_level_user_sees_only_that_zone_and_descendants(api_client, hierarchy, fga_cleanup):
    user = "user:carol"
    assert grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_north"]).status_code == 201

    response = get_tree(api_client, hierarchy["client_a"], user)
    assert response.status_code == 200
    ids = node_ids_by_type(response.json())

    # Ancestor pass-through: client and project nodes still render (they're
    # the path to what carol can see) even though she has no grant on them.
    assert ids["client"] == {hierarchy["client_a"]}
    assert ids["project"] == {hierarchy["project_a"]}

    assert ids["zone"] == {hierarchy["zone_north"], hierarchy["zone_delhi"], hierarchy["zone_central"]}
    assert hierarchy["zone_south"] not in ids["zone"]
    assert hierarchy["zone_western"] not in ids["zone"]

    assert ids["structure"] == {hierarchy["structure_yamuna"], hierarchy["structure_agra"]}
    assert hierarchy["structure_south"] not in ids.get("structure", set())
    assert hierarchy["structure_western"] not in ids.get("structure", set())


async def test_nested_zone_grant_prunes_correctly(api_client, hierarchy, fga_cleanup):
    """A grant two levels deep (zone_delhi, itself nested under zone_north)
    must still surface zone_north as a pass-through container, while
    everything outside the delhi/central branch stays pruned."""
    user = "user:diana"
    assert grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_delhi"]).status_code == 201

    response = get_tree(api_client, hierarchy["client_a"], user)
    assert response.status_code == 200
    ids = node_ids_by_type(response.json())

    assert ids["zone"] == {hierarchy["zone_north"], hierarchy["zone_delhi"], hierarchy["zone_central"]}
    assert ids["structure"] == {hierarchy["structure_yamuna"], hierarchy["structure_agra"]}


async def test_structure_level_user_sees_only_that_structure(api_client, hierarchy, fga_cleanup):
    user = "user:erin"
    assert grant(api_client, fga_cleanup, user, "structure", hierarchy["structure_yamuna"]).status_code == 201

    response = get_tree(api_client, hierarchy["client_a"], user)
    assert response.status_code == 200
    ids = node_ids_by_type(response.json())

    assert ids.get("structure") == {hierarchy["structure_yamuna"]}
    # The sibling structure in the very same zone is pruned.
    assert hierarchy["structure_agra"] not in ids.get("structure", set())
    # Path down to it still renders as pass-through.
    assert ids["zone"] == {hierarchy["zone_north"], hierarchy["zone_delhi"], hierarchy["zone_central"]}


async def test_sibling_branches_remain_hidden(api_client, hierarchy, fga_cleanup):
    user = "user:frank"
    assert grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_south"]).status_code == 201

    response = get_tree(api_client, hierarchy["client_a"], user)
    ids = node_ids_by_type(response.json())

    assert ids["zone"] == {hierarchy["zone_south"]}
    assert ids["structure"] == {hierarchy["structure_south"]}


async def test_other_clients_remain_hidden(api_client, hierarchy, fga_cleanup):
    user = "user:grace"
    assert grant(api_client, fga_cleanup, user, "client", hierarchy["client_a"]).status_code == 201

    # grace has no grant anywhere in client_b's tree.
    response = get_tree(api_client, hierarchy["client_b"], user)
    assert response.status_code == 404


async def test_zero_access_user_gets_404(api_client, hierarchy):
    response = get_tree(api_client, hierarchy["client_a"], "user:nobody")
    assert response.status_code == 404


async def test_nonexistent_client_gets_identical_404(api_client, hierarchy):
    """Anti-enumeration: same status and same detail shape whether the
    client truly doesn't exist or the user simply lacks access to it."""
    nonexistent_id = "this-client-does-not-exist"
    try:
        unauthorized = get_tree(api_client, hierarchy["client_a"], "user:nobody")
        nonexistent = get_tree(api_client, nonexistent_id, "user:nobody")

        assert unauthorized.status_code == nonexistent.status_code == 404
        assert set(unauthorized.json().keys()) == set(nonexistent.json().keys())
    finally:
        # get_client_tree audits a denial for the nonexistent id too, keyed
        # by a literal not tracked in the `hierarchy` fixture's cleanup.
        session = SessionLocal()
        session.query(AuditEvent).filter(AuditEvent.resource_id == nonexistent_id).delete(
            synchronize_session=False
        )
        session.commit()
        session.close()


async def test_tree_fails_closed_when_openfga_unreachable(monkeypatch, api_client, hierarchy, fga_cleanup):
    user = "user:parth"
    grant(api_client, fga_cleanup, user, "client", hierarchy["client_a"])

    async def broken_check(self, *args, **kwargs):
        raise AuthorizationServiceUnavailableError("simulated outage")

    monkeypatch.setattr(AuthorizationService, "check", broken_check)

    response = get_tree(api_client, hierarchy["client_a"], user)
    assert response.status_code == 503


async def test_audit_events_recorded_for_success_and_denial(api_client, hierarchy, fga_cleanup):
    user = "user:henry"
    grant(api_client, fga_cleanup, user, "client", hierarchy["client_a"])
    get_tree(api_client, hierarchy["client_a"], user)
    get_tree(api_client, hierarchy["client_a"], "user:intruder")

    session = SessionLocal()
    try:
        success_event = (
            session.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "tree.access",
                AuditEvent.actor == user,
                AuditEvent.resource_id == hierarchy["client_a"],
            )
            .one()
        )
        assert success_event.result == "success"
        assert success_event.event_metadata is None

        denied_event = (
            session.query(AuditEvent)
            .filter(
                AuditEvent.event_type == "tree.access",
                AuditEvent.actor == "user:intruder",
                AuditEvent.resource_id == hierarchy["client_a"],
            )
            .one()
        )
        assert denied_event.result == "denied"
        # No secrets/PII beyond the internal reason code.
        assert denied_event.event_metadata == {"reason": "unauthorized"}
    finally:
        session.close()

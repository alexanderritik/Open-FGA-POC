"""API-level tests for /authorization/{check,grant} demonstrating the full
authorization path Client -> Project -> recursive Zone -> Structure, using
only the public APIs (plus one direct tuple write standing in for the
Project-creation API, which doesn't exist yet — see the `hierarchy`
fixture docstring).

Hierarchy built per test:

    client_a
      └── project_a
            ├── zone_north
            │     └── zone_delhi
            │           └── zone_central
            │                 └── structure
            └── zone_south      (sibling of zone_north)

    client_b
      └── project_b
            └── zone_other      (separate branch entirely, for cross-client tests)
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
    """Builds the two-branch hierarchy described in this module's docstring.

    No Project-creation API exists yet (out of scope through Step 9), so
    the `project:<id>#parent@client:<id>` tuple — what such an endpoint
    would write — is created directly here via a raw OpenFGA write,
    exactly like zone-under-project tuples in Step 8's tests stood in for
    a not-yet-built Structure API. Everything else (zones, the structure)
    goes through the real API.
    """
    session = SessionLocal()
    ids = {
        "client_a": _uid("aa-client"),
        "project_a": _uid("aa-project"),
        "client_b": _uid("aa-client"),
        "project_b": _uid("aa-project"),
        "zone_north": _uid("aa-zone"),
        "zone_south": _uid("aa-zone"),
        "zone_delhi": _uid("aa-zone"),
        "zone_central": _uid("aa-zone"),
        "zone_other": _uid("aa-zone"),
        "structure": _uid("aa-structure"),
    }

    session.add(Client(id=ids["client_a"], name=ids["client_a"]))
    session.add(Client(id=ids["client_b"], name=ids["client_b"]))
    session.add(Project(id=ids["project_a"], client_id=ids["client_a"], name=ids["project_a"]))
    session.add(Project(id=ids["project_b"], client_id=ids["client_b"], name=ids["project_b"]))
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

    create_zone(ids["zone_north"], "project", ids["project_a"])
    create_zone(ids["zone_south"], "project", ids["project_a"])
    create_zone(ids["zone_delhi"], "zone", ids["zone_north"])
    create_zone(ids["zone_central"], "zone", ids["zone_delhi"])
    create_zone(ids["zone_other"], "project", ids["project_b"])

    r = api_client.post(
        "/structures",
        json={"id": ids["structure"], "name": "Bridge", "parent_type": "zone", "parent_id": ids["zone_central"]},
    )
    assert r.status_code == 201, r.text
    fga_cleanup.append((f"zone:{ids['zone_central']}", "parent", f"structure:{ids['structure']}"))

    try:
        yield ids
    finally:
        session.query(AuditEvent).filter(AuditEvent.resource_id.in_(list(ids.values()))).delete(
            synchronize_session=False
        )
        session.query(Structure).filter(Structure.id == ids["structure"]).delete(synchronize_session=False)
        session.query(Project).filter(Project.id.in_([ids["project_a"], ids["project_b"]])).delete(
            synchronize_session=False
        )
        session.query(Client).filter(Client.id.in_([ids["client_a"], ids["client_b"]])).delete(
            synchronize_session=False
        )
        session.commit()
        session.close()


def check(api_client, user: str, resource_type: str, resource_id: str, permission: str = "viewer") -> bool:
    response = api_client.get(
        "/authorization/check",
        params={"user": user, "resource_type": resource_type, "resource_id": resource_id, "permission": permission},
    )
    assert response.status_code == 200, response.text
    return response.json()["allowed"]


def grant(api_client, fga_cleanup, user: str, resource_type: str, resource_id: str, permission: str = "viewer"):
    response = api_client.post(
        "/authorization/grant",
        json={"user": user, "resource_type": resource_type, "resource_id": resource_id, "permission": permission},
    )
    # Track for cleanup regardless of outcome — a 404 writes nothing, and
    # deleting a tuple that was never written (or already revoked) is a
    # harmless no-op in the fga_cleanup fixture's teardown.
    fga_cleanup.append((user, permission, f"{resource_type}:{resource_id}"))
    return response


def revoke(api_client, user: str, resource_type: str, resource_id: str, permission: str = "viewer"):
    return api_client.delete(
        "/authorization/grant",
        params={"user": user, "resource_type": resource_type, "resource_id": resource_id, "permission": permission},
    )


async def test_zero_grant_denies_everything(api_client, hierarchy):
    user = "user:nobody"
    assert check(api_client, user, "structure", hierarchy["structure"]) is False
    assert check(api_client, user, "zone", hierarchy["zone_north"]) is False
    assert check(api_client, user, "project", hierarchy["project_a"]) is False
    assert check(api_client, user, "client", hierarchy["client_a"]) is False


async def test_client_level_grant_inherits_all_the_way_down_to_structure(api_client, hierarchy, fga_cleanup):
    user = "user:alice"
    assert grant(api_client, fga_cleanup, user, "client", hierarchy["client_a"]).status_code == 201

    assert check(api_client, user, "client", hierarchy["client_a"]) is True
    assert check(api_client, user, "project", hierarchy["project_a"]) is True
    assert check(api_client, user, "zone", hierarchy["zone_north"]) is True
    assert check(api_client, user, "zone", hierarchy["zone_delhi"]) is True
    assert check(api_client, user, "zone", hierarchy["zone_central"]) is True
    assert check(api_client, user, "structure", hierarchy["structure"]) is True

    # No cross-client leakage.
    assert check(api_client, user, "client", hierarchy["client_b"]) is False
    assert check(api_client, user, "zone", hierarchy["zone_other"]) is False


async def test_project_level_grant_inherits_down_but_not_up(api_client, hierarchy, fga_cleanup):
    user = "user:bob"
    assert grant(api_client, fga_cleanup, user, "project", hierarchy["project_a"]).status_code == 201

    assert check(api_client, user, "project", hierarchy["project_a"]) is True
    assert check(api_client, user, "zone", hierarchy["zone_north"]) is True
    assert check(api_client, user, "structure", hierarchy["structure"]) is True

    assert check(api_client, user, "client", hierarchy["client_a"]) is False  # no upward inheritance
    assert check(api_client, user, "zone", hierarchy["zone_other"]) is False  # no cross-client access


async def test_zone_level_grant_inherits_through_nested_zones_but_not_up_or_sideways(api_client, hierarchy, fga_cleanup):
    user = "user:carol"
    assert grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_north"]).status_code == 201

    assert check(api_client, user, "zone", hierarchy["zone_north"]) is True
    assert check(api_client, user, "zone", hierarchy["zone_delhi"]) is True  # nested zone inheritance
    assert check(api_client, user, "zone", hierarchy["zone_central"]) is True  # deeper nested zone inheritance
    assert check(api_client, user, "structure", hierarchy["structure"]) is True

    assert check(api_client, user, "project", hierarchy["project_a"]) is False  # no upward inheritance
    assert check(api_client, user, "client", hierarchy["client_a"]) is False  # no upward inheritance
    assert check(api_client, user, "zone", hierarchy["zone_south"]) is False  # no sibling/cross-branch access


async def test_structure_only_grant_has_no_upward_access_at_all(api_client, hierarchy, fga_cleanup):
    user = "user:dave"
    assert grant(api_client, fga_cleanup, user, "structure", hierarchy["structure"]).status_code == 201

    assert check(api_client, user, "structure", hierarchy["structure"]) is True
    assert check(api_client, user, "zone", hierarchy["zone_central"]) is False
    assert check(api_client, user, "zone", hierarchy["zone_delhi"]) is False
    assert check(api_client, user, "zone", hierarchy["zone_north"]) is False
    assert check(api_client, user, "project", hierarchy["project_a"]) is False
    assert check(api_client, user, "client", hierarchy["client_a"]) is False


async def test_no_cross_client_access_even_with_broad_project_grant(api_client, hierarchy, fga_cleanup):
    user = "user:eve"
    grant(api_client, fga_cleanup, user, "project", hierarchy["project_a"])
    assert check(api_client, user, "zone", hierarchy["zone_other"]) is False
    assert check(api_client, user, "client", hierarchy["client_b"]) is False


async def test_multiple_direct_grants_are_independent(api_client, hierarchy, fga_cleanup):
    user = "user:erin"
    assert grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_south"]).status_code == 201
    assert grant(api_client, fga_cleanup, user, "structure", hierarchy["structure"]).status_code == 201

    assert check(api_client, user, "zone", hierarchy["zone_south"]) is True
    assert check(api_client, user, "structure", hierarchy["structure"]) is True
    assert check(api_client, user, "zone", hierarchy["zone_north"]) is False  # separate branch, no grant there


async def test_grant_then_revoke_removes_access(api_client, hierarchy, fga_cleanup):
    user = "user:frank"
    grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_north"])
    assert check(api_client, user, "zone", hierarchy["zone_north"]) is True

    revoke_response = revoke(api_client, user, "zone", hierarchy["zone_north"])
    assert revoke_response.status_code == 204
    assert check(api_client, user, "zone", hierarchy["zone_north"]) is False
    # Descendant access granted by inheritance disappears too.
    assert check(api_client, user, "zone", hierarchy["zone_delhi"]) is False


async def test_revoke_is_idempotent(api_client, hierarchy):
    user = "user:frank2"
    assert revoke(api_client, user, "zone", hierarchy["zone_north"]).status_code == 204
    assert revoke(api_client, user, "zone", hierarchy["zone_north"]).status_code == 204


async def test_grant_is_idempotent(api_client, hierarchy, fga_cleanup):
    user = "user:grace"
    first = grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_south"])
    second = grant(api_client, fga_cleanup, user, "zone", hierarchy["zone_south"])
    assert first.status_code == 201
    assert second.status_code == 200
    assert check(api_client, user, "zone", hierarchy["zone_south"]) is True


async def test_grant_on_nonexistent_resource_returns_404(api_client, fga_cleanup):
    response = grant(api_client, fga_cleanup, "user:x", "zone", "does-not-exist-anywhere")
    assert response.status_code == 404


async def test_check_fails_closed_when_openfga_unreachable(monkeypatch, api_client):
    from app.authorization.exceptions import AuthorizationServiceUnavailableError
    from app.services import access_service

    async def broken_check(*args, **kwargs):
        raise AuthorizationServiceUnavailableError("simulated outage")

    monkeypatch.setattr(access_service, "check_access", broken_check)

    response = api_client.get(
        "/authorization/check",
        params={"user": "user:x", "resource_type": "zone", "resource_id": "north", "permission": "viewer"},
    )
    assert response.status_code == 503
    assert "allowed" not in response.json()

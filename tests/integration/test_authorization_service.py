"""Integration tests for the centralized authorization layer
(app/authorization/{client,service,exceptions}.py) against a live OpenFGA
instance, plus fail-closed behavior when it is unreachable.
"""

import pytest
from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration

from app.authorization.exceptions import (
    AuthorizationServiceUnavailableError,
    InvalidAuthorizationRequestError,
)
from app.authorization.service import AuthorizationService
from app.core.config import get_settings


@pytest.fixture
async def service():
    settings = get_settings()
    if not settings.fga_store_id or not settings.fga_model_id:
        pytest.skip("FGA_STORE_ID/FGA_MODEL_ID not configured; run scripts/bootstrap_openfga.py first")

    configuration = ClientConfiguration(
        api_url=settings.fga_api_url,
        store_id=settings.fga_store_id,
        authorization_model_id=settings.fga_model_id,
    )
    client = OpenFgaClient(configuration)
    yield AuthorizationService(client)
    await client.close()


async def test_write_check_delete_round_trip(service):
    user, relation, obj = "user:svc-alice", "viewer", "client:svc-test"

    denied_before = await service.check(user, relation, obj)
    assert denied_before is False

    await service.write_tuple(user, relation, obj)
    try:
        assert await service.check(user, relation, obj) is True
        assert await service.check("user:svc-someone-else", relation, obj) is False
    finally:
        await service.delete_tuple(user, relation, obj)

    assert await service.check(user, relation, obj) is False


async def test_list_relationships_reflects_written_tuples(service):
    user, relation = "user:svc-bob", "viewer"
    await service.write_tuple(user, relation, "client:svc-a")
    await service.write_tuple(user, relation, "client:svc-b")
    try:
        objects = await service.list_relationships(user, relation, "client")
        assert set(objects) == {"client:svc-a", "client:svc-b"}
    finally:
        await service.delete_tuple(user, relation, "client:svc-a")
        await service.delete_tuple(user, relation, "client:svc-b")


@pytest.mark.parametrize(
    "user,relation,obj",
    [
        ("", "viewer", "client:x"),
        ("user:alice", "", "client:x"),
        ("user:alice", "viewer", ""),
        (" user:alice", "viewer", "client:x"),
    ],
)
async def test_invalid_tuple_key_is_rejected_before_calling_openfga(service, user, relation, obj):
    with pytest.raises(InvalidAuthorizationRequestError):
        await service.check(user, relation, obj)


async def test_check_fails_closed_when_openfga_unreachable():
    settings = get_settings()
    if not settings.fga_store_id:
        pytest.skip("FGA_STORE_ID not configured")

    unreachable_config = ClientConfiguration(
        api_url="http://192.0.2.1:8080",  # RFC 5737 TEST-NET, guaranteed unroutable
        store_id=settings.fga_store_id,
        timeout_millisec=1000,
    )
    client = OpenFgaClient(unreachable_config)
    unreachable_service = AuthorizationService(client)
    try:
        with pytest.raises(AuthorizationServiceUnavailableError):
            await unreachable_service.check("user:x", "viewer", "client:y")
    finally:
        await client.close()

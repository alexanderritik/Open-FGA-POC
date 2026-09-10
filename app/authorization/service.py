import logging
from collections.abc import Generator

from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.models.check_request import ClientCheckRequest
from openfga_sdk.client.models.list_objects_request import ClientListObjectsRequest
from openfga_sdk.client.models.tuple import ClientTuple
from openfga_sdk.exceptions import ApiException

from app.authorization.client import openfga_client_manager
from app.authorization.exceptions import (
    AuthorizationServiceUnavailableError,
    InvalidAuthorizationRequestError,
)

logger = logging.getLogger(__name__)

# OpenFGA API status codes that indicate a malformed/invalid request (a
# programming error in the caller) rather than the authorization engine
# being unavailable. Everything else fails closed.
_CLIENT_ERROR_STATUSES = {400, 404, 422}


def _validate_key_part(name: str, value: str) -> None:
    if not value or not value.strip():
        raise InvalidAuthorizationRequestError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise InvalidAuthorizationRequestError(f"{name} must not have leading/trailing whitespace")


def _validate_tuple_key(user: str, relation: str, object_: str) -> None:
    _validate_key_part("user", user)
    _validate_key_part("relation", relation)
    _validate_key_part("object", object_)


class AuthorizationService:
    """Single choke point for all OpenFGA SDK calls.

    API routes and business services must go through this class rather
    than importing the OpenFGA SDK directly, so authorization semantics
    (validation, fail-closed error handling) stay consistent everywhere.
    """

    def __init__(self, client: OpenFgaClient) -> None:
        self._client = client

    async def write_tuple(self, user: str, relation: str, object: str) -> None:
        _validate_tuple_key(user, relation, object)
        try:
            await self._client.write_tuples([ClientTuple(user=user, relation=relation, object=object)])
        except Exception as exc:
            self._handle_error("write_tuple", exc, user=user, relation=relation, object=object)

    async def delete_tuple(self, user: str, relation: str, object: str) -> None:
        _validate_tuple_key(user, relation, object)
        try:
            await self._client.delete_tuples([ClientTuple(user=user, relation=relation, object=object)])
        except Exception as exc:
            self._handle_error("delete_tuple", exc, user=user, relation=relation, object=object)

    async def check(self, user: str, relation: str, object: str) -> bool:
        """Returns True/False for a well-formed authorization decision.

        Never returns True as a result of an error: any failure to reach or
        get a valid answer from OpenFGA raises
        AuthorizationServiceUnavailableError instead, so callers cannot
        accidentally treat "the engine failed" as "access granted".
        """
        _validate_tuple_key(user, relation, object)
        try:
            response = await self._client.check(ClientCheckRequest(user=user, relation=relation, object=object))
        except Exception as exc:
            self._handle_error("check", exc, user=user, relation=relation, object=object)
        return bool(response.allowed)

    async def list_relationships(self, user: str, relation: str, object_type: str) -> list[str]:
        """Returns the ids of objects of `object_type` that `user` has
        `relation` on (e.g. all zones a user can view), per OpenFGA's
        ListObjects API."""
        _validate_key_part("user", user)
        _validate_key_part("relation", relation)
        _validate_key_part("object_type", object_type)
        try:
            response = await self._client.list_objects(
                ClientListObjectsRequest(user=user, relation=relation, type=object_type)
            )
        except Exception as exc:
            self._handle_error("list_relationships", exc, user=user, relation=relation, object=object_type)
        return list(response.objects or [])

    @staticmethod
    def _handle_error(operation: str, exc: Exception, **context) -> None:
        if isinstance(exc, (InvalidAuthorizationRequestError, AuthorizationServiceUnavailableError)):
            raise exc

        if isinstance(exc, ApiException) and exc.status in _CLIENT_ERROR_STATUSES:
            logger.warning("Invalid authorization request in %s: %s (%s)", operation, exc, context)
            raise InvalidAuthorizationRequestError(str(exc)) from exc

        logger.error("OpenFGA %s failed, failing closed: %s (%s)", operation, exc, context, exc_info=True)
        raise AuthorizationServiceUnavailableError(
            f"Authorization engine unavailable while performing {operation}"
        ) from exc


def get_authorization_service() -> Generator[AuthorizationService, None, None]:
    """FastAPI dependency: yields an AuthorizationService bound to the
    process-wide OpenFGA client managed by the application lifespan."""
    yield AuthorizationService(openfga_client_manager.client)

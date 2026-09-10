import logging

from openfga_sdk.client.client import OpenFgaClient
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.configuration import RetryParams

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Conservative defaults for a synchronous authorization dependency sitting in
# the request path: fail fast rather than hang a request on a stuck
# OpenFGA call, but tolerate a couple of transient blips before giving up.
DEFAULT_TIMEOUT_MILLISEC = 3_000
DEFAULT_MAX_RETRY = 2
DEFAULT_MIN_WAIT_IN_MS = 100


def build_configuration() -> ClientConfiguration:
    settings = get_settings()
    return ClientConfiguration(
        api_url=settings.fga_api_url,
        store_id=settings.fga_store_id or None,
        authorization_model_id=settings.fga_model_id or None,
        timeout_millisec=DEFAULT_TIMEOUT_MILLISEC,
        retry_params=RetryParams(max_retry=DEFAULT_MAX_RETRY, min_wait_in_ms=DEFAULT_MIN_WAIT_IN_MS),
    )


class OpenFgaClientManager:
    """Owns the single OpenFGA SDK client instance for the process.

    Intended to be started/stopped exactly once, from the FastAPI lifespan,
    so the underlying HTTP session is opened and closed cleanly alongside
    the application rather than per-request.
    """

    def __init__(self) -> None:
        self._client: OpenFgaClient | None = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        configuration = build_configuration()
        self._client = OpenFgaClient(configuration)
        logger.info("OpenFGA client connected (api_url=%s)", configuration.api_url)

    async def close(self) -> None:
        if self._client is None:
            return
        await self._client.close()
        self._client = None
        logger.info("OpenFGA client closed")

    @property
    def client(self) -> OpenFgaClient:
        if self._client is None:
            raise RuntimeError(
                "OpenFGA client not initialized. Call OpenFgaClientManager.connect() "
                "from the application lifespan before use."
            )
        return self._client


# Process-wide singleton, started/stopped from app.main's lifespan.
openfga_client_manager = OpenFgaClientManager()

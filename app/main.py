import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.authorization import router as authorization_router
from app.api.clients import router as clients_router
from app.api.structures import router as structures_router
from app.api.tree import router as tree_router
from app.api.zones import router as zones_router
from app.authorization.client import openfga_client_manager
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting up (env=%s)", settings.app_env)
    await openfga_client_manager.connect()
    # The application database engine is process-wide (module-level in
    # app/db/database.py) and needs no lifespan hook of its own.
    try:
        yield
    finally:
        await openfga_client_manager.close()
        logger.info("Shutting down")


app = FastAPI(
    title="OpenFGA ReBAC Authorization PoC",
    description=(
        "Demonstrates relationship-based access control with OpenFGA as the "
        "authorization source of truth, fronted by a FastAPI application."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


app.include_router(clients_router)
app.include_router(zones_router)
app.include_router(structures_router)
app.include_router(authorization_router)
app.include_router(tree_router)


@app.get("/health", tags=["health"], summary="Liveness check")
def health() -> dict:
    return {"status": "ok"}

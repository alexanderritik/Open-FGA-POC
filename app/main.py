import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting up (env=%s)", settings.app_env)
    # Database engine and OpenFGA client lifecycle are wired in here in later steps.
    yield
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


@app.get("/health", tags=["health"], summary="Liveness check")
def health() -> dict:
    return {"status": "ok"}

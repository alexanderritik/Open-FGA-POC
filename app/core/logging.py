import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure structured, leveled logging for the application.

    Idempotent: safe to call multiple times (e.g. once at import time and
    once from the app lifespan) without duplicating handlers.
    """
    settings = get_settings()
    level = logging.DEBUG if settings.app_env == "development" else logging.INFO

    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root.addHandler(handler)

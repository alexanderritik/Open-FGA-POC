from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables / .env.

    Infrastructure endpoints (database URL, OpenFGA URL/store/model) live
    here so business logic never hardcodes them.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8002

    # --- Application PostgreSQL (business data only) ---
    database_url: str = "postgresql+psycopg://app_user:app_password@localhost:5432/app_db"

    # --- OpenFGA (authorization data only) ---
    fga_api_url: str = "http://localhost:8080"
    fga_store_id: str = ""
    fga_model_id: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

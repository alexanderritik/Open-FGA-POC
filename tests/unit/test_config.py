from app.core.config import Settings


def test_settings_have_sane_defaults():
    settings = Settings(_env_file=None)

    assert settings.app_port == 8002
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.fga_api_url.startswith("http://") or settings.fga_api_url.startswith("https://")

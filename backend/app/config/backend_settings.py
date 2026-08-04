"""Runtime configuration for the Tapio backend service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Backend-specific settings, layered alongside ``RAGConfig``.

    Args:
        host: Interface uvicorn binds to.
        port: Port uvicorn binds to.
        cors_origins: Origins allowed to call this API. Defaults to the SvelteKit dev server.
    """

    model_config = SettingsConfigDict(env_prefix="TAPIO_BACKEND_")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]

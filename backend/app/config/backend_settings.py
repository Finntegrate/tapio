"""Runtime configuration for the Tapio backend service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Backend-specific settings, layered alongside ``RAGConfig``.

    Args:
        host: Interface uvicorn binds to.
        port: Port uvicorn binds to.
        cors_origins: Origins allowed to call this API. Defaults to the SvelteKit dev server.
        require_approved_crisis_resources: If true, guardrail crisis/legal-sensitive responses
            withhold specific contact details from ``crisis_resources.yaml`` unless its `status`
            is `approved`, per the governance doc (docs/specs/crisis-escalation-resources.md).
            Defaults to false: nothing has shipped to broad release yet, and the project's own
            governance doc treats sign-off — not a code gate — as the actual control for the
            draft period. A deployer choosing to enforce that gate in code sets this explicitly.
    """

    model_config = SettingsConfigDict(env_prefix="TAPIO_BACKEND_")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]
    require_approved_crisis_resources: bool = False

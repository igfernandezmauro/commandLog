import os

class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""

def required_env(name: str) -> str:
    value = os.getenv(name)

    if value is None or not value.strip():
        raise ConfigurationError(f"Required environment variable is missing: {name}")

    return value.strip()

def optional_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip()

def app_environment() -> str:
    return optional_env("APP_ENV", "production") or "production"

def is_local() -> bool:
    return app_environment.lower() == "local"

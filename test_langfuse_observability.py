import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.observability.config import LangfuseSettings


def test_langfuse_settings_enable_tracing_from_env(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_ENVIRONMENT", "assessment-prod")
    monkeypatch.setenv("LANGFUSE_RELEASE", "git-sha-123")

    settings = LangfuseSettings.from_env()

    assert settings.enabled is True
    assert settings.configured is True
    assert settings.base_url == "https://cloud.langfuse.com"
    assert settings.environment == "assessment-prod"
    assert settings.release == "git-sha-123"


def test_langfuse_settings_default_to_disabled_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_TRACING_ENABLED", raising=False)

    settings = LangfuseSettings.from_env()

    assert settings.enabled is False
    assert settings.configured is False
    assert settings.base_url == "https://cloud.langfuse.com"

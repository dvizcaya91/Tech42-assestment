from dataclasses import dataclass
import os


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _parse_optional_bool(raw_value: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        "LANGFUSE_TRACING_ENABLED must be one of "
        "'true', 'false', '1', '0', 'yes', 'no', 'on', or 'off'."
    )


@dataclass(frozen=True)
class LangfuseSettings:
    public_key: str = ""
    secret_key: str = ""
    base_url: str = "https://cloud.langfuse.com"
    environment: str = "assessment"
    release: str = "aws-agentcore-stock-assistant"
    requested: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.public_key and self.secret_key)

    @property
    def enabled(self) -> bool:
        return self.requested and self.configured

    @classmethod
    def from_env(cls) -> "LangfuseSettings":
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        raw_enabled = os.getenv("LANGFUSE_TRACING_ENABLED")

        if raw_enabled is None:
            requested = bool(public_key and secret_key)
        else:
            requested = _parse_optional_bool(raw_enabled)

        base_url = (
            os.getenv("LANGFUSE_BASE_URL")
            or os.getenv("LANGFUSE_HOST")
            or "https://cloud.langfuse.com"
        ).strip()

        return cls(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment=os.getenv("LANGFUSE_ENVIRONMENT", "assessment").strip()
            or "assessment",
            release=os.getenv(
                "LANGFUSE_RELEASE",
                "aws-agentcore-stock-assistant",
            ).strip()
            or "aws-agentcore-stock-assistant",
            requested=requested,
        )

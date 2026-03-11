from dataclasses import dataclass
import os
from typing import Mapping, Optional


@dataclass(frozen=True)
class CognitoSettings:
    user_pool_id: str
    user_pool_client_id: str
    issuer_url: str

    @classmethod
    def from_env(
        cls, environ: Optional[Mapping[str, str]] = None
    ) -> "CognitoSettings":
        source = environ or os.environ
        values = {
            "COGNITO_USER_POOL_ID": source.get("COGNITO_USER_POOL_ID", "").strip(),
            "COGNITO_USER_POOL_CLIENT_ID": source.get(
                "COGNITO_USER_POOL_CLIENT_ID", ""
            ).strip(),
            "COGNITO_USER_POOL_ISSUER_URL": source.get(
                "COGNITO_USER_POOL_ISSUER_URL", ""
            ).strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(
                "Missing required Cognito configuration: "
                + ", ".join(sorted(missing))
            )

        return cls(
            user_pool_id=values["COGNITO_USER_POOL_ID"],
            user_pool_client_id=values["COGNITO_USER_POOL_CLIENT_ID"],
            issuer_url=values["COGNITO_USER_POOL_ISSUER_URL"],
        )

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer_url}/.well-known/jwks.json"

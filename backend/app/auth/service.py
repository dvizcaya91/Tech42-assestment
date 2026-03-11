from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.auth.config import CognitoSettings
from app.auth.exceptions import AuthenticationError


@dataclass(frozen=True)
class AuthenticatedUser:
    subject: str
    username: Optional[str]
    token_use: str
    claims: Dict[str, Any]


class CognitoTokenVerifier:
    def __init__(self, settings: CognitoSettings):
        self._settings = settings

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            import jwt
            from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient
        except ImportError as exc:
            raise RuntimeError(
                "Install backend requirements to enable Cognito token validation."
            ) from exc

        jwk_client = PyJWKClient(self._settings.jwks_url)

        try:
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._settings.issuer_url,
                options={
                    "require": ["exp", "iat", "iss", "sub", "token_use"],
                    "verify_aud": False,
                },
            )
        except ExpiredSignatureError as exc:
            raise AuthenticationError("Cognito token is expired.") from exc
        except InvalidTokenError as exc:
            raise AuthenticationError("Cognito token is invalid.") from exc

        token_use = claims.get("token_use")
        if token_use == "access":
            audience = claims.get("client_id")
        elif token_use == "id":
            audience = claims.get("aud")
        else:
            raise AuthenticationError("Cognito token has an unsupported token_use.")

        if audience != self._settings.user_pool_client_id:
            raise AuthenticationError(
                "Cognito token was not issued for the configured app client."
            )

        return AuthenticatedUser(
            subject=claims["sub"],
            username=claims.get("cognito:username"),
            token_use=token_use,
            claims=claims,
        )

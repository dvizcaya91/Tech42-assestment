from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.agent.service import AgentService
from app.auth.config import CognitoSettings
from app.auth.exceptions import AuthenticationError
from app.auth.service import AuthenticatedUser, CognitoTokenVerifier
from app.observability import (
    AgentExecutionTracer,
    LangfuseSettings,
    build_agent_execution_tracer,
)
from app.retrieval.service import RetrievalService
from app.tools.registry import ToolRegistry

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_cognito_settings() -> CognitoSettings:
    return CognitoSettings.from_env()


@lru_cache(maxsize=1)
def get_token_verifier() -> CognitoTokenVerifier:
    return CognitoTokenVerifier(settings=get_cognito_settings())


@lru_cache(maxsize=1)
def get_langfuse_settings() -> LangfuseSettings:
    return LangfuseSettings.from_env()


@lru_cache(maxsize=1)
def get_agent_execution_tracer() -> AgentExecutionTracer:
    return build_agent_execution_tracer(get_langfuse_settings())


def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    try:
        token_verifier = get_token_verifier()
        return token_verifier.verify(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


def get_agent_service() -> AgentService:
    return AgentService(
        tool_registry=ToolRegistry.default(),
        retrieval_service=RetrievalService(),
        execution_tracer=get_agent_execution_tracer(),
    )

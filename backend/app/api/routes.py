import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.service import AgentService, AgentStreamEvent
from app.api.dependencies import get_agent_service, require_authenticated_user
from app.api.models import QueryRequest, StreamEvent
from app.auth.service import AuthenticatedUser

router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get("/health")
def healthcheck(agent_service: AgentService = Depends(get_agent_service)) -> dict:
    return {
        "status": "ok",
        "service": "aws-agentcore-stock-assistant",
        "components": agent_service.component_status(),
    }


async def _stream_agent_events(
    events: AsyncIterator[AgentStreamEvent],
) -> AsyncIterator[str]:
    async for event in events:
        payload = StreamEvent(
            event=event.event,
            sequence=event.sequence,
            data=event.data,
        )
        if hasattr(payload, "model_dump"):
            serialized_payload = payload.model_dump()
        else:
            serialized_payload = payload.dict()

        yield json.dumps(serialized_payload) + "\n"


@router.post("/query")
async def query_agent(
    request: QueryRequest,
    authenticated_user: AuthenticatedUser = Depends(require_authenticated_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_agent_events(
            agent_service.stream_query(
                query=request.query,
                user_id=authenticated_user.subject,
            )
        ),
        media_type="application/x-ndjson",
    )

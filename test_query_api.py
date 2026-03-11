import json
import sys
from pathlib import Path

import pytest


pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.agent.service import AgentStreamEvent
from app.api.dependencies import get_agent_service, require_authenticated_user
from app.auth.service import AuthenticatedUser
from app.main import create_app


class _StreamingAgentServiceStub:
    def __init__(self):
        self.calls = []

    async def stream_query(self, query: str, user_id: str):
        self.calls.append({"query": query, "user_id": user_id})
        yield AgentStreamEvent(
            event="metadata",
            sequence=0,
            data={"query": query, "user_id": user_id},
        )
        yield AgentStreamEvent(
            event="message",
            sequence=1,
            data={"text": "streamed-response"},
        )
        yield AgentStreamEvent(
            event="complete",
            sequence=2,
            data={"status": "finished"},
        )


def test_query_route_streams_agent_events_as_ndjson():
    app = create_app()
    agent_service = _StreamingAgentServiceStub()
    app.dependency_overrides[require_authenticated_user] = lambda: AuthenticatedUser(
        subject="user-123",
        username="user-123",
        token_use="access",
        claims={"sub": "user-123"},
    )
    app.dependency_overrides[get_agent_service] = lambda: agent_service

    with TestClient(app) as client:
        response = client.post(
            "/query",
            json={"query": "What is the stock price for Amazon right now?"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert agent_service.calls == [
        {
            "query": "What is the stock price for Amazon right now?",
            "user_id": "user-123",
        }
    ]

    lines = [
        json.loads(line)
        for line in response.text.strip().splitlines()
    ]
    assert [line["event"] for line in lines] == ["metadata", "message", "complete"]
    assert lines[1]["data"]["text"] == "streamed-response"

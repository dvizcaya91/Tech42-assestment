import asyncio
from contextlib import contextmanager
import sys
from datetime import date
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.agent.service import AgentService
from app.tools.registry import ToolRegistry


class _RecordingTools:
    def __init__(self):
        self.realtime_calls = []
        self.analyst_calls = []
        self.historical_calls = []

    def retrieve_realtime_stock_price(self, stock_identifier: str):
        self.realtime_calls.append({"stock_identifier": stock_identifier})
        return {
            "tool_name": "retrieve_realtime_stock_price",
            "stock_identifier": stock_identifier,
            "price": 203.15,
            "currency": "USD",
            "market_state": "REGULAR",
            "previous_close": 202.01,
            "open_price": 201.25,
            "source": "stub",
        }

    def retrieve_analyst_consensus(self, stock_identifier: str):
        self.analyst_calls.append({"stock_identifier": stock_identifier})
        return {
            "tool_name": "retrieve_analyst_consensus",
            "stock_identifier": stock_identifier,
            "target_mean_price": 245.0,
            "target_low_price": 175.0,
            "target_high_price": 300.0,
            "recommendation_key": "strong_buy",
            "recommendation_mean": 1.34,
            "analyst_count": 62,
            "current_price": 203.15,
            "source": "stub",
        }

    def retrieve_historical_stock_price(
        self,
        stock_identifier: str,
        start_date: str,
        end_date: str,
    ):
        self.historical_calls.append(
            {
                "stock_identifier": stock_identifier,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        return {
            "tool_name": "retrieve_historical_stock_price",
            "stock_identifier": stock_identifier,
            "start_date": start_date,
            "end_date": end_date,
            "interval": "1d",
            "prices": [
                {
                    "date": start_date,
                    "open_price": 185.0,
                    "high_price": 188.5,
                    "low_price": 183.8,
                    "close_price": 187.2,
                    "volume": 1250000,
                },
                {
                    "date": end_date,
                    "open_price": 219.5,
                    "high_price": 221.1,
                    "low_price": 217.4,
                    "close_price": 220.2,
                    "volume": 980000,
                },
            ],
            "source": "stub",
        }


class _RecordingRetrievalService:
    def __init__(self):
        self.requests = []

    def describe(self):
        return {"status": "configured", "source_count": 3}

    def retrieve_context(self, query: str, limit: int = 3):
        self.requests.append({"query": query, "limit": limit})
        normalized_query = query.lower()

        if "office space" in normalized_query:
            return {
                "query": query,
                "status": "ready",
                "result_count": 1,
                "results": [
                    {
                        "title": "Amazon 2024 Annual Report",
                        "excerpt": (
                            "Amazon owned approximately 49.7 million square feet of "
                            "office space in North America in 2024."
                        ),
                        "matched_terms": ["north", "office", "owned", "space"],
                        "score": 6.0,
                    }
                ],
                "formatted_context": "Retrieved Amazon report context",
            }

        if "ai business" in normalized_query:
            return {
                "query": query,
                "status": "ready",
                "result_count": 2,
                "results": [
                    {
                        "title": "AMZN Q2 2025 Earnings Release",
                        "excerpt": (
                            "Amazon described continued growth in its AI business, "
                            "highlighting Bedrock, Trainium, and Inferentia."
                        ),
                        "matched_terms": ["ai", "bedrock", "trainium"],
                        "score": 5.5,
                    },
                    {
                        "title": "Amazon 2024 Annual Report",
                        "excerpt": (
                            "The annual report highlights Amazon's AI business across "
                            "AWS and its Anthropic collaboration."
                        ),
                        "matched_terms": ["ai", "anthropic", "aws"],
                        "score": 4.0,
                    },
                ],
                "formatted_context": "Retrieved Amazon report context",
            }

        return {
            "query": query,
            "status": "ready",
            "result_count": 1,
            "results": [
                {
                    "title": "AMZN Q3 2025 Earnings Release",
                    "excerpt": (
                        "Analysts had predicted $1.58 in EPS, while Amazon cited "
                        "stronger operating income and generative AI demand."
                    ),
                    "matched_terms": ["analyst", "predicted", "reports"],
                    "score": 5.0,
                }
            ],
            "formatted_context": "Retrieved Amazon report context",
        }


class _RecordingTraceHandle:
    def __init__(self, trace_id: str, trace_url: str):
        self.trace_id = trace_id
        self.trace_url = trace_url
        self.graph_updates = []
        self.completed_payloads = []
        self.failed = []

    def trace_metadata(self):
        return {
            "enabled": True,
            "provider": "langfuse",
            "trace_id": self.trace_id,
            "trace_url": self.trace_url,
        }

    def record_graph_update(self, *, node_name, state_update, state_snapshot):
        self.graph_updates.append(
            {
                "node_name": node_name,
                "state_update": dict(state_update),
                "state_snapshot": dict(state_snapshot),
            }
        )

    def complete(self, *, answer, tool_results, retrieval_result):
        self.completed_payloads.append(
            {
                "answer": answer,
                "tool_results": list(tool_results),
                "retrieval_result": retrieval_result,
            }
        )

    def fail(self, exc):
        self.failed.append(str(exc))


class _RecordingExecutionTracer:
    def __init__(self):
        self.calls = []
        self.handles = []

    def describe(self):
        return {
            "provider": "langfuse",
            "enabled": True,
            "configured": True,
            "backend": "recording-stub",
            "base_url": "https://cloud.langfuse.com",
            "environment": "test",
            "release": "tests",
        }

    @contextmanager
    def trace_query(self, *, query, user_id, transport, orchestration_backend):
        handle = _RecordingTraceHandle(
            trace_id="trace-{0}".format(len(self.handles) + 1),
            trace_url="https://cloud.langfuse.com/project/tests/traces/{0}".format(
                len(self.handles) + 1
            ),
        )
        self.calls.append(
            {
                "query": query,
                "user_id": user_id,
                "transport": transport,
                "orchestration_backend": orchestration_backend,
            }
        )
        self.handles.append(handle)
        yield handle


def _build_service(
    today: date = date(2026, 3, 9),
    execution_tracer=None,
):
    tools = _RecordingTools()
    retrieval_service = _RecordingRetrievalService()
    registry = ToolRegistry(
        tools={
            "retrieve_realtime_stock_price": tools.retrieve_realtime_stock_price,
            "retrieve_analyst_consensus": tools.retrieve_analyst_consensus,
            "retrieve_historical_stock_price": tools.retrieve_historical_stock_price,
        }
    )
    service = AgentService(
        tool_registry=registry,
        retrieval_service=retrieval_service,
        today=today,
        execution_tracer=execution_tracer or _RecordingExecutionTracer(),
    )
    return service, tools, retrieval_service


async def _collect_events(service: AgentService, query: str):
    return [event async for event in service.stream_query(query=query, user_id="user-123")]


class _StreamingOnlyGraph:
    def __init__(self):
        self.astream_calls = []

    async def astream(self, state, stream_mode="updates"):
        self.astream_calls.append(
            {
                "state": dict(state),
                "stream_mode": stream_mode,
            }
        )
        yield {
            "plan": {
                "thought": "Use market-data tooling to gather Amazon stock context.",
                "tool_actions": [
                    {
                        "type": "tool",
                        "name": "retrieve_realtime_stock_price",
                        "input": {"stock_identifier": "AMZN"},
                    }
                ],
                "use_retrieval": False,
                "retrieval_limit": 3,
                "stock_identifier": "AMZN",
                "tool_results": [],
                "retrieval_result": None,
            }
        }
        yield {
            "execute_tools": {
                "tool_results": [
                    {
                        "action": {
                            "type": "tool",
                            "name": "retrieve_realtime_stock_price",
                            "input": {"stock_identifier": "AMZN"},
                        },
                        "observation": {
                            "tool_name": "retrieve_realtime_stock_price",
                            "stock_identifier": "AMZN",
                            "price": 203.15,
                            "currency": "USD",
                        },
                    }
                ]
            }
        }
        yield {"answer": {"answer": "AMZN is trading at $203.15."}}

    async def ainvoke(self, state):
        raise AssertionError("run_query should consume graph updates through astream().")


def test_agent_service_uses_realtime_tool_for_current_price_queries():
    tracer = _RecordingExecutionTracer()
    service, tools, retrieval_service = _build_service(execution_tracer=tracer)

    result = asyncio.run(
        service.run_query(
            query="What is the stock price for Amazon right now?",
            user_id="user-123",
        )
    )

    assert tools.realtime_calls == [{"stock_identifier": "AMZN"}]
    assert tools.analyst_calls == []
    assert tools.historical_calls == []
    assert retrieval_service.requests == []
    assert result["tool_actions"] == [
        {
            "type": "tool",
            "name": "retrieve_realtime_stock_price",
            "input": {"stock_identifier": "AMZN"},
        }
    ]
    assert "AMZN is trading at $203.15" in result["answer"]
    assert result["trace"]["trace_id"] == "trace-1"
    assert tracer.calls[0]["transport"] == "buffered-run"


def test_run_query_uses_graph_astream_when_available():
    service, _, retrieval_service = _build_service()
    graph = _StreamingOnlyGraph()
    service = AgentService(
        tool_registry=service.tool_registry,
        retrieval_service=retrieval_service,
        today=date(2026, 3, 9),
        agent_graph=graph,
    )

    result = asyncio.run(
        service.run_query(
            query="What is the stock price for Amazon right now?",
            user_id="user-123",
        )
    )

    assert len(graph.astream_calls) == 1
    assert graph.astream_calls[0]["stream_mode"] == "updates"
    assert result["thought"] == "Use market-data tooling to gather Amazon stock context."
    assert result["tool_results"][0]["observation"]["tool_name"] == "retrieve_realtime_stock_price"
    assert result["answer"] == "AMZN is trading at $203.15."


def test_agent_service_routes_q4_last_year_queries_to_historical_prices():
    service, tools, retrieval_service = _build_service()

    result = asyncio.run(
        service.run_query(
            query="What were the stock prices for Amazon in Q4 last year?",
            user_id="user-123",
        )
    )

    assert tools.realtime_calls == []
    assert tools.analyst_calls == []
    assert tools.historical_calls == [
        {
            "stock_identifier": "AMZN",
            "start_date": "2025-10-01",
            "end_date": "2025-12-31",
        }
    ]
    assert retrieval_service.requests == []
    assert "2025-10-01" in result["answer"]
    assert "2025-12-31" in result["answer"]
    assert "220.20" in result["answer"]


def test_agent_service_combines_realtime_and_retrieval_for_ai_questions():
    service, tools, retrieval_service = _build_service()

    result = asyncio.run(
        service.run_query(
            query=(
                "I'm researching AMZN give me the current price and any relevant "
                "information about their AI business"
            ),
            user_id="user-123",
        )
    )

    assert tools.realtime_calls == [{"stock_identifier": "AMZN"}]
    assert tools.analyst_calls == []
    assert tools.historical_calls == []
    assert retrieval_service.requests == [
        {
            "query": (
                "I'm researching AMZN give me the current price and any relevant "
                "information about their AI business"
            ),
            "limit": 3,
        }
    ]
    assert "AMZN is trading at $203.15" in result["answer"]
    assert "AI business" in result["answer"]
    assert "Bedrock" in result["answer"]


def test_agent_service_uses_retrieval_for_office_space_questions():
    service, tools, retrieval_service = _build_service()

    result = asyncio.run(
        service.run_query(
            query="What is the total amount of office space Amazon owned in North America in 2024?",
            user_id="user-123",
        )
    )

    assert tools.realtime_calls == []
    assert tools.analyst_calls == []
    assert tools.historical_calls == []
    assert retrieval_service.requests == [
        {
            "query": "What is the total amount of office space Amazon owned in North America in 2024?",
            "limit": 3,
        }
    ]
    assert "Amazon 2024 Annual Report" in result["answer"]
    assert "49.7 million square feet of office space" in result["answer"]


def test_stream_query_emits_react_style_events_for_comparison_queries():
    tracer = _RecordingExecutionTracer()
    service, tools, retrieval_service = _build_service(execution_tracer=tracer)

    events = asyncio.run(
        _collect_events(
            service,
            "Compare Amazon's recent stock performance to what analysts predicted in their reports",
        )
    )

    assert [event.event for event in events] == [
        "metadata",
        "reasoning",
        "tool_result",
        "tool_result",
        "retrieval_result",
        "message",
        "complete",
    ]
    assert events[0].data["supports_langgraph_astream"] is True
    assert events[0].data["trace"]["trace_id"] == "trace-1"
    assert events[1].data["selected_actions"][0]["name"] == "retrieve_realtime_stock_price"
    assert events[1].data["selected_actions"][1]["name"] == "retrieve_analyst_consensus"
    assert events[2].data["observation"]["tool_name"] == "retrieve_realtime_stock_price"
    assert events[3].data["observation"]["tool_name"] == "retrieve_analyst_consensus"
    assert events[4].data["results"][0]["title"] == "AMZN Q3 2025 Earnings Release"
    assert "yfinance analyst mean target" in events[5].data["text"]
    assert "Analysts had predicted $1.58 in EPS" in events[5].data["text"]
    assert tools.realtime_calls == [{"stock_identifier": "AMZN"}]
    assert tools.analyst_calls == [{"stock_identifier": "AMZN"}]
    assert len(retrieval_service.requests) == 1
    assert tracer.calls[0]["transport"] == "fastapi-stream"
    assert [update["node_name"] for update in tracer.handles[0].graph_updates] == [
        "plan",
        "execute_tools",
        "retrieve_context",
        "answer",
    ]
    assert tracer.handles[0].completed_payloads[0]["retrieval_result"]["status"] == "ready"
    assert tracer.handles[0].failed == []

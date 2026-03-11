from dataclasses import dataclass, field
from datetime import date
import inspect
import re
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, TypedDict

from app.observability import AgentExecutionTraceHandle, NoOpAgentExecutionTracer
from app.retrieval.service import RetrievalService
from app.tools.registry import ToolRegistry

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - optional until backend extras are installed
    END = None
    START = None
    StateGraph = None


class AgentState(TypedDict, total=False):
    query: str
    user_id: str
    thought: str
    stock_identifier: Optional[str]
    tool_actions: List[Dict[str, Any]]
    use_retrieval: bool
    retrieval_limit: int
    tool_results: List[Dict[str, Any]]
    retrieval_result: Optional[Dict[str, Any]]
    answer: str


@dataclass(frozen=True)
class AgentStreamEvent:
    event: str
    sequence: int
    data: Dict[str, Any]


@dataclass
class _FallbackCompiledAgentGraph:
    service: "AgentService"

    async def ainvoke(self, state: AgentState) -> AgentState:
        next_state = dict(state)
        async for _, state_update in self.service._graph_updates_from_stream(
            self.astream(state)
        ):
            next_state.update(state_update)
        return next_state

    async def astream(
        self,
        state: AgentState,
        stream_mode: str = "updates",
    ) -> AsyncIterator[Dict[str, AgentState]]:
        del stream_mode

        next_state = dict(state)

        plan_update = self.service._plan_step(next_state)
        next_state.update(plan_update)
        yield {"plan": plan_update}

        next_route = self.service._route_after_plan(next_state)
        if next_route == "execute_tools":
            tools_update = await self.service._execute_tools_step(next_state)
            next_state.update(tools_update)
            yield {"execute_tools": tools_update}
            next_route = self.service._route_after_tools(next_state)

        if next_route == "retrieve_context":
            retrieval_update = await self.service._retrieve_context_step(next_state)
            next_state.update(retrieval_update)
            yield {"retrieve_context": retrieval_update}

        answer_update = self.service._answer_step(next_state)
        next_state.update(answer_update)
        yield {"answer": answer_update}


@dataclass
class AgentService:
    tool_registry: ToolRegistry
    retrieval_service: RetrievalService
    today: Optional[date] = None
    agent_graph: Optional[Any] = None
    execution_tracer: Any = field(default_factory=NoOpAgentExecutionTracer)
    orchestration_backend: str = field(init=False, default="uninitialized")

    def __post_init__(self) -> None:
        if self.agent_graph is not None:
            self.orchestration_backend = "injected"
            return

        if StateGraph is None:
            self.agent_graph = _FallbackCompiledAgentGraph(self)
            self.orchestration_backend = "langgraph-unavailable-fallback"
            return

        workflow = StateGraph(AgentState)
        workflow.add_node("plan", self._plan_step)
        workflow.add_node("execute_tools", self._execute_tools_step)
        workflow.add_node("retrieve_context", self._retrieve_context_step)
        workflow.add_node("answer", self._answer_step)
        workflow.add_edge(START, "plan")
        workflow.add_conditional_edges(
            "plan",
            self._route_after_plan,
            {
                "execute_tools": "execute_tools",
                "retrieve_context": "retrieve_context",
                "answer": "answer",
            },
        )
        workflow.add_conditional_edges(
            "execute_tools",
            self._route_after_tools,
            {
                "retrieve_context": "retrieve_context",
                "answer": "answer",
            },
        )
        workflow.add_edge("retrieve_context", "answer")
        workflow.add_edge("answer", END)
        self.agent_graph = workflow.compile()
        self.orchestration_backend = "langgraph"

    def component_status(self) -> Dict[str, object]:
        return {
            "agent": "langgraph-react",
            "react_style": True,
            "orchestration_backend": self.orchestration_backend,
            "tools": self.tool_registry.list_tools(),
            "retrieval": self.retrieval_service.describe(),
            "observability": self.execution_tracer.describe(),
        }

    async def run_query(
        self,
        query: str,
        user_id: str,
    ) -> Dict[str, Any]:
        with self.execution_tracer.trace_query(
            query=query,
            user_id=user_id,
            transport="buffered-run",
            orchestration_backend=self.orchestration_backend,
        ) as trace_handle:
            final_state = await self._collect_final_state(
                query=query,
                user_id=user_id,
                trace_handle=trace_handle,
            )
            trace_handle.complete(
                answer=final_state.get("answer", ""),
                tool_results=list(final_state.get("tool_results", [])),
                retrieval_result=final_state.get("retrieval_result"),
            )

        return {
            "query": query,
            "user_id": user_id,
            "thought": final_state.get("thought", ""),
            "tool_actions": list(final_state.get("tool_actions", [])),
            "tool_results": list(final_state.get("tool_results", [])),
            "retrieval_result": final_state.get("retrieval_result"),
            "answer": final_state.get("answer", ""),
            "orchestration_backend": self.orchestration_backend,
            "trace": trace_handle.trace_metadata(),
        }

    async def stream_query(
        self,
        query: str,
        user_id: str,
    ) -> AsyncIterator[AgentStreamEvent]:
        final_state = self._build_initial_state(query=query, user_id=user_id)
        sequence = 0

        with self.execution_tracer.trace_query(
            query=query,
            user_id=user_id,
            transport="fastapi-stream",
            orchestration_backend=self.orchestration_backend,
        ) as trace_handle:
            try:
                yield AgentStreamEvent(
                    event="metadata",
                    sequence=sequence,
                    data={
                        "query": query,
                        "user_id": user_id,
                        "transport": "fastapi-stream",
                        "supports_langgraph_astream": True,
                        "orchestration_backend": self.orchestration_backend,
                        "react_style": True,
                        "trace": trace_handle.trace_metadata(),
                    },
                )
                sequence += 1

                async for node_name, state_update in self._stream_graph_updates(
                    final_state,
                    trace_handle=trace_handle,
                ):
                    final_state.update(state_update)

                    if node_name == "plan":
                        yield AgentStreamEvent(
                            event="reasoning",
                            sequence=sequence,
                            data={
                                "thought": final_state.get("thought", ""),
                                "selected_actions": list(
                                    final_state.get("tool_actions", [])
                                ),
                            },
                        )
                        sequence += 1
                        continue

                    if node_name == "execute_tools":
                        for tool_result in state_update.get("tool_results", []):
                            yield AgentStreamEvent(
                                event="tool_result",
                                sequence=sequence,
                                data=tool_result,
                            )
                            sequence += 1
                        continue

                    if node_name == "retrieve_context":
                        retrieval_result = final_state.get("retrieval_result")
                        if retrieval_result is not None:
                            yield AgentStreamEvent(
                                event="retrieval_result",
                                sequence=sequence,
                                data=retrieval_result,
                            )
                            sequence += 1
                        continue

                    if node_name == "answer":
                        yield AgentStreamEvent(
                            event="message",
                            sequence=sequence,
                            data={
                                "text": final_state.get("answer", ""),
                                "tool_results": list(
                                    final_state.get("tool_results", [])
                                ),
                                "retrieval_result": final_state.get(
                                    "retrieval_result"
                                ),
                            },
                        )
                        sequence += 1

                trace_handle.complete(
                    answer=final_state.get("answer", ""),
                    tool_results=list(final_state.get("tool_results", [])),
                    retrieval_result=final_state.get("retrieval_result"),
                )
            except Exception as exc:
                trace_handle.fail(exc)
                raise

        yield AgentStreamEvent(
            event="complete",
            sequence=sequence,
            data={"status": "finished"},
        )

    def _build_initial_state(self, query: str, user_id: str) -> AgentState:
        return AgentState(
            query=query,
            user_id=user_id,
            tool_actions=[],
            tool_results=[],
            use_retrieval=False,
            retrieval_limit=3,
            retrieval_result=None,
        )

    async def _collect_final_state(
        self,
        query: str,
        user_id: str,
        trace_handle: Optional[AgentExecutionTraceHandle] = None,
    ) -> AgentState:
        final_state = self._build_initial_state(query=query, user_id=user_id)
        async for _, state_update in self._stream_graph_updates(
            final_state,
            trace_handle=trace_handle,
        ):
            final_state.update(state_update)
        return final_state

    async def _stream_graph_updates(
        self,
        initial_state: AgentState,
        trace_handle: Optional[AgentExecutionTraceHandle] = None,
    ) -> AsyncIterator[Tuple[str, AgentState]]:
        current_state = AgentState(**dict(initial_state))

        if hasattr(self.agent_graph, "astream"):
            try:
                graph_stream = self.agent_graph.astream(
                    dict(initial_state),
                    stream_mode="updates",
                )
            except TypeError:
                graph_stream = self.agent_graph.astream(dict(initial_state))

            async for node_name, state_update in self._graph_updates_from_stream(
                graph_stream
            ):
                current_state.update(state_update)
                if trace_handle is not None:
                    trace_handle.record_graph_update(
                        node_name=node_name,
                        state_update=state_update,
                        state_snapshot=dict(current_state),
                    )
                yield node_name, state_update
            return

        result = self.agent_graph.ainvoke(dict(initial_state))
        if inspect.isawaitable(result):
            final_state = await result
        else:  # pragma: no cover - defensive branch for alternate graph implementations
            final_state = result

        for node_name, state_update in self._graph_updates_from_state(final_state):
            current_state.update(state_update)
            if trace_handle is not None:
                trace_handle.record_graph_update(
                    node_name=node_name,
                    state_update=state_update,
                    state_snapshot=dict(current_state),
                )
            yield node_name, state_update

    async def _graph_updates_from_stream(
        self,
        graph_stream: AsyncIterator[Any],
    ) -> AsyncIterator[Tuple[str, AgentState]]:
        async for raw_update in graph_stream:
            for node_name, state_update in self._normalize_graph_update(raw_update):
                yield node_name, state_update

    def _graph_updates_from_state(
        self,
        state: Dict[str, Any],
    ) -> List[Tuple[str, AgentState]]:
        updates: List[Tuple[str, AgentState]] = []

        if "thought" in state or "tool_actions" in state:
            updates.append(
                (
                    "plan",
                    AgentState(
                        thought=state.get("thought", ""),
                        tool_actions=list(state.get("tool_actions", [])),
                        use_retrieval=bool(state.get("use_retrieval", False)),
                        retrieval_limit=int(state.get("retrieval_limit", 3)),
                        stock_identifier=state.get("stock_identifier"),
                    ),
                )
            )

        if state.get("tool_results"):
            updates.append(
                (
                    "execute_tools",
                    AgentState(tool_results=list(state.get("tool_results", []))),
                )
            )

        if state.get("retrieval_result") is not None:
            updates.append(
                (
                    "retrieve_context",
                    AgentState(retrieval_result=state.get("retrieval_result")),
                )
            )

        if "answer" in state:
            updates.append(("answer", AgentState(answer=state.get("answer", ""))))

        return updates

    def _normalize_graph_update(self, raw_update: Any) -> List[Tuple[str, AgentState]]:
        if isinstance(raw_update, tuple) and len(raw_update) == 2:
            _, raw_update = raw_update

        if not isinstance(raw_update, dict):
            return []

        known_nodes = ("plan", "execute_tools", "retrieve_context", "answer")
        if any(node_name in raw_update for node_name in known_nodes):
            updates = []
            for node_name in known_nodes:
                state_update = raw_update.get(node_name)
                if isinstance(state_update, dict):
                    updates.append((node_name, AgentState(**state_update)))
            return updates

        inferred_node_name = self._infer_node_name(raw_update)
        if inferred_node_name is None:
            return []
        return [(inferred_node_name, AgentState(**raw_update))]

    def _infer_node_name(self, state_update: Dict[str, Any]) -> Optional[str]:
        if "thought" in state_update or "tool_actions" in state_update:
            return "plan"
        if "tool_results" in state_update:
            return "execute_tools"
        if "retrieval_result" in state_update:
            return "retrieve_context"
        if "answer" in state_update:
            return "answer"
        return None

    def _plan_step(self, state: AgentState) -> AgentState:
        query = state["query"]
        normalized_query = query.lower()
        stock_identifier = self._extract_stock_identifier(query)
        tool_actions = []
        use_retrieval = self._should_use_retrieval(normalized_query)

        if self._should_use_historical_price_tool(normalized_query):
            date_range = self._resolve_historical_date_range(normalized_query)
            if stock_identifier is not None and date_range is not None:
                tool_actions.append(
                    {
                        "type": "tool",
                        "name": "retrieve_historical_stock_price",
                        "input": {
                            "stock_identifier": stock_identifier,
                            "start_date": date_range["start_date"],
                            "end_date": date_range["end_date"],
                        },
                    }
                )
        elif self._should_use_realtime_price_tool(normalized_query):
            if stock_identifier is not None:
                tool_actions.append(
                    {
                        "type": "tool",
                        "name": "retrieve_realtime_stock_price",
                        "input": {
                            "stock_identifier": stock_identifier,
                        },
                    }
                )

        if self._should_use_analyst_consensus_tool(normalized_query):
            if stock_identifier is not None:
                tool_actions.append(
                    {
                        "type": "tool",
                        "name": "retrieve_analyst_consensus",
                        "input": {
                            "stock_identifier": stock_identifier,
                        },
                    }
                )

        thought_parts = []
        if tool_actions:
            thought_parts.append(
                "Use market-data tooling to gather Amazon stock context."
            )
        if use_retrieval:
            thought_parts.append(
                "Consult the required Amazon reports for grounded business context."
            )
        if not thought_parts:
            thought_parts.append(
                "Answer directly with the available assessment context."
            )

        return AgentState(
            thought=" ".join(thought_parts),
            stock_identifier=stock_identifier,
            tool_actions=tool_actions,
            use_retrieval=use_retrieval,
            retrieval_limit=3,
            tool_results=[],
            retrieval_result=None,
        )

    async def _execute_tools_step(self, state: AgentState) -> AgentState:
        tool_results = []
        for action in state.get("tool_actions", []):
            tool = self.tool_registry.get_tool(action["name"])
            observation = tool(**action["input"])
            if inspect.isawaitable(observation):
                observation = await observation

            tool_results.append(
                {
                    "action": action,
                    "observation": observation,
                }
            )

        return AgentState(tool_results=tool_results)

    async def _retrieve_context_step(self, state: AgentState) -> AgentState:
        retrieval_result = self.retrieval_service.retrieve_context(
            state["query"],
            limit=int(state.get("retrieval_limit", 3)),
        )
        if inspect.isawaitable(retrieval_result):
            retrieval_result = await retrieval_result
        return AgentState(retrieval_result=retrieval_result)

    def _answer_step(self, state: AgentState) -> AgentState:
        answer_segments = []
        tool_results = state.get("tool_results", [])
        retrieval_result = state.get("retrieval_result")

        realtime_observation = self._find_tool_observation(
            tool_results,
            "retrieve_realtime_stock_price",
        )
        analyst_observation = self._find_tool_observation(
            tool_results,
            "retrieve_analyst_consensus",
        )
        historical_observation = self._find_tool_observation(
            tool_results,
            "retrieve_historical_stock_price",
        )

        if realtime_observation is not None:
            answer_segments.append(self._summarize_realtime_price(realtime_observation))

        if analyst_observation is not None:
            answer_segments.append(
                self._summarize_analyst_consensus(
                    analyst_observation,
                    realtime_observation=realtime_observation,
                )
            )

        if historical_observation is not None:
            answer_segments.append(
                self._summarize_historical_prices(historical_observation)
            )

        if retrieval_result is not None:
            retrieval_summary = self._summarize_retrieval_result(retrieval_result)
            if retrieval_summary:
                answer_segments.append(retrieval_summary)

        if not answer_segments:
            answer_segments.append(
                "I could not find market or report context for that question."
            )

        return AgentState(answer=" ".join(answer_segments))

    def _route_after_plan(self, state: AgentState) -> str:
        if state.get("tool_actions"):
            return "execute_tools"
        if state.get("use_retrieval"):
            return "retrieve_context"
        return "answer"

    def _route_after_tools(self, state: AgentState) -> str:
        if state.get("use_retrieval"):
            return "retrieve_context"
        return "answer"

    def _extract_stock_identifier(self, query: str) -> Optional[str]:
        normalized_query = query.lower()
        if "amazon" in normalized_query or "amzn" in normalized_query:
            return "AMZN"

        for token in re.findall(r"\b[A-Z]{1,5}\b", query):
            if token not in {"AI", "EPS"}:
                return token
        return None

    def _should_use_realtime_price_tool(self, normalized_query: str) -> bool:
        realtime_markers = (
            "right now",
            "current price",
            "stock price",
            "price for amazon right now",
            "price and",
            "compare",
        )
        if self._should_use_historical_price_tool(normalized_query):
            return False
        return any(marker in normalized_query for marker in realtime_markers)

    def _should_use_analyst_consensus_tool(self, normalized_query: str) -> bool:
        analyst_markers = (
            "analyst",
            "analysts",
            "predicted",
            "prediction",
            "consensus",
            "forecast",
            "target price",
            "compare",
        )
        return any(marker in normalized_query for marker in analyst_markers)

    def _should_use_historical_price_tool(self, normalized_query: str) -> bool:
        has_price_language = "price" in normalized_query or "stock" in normalized_query
        historical_markers = (
            "q1",
            "q2",
            "q3",
            "q4",
            "historical",
            "last year",
            "from ",
            "between ",
        )
        return has_price_language and any(
            marker in normalized_query for marker in historical_markers
        )

    def _should_use_retrieval(self, normalized_query: str) -> bool:
        retrieval_markers = (
            "analyst",
            "predicted",
            "prediction",
            "report",
            "reports",
            "ai business",
            "bedrock",
            "trainium",
            "anthropic",
            "office space",
            "north america",
            "owned",
            "leased",
            "compare",
        )
        return any(marker in normalized_query for marker in retrieval_markers)

    def _resolve_historical_date_range(
        self,
        normalized_query: str,
    ) -> Optional[Dict[str, str]]:
        reference_date = self.today if self.today is not None else date.today()
        quarter_match = re.search(r"\bq([1-4])\b", normalized_query)
        if quarter_match is None:
            return None

        quarter = int(quarter_match.group(1))
        year_match = re.search(r"\b(20\d{2})\b", normalized_query)
        if year_match is not None:
            year = int(year_match.group(1))
        elif "last year" in normalized_query:
            year = reference_date.year - 1
        else:
            year = reference_date.year

        quarter_start_month = ((quarter - 1) * 3) + 1
        quarter_end_month = quarter_start_month + 2
        start_date = date(year, quarter_start_month, 1)
        end_day = 31
        if quarter_end_month in (4, 6, 9, 11):
            end_day = 30
        return {
            "start_date": start_date.isoformat(),
            "end_date": date(year, quarter_end_month, end_day).isoformat(),
        }

    def _find_tool_observation(
        self,
        tool_results: List[Dict[str, Any]],
        tool_name: str,
    ) -> Optional[Dict[str, Any]]:
        for result in tool_results:
            action = result.get("action", {})
            if action.get("name") == tool_name:
                observation = result.get("observation")
                if isinstance(observation, dict):
                    return observation
        return None

    def _summarize_realtime_price(self, observation: Dict[str, Any]) -> str:
        price = observation.get("price")
        stock_identifier = observation.get("stock_identifier", "the stock")
        currency = observation.get("currency")
        if currency == "USD":
            price_text = "${0:.2f}".format(float(price))
        elif currency:
            price_text = "{0:.2f} {1}".format(float(price), currency)
        else:
            price_text = "{0:.2f}".format(float(price))

        details = []
        if observation.get("open_price") is not None:
            details.append("opened at ${0:.2f}".format(float(observation["open_price"])))
        if observation.get("previous_close") is not None:
            details.append(
                "previous close was ${0:.2f}".format(float(observation["previous_close"]))
            )

        if details:
            return "{stock_identifier} is trading at {price_text}; it {details}.".format(
                stock_identifier=stock_identifier,
                price_text=price_text,
                details=", and ".join(details),
            )
        return "{stock_identifier} is trading at {price_text}.".format(
            stock_identifier=stock_identifier,
            price_text=price_text,
        )

    def _summarize_historical_prices(self, observation: Dict[str, Any]) -> str:
        prices = observation.get("prices", [])
        if not prices:
            return "No historical candles were returned."

        first_point = prices[0]
        last_point = prices[-1]
        return (
            "{stock_identifier} returned {count} historical candles from {start_date} "
            "through {end_date}. The first close was ${first_close:.2f} and the last "
            "close was ${last_close:.2f}."
        ).format(
            stock_identifier=observation.get("stock_identifier", "The stock"),
            count=len(prices),
            start_date=observation.get("start_date"),
            end_date=observation.get("end_date"),
            first_close=float(first_point.get("close_price") or 0.0),
            last_close=float(last_point.get("close_price") or 0.0),
        )

    def _summarize_analyst_consensus(
        self,
        observation: Dict[str, Any],
        realtime_observation: Optional[Dict[str, Any]] = None,
    ) -> str:
        stock_identifier = observation.get("stock_identifier", "The stock")
        target_mean_price = observation.get("target_mean_price")
        analyst_count = observation.get("analyst_count")
        recommendation_key = observation.get("recommendation_key")
        recommendation_mean = observation.get("recommendation_mean")
        comparison_price = None

        if realtime_observation is not None:
            comparison_price = realtime_observation.get("price")
        if comparison_price is None:
            comparison_price = observation.get("current_price")

        summary_parts = []
        if target_mean_price is not None:
            target_text = "{0} has a yfinance analyst mean target of ${1:.2f}".format(
                stock_identifier,
                float(target_mean_price),
            )
            if analyst_count is not None:
                target_text += " across {0} analysts".format(int(analyst_count))
            summary_parts.append(target_text + ".")

            if comparison_price is not None and float(comparison_price) > 0:
                implied_change = (
                    (float(target_mean_price) - float(comparison_price))
                    / float(comparison_price)
                ) * 100.0
                summary_parts.append(
                    "That is {0:.1f}% {1} the current price.".format(
                        abs(implied_change),
                        "above" if implied_change >= 0 else "below",
                    )
                )

        if recommendation_key:
            recommendation_text = "Consensus recommendation is {0}".format(
                str(recommendation_key).replace("_", " ")
            )
            if recommendation_mean is not None:
                recommendation_text += " ({0:.2f})".format(
                    float(recommendation_mean)
                )
            summary_parts.append(recommendation_text + ".")

        if summary_parts:
            return " ".join(summary_parts)

        return "No analyst consensus details were returned."

    def _summarize_retrieval_result(self, retrieval_result: Dict[str, Any]) -> str:
        if retrieval_result.get("status") != "ready":
            return ""

        top_results = retrieval_result.get("results", [])
        if not top_results:
            return ""

        lead = top_results[0]
        summary = "From {title}: {excerpt}".format(
            title=lead.get("title", "the Amazon reports"),
            excerpt=lead.get("excerpt", ""),
        )

        if len(top_results) > 1:
            supporting_titles = ", ".join(
                result.get("title", "")
                for result in top_results[1:]
                if result.get("title")
            )
            if supporting_titles:
                summary += " Supporting report context also came from {0}.".format(
                    supporting_titles
                )
        return summary

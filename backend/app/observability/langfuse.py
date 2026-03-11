from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, ContextManager, Dict, Iterator, List, Optional, Protocol

from app.observability.config import LangfuseSettings

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover - optional until backend extras are installed
    Langfuse = None


class AgentExecutionTraceHandle(Protocol):
    trace_id: Optional[str]
    trace_url: Optional[str]

    def trace_metadata(self) -> Dict[str, Any]:
        ...

    def record_graph_update(
        self,
        *,
        node_name: str,
        state_update: Dict[str, Any],
        state_snapshot: Dict[str, Any],
    ) -> None:
        ...

    def complete(
        self,
        *,
        answer: str,
        tool_results: List[Dict[str, Any]],
        retrieval_result: Optional[Dict[str, Any]],
    ) -> None:
        ...

    def fail(self, exc: BaseException) -> None:
        ...


class AgentExecutionTracer(Protocol):
    def describe(self) -> Dict[str, Any]:
        ...

    def trace_query(
        self,
        *,
        query: str,
        user_id: str,
        transport: str,
        orchestration_backend: str,
    ) -> ContextManager[AgentExecutionTraceHandle]:
        ...


@dataclass
class _NoOpTraceHandle:
    trace_id: Optional[str] = None
    trace_url: Optional[str] = None

    def trace_metadata(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "trace_id": self.trace_id,
            "trace_url": self.trace_url,
        }

    def record_graph_update(
        self,
        *,
        node_name: str,
        state_update: Dict[str, Any],
        state_snapshot: Dict[str, Any],
    ) -> None:
        del node_name, state_update, state_snapshot

    def complete(
        self,
        *,
        answer: str,
        tool_results: List[Dict[str, Any]],
        retrieval_result: Optional[Dict[str, Any]],
    ) -> None:
        del answer, tool_results, retrieval_result

    def fail(self, exc: BaseException) -> None:
        del exc


@dataclass
class NoOpAgentExecutionTracer:
    settings: LangfuseSettings = field(default_factory=LangfuseSettings)
    backend: str = "disabled"

    def describe(self) -> Dict[str, Any]:
        return {
            "provider": "langfuse",
            "enabled": False,
            "configured": self.settings.configured,
            "backend": self.backend,
            "base_url": self.settings.base_url,
            "environment": self.settings.environment,
            "release": self.settings.release,
        }

    @contextmanager
    def trace_query(
        self,
        *,
        query: str,
        user_id: str,
        transport: str,
        orchestration_backend: str,
    ) -> Iterator[AgentExecutionTraceHandle]:
        del query, user_id, transport, orchestration_backend
        yield _NoOpTraceHandle()


@dataclass
class _LangfuseTraceHandle:
    client: Any
    query: str
    user_id: str
    transport: str
    orchestration_backend: str
    settings: LangfuseSettings
    trace_id: Optional[str] = None
    trace_url: Optional[str] = None
    _root_context: Optional[Any] = None
    _root_observation: Optional[Any] = None
    _completed: bool = False
    _failed: bool = False

    def __enter__(self) -> "_LangfuseTraceHandle":
        self._root_context = self._start_current_observation(
            name="agent_query",
            as_type="agent",
            input={"query": self.query, "transport": self.transport},
            user_id=self.user_id,
            metadata={
                "orchestration_backend": self.orchestration_backend,
                "langfuse_environment": self.settings.environment,
                "release": self.settings.release,
            },
        )
        self._root_observation = self._root_context.__enter__()
        self.trace_id = self._safe_get_current_trace_id()
        self.trace_url = self._safe_get_trace_url()
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if exc is not None:
            self.fail(exc)

        if self._root_context is not None:
            self._root_context.__exit__(exc_type, exc, exc_tb)

        self._safe_flush()

    def trace_metadata(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "provider": "langfuse",
            "trace_id": self.trace_id,
            "trace_url": self.trace_url,
        }

    def record_graph_update(
        self,
        *,
        node_name: str,
        state_update: Dict[str, Any],
        state_snapshot: Dict[str, Any],
    ) -> None:
        if node_name == "plan":
            self._record_observation(
                name="plan",
                as_type="chain",
                input={"query": state_snapshot.get("query", self.query)},
                output={
                    "thought": state_update.get("thought", ""),
                    "tool_actions": list(state_update.get("tool_actions", [])),
                    "use_retrieval": bool(state_update.get("use_retrieval", False)),
                },
            )
            return

        if node_name == "execute_tools":
            for tool_result in state_update.get("tool_results", []):
                action = tool_result.get("action", {})
                self._record_observation(
                    name=action.get("name", "tool_execution"),
                    as_type="tool",
                    input=action.get("input", {}),
                    output=tool_result.get("observation", tool_result),
                    metadata={"tool_action": action},
                )
            return

        if node_name == "retrieve_context":
            self._record_observation(
                name="retrieve_context",
                as_type="retriever",
                input={
                    "query": state_snapshot.get("query", self.query),
                    "limit": state_snapshot.get("retrieval_limit", 3),
                },
                output=state_update.get("retrieval_result"),
            )
            return

        if node_name == "answer":
            self._record_observation(
                name="answer",
                as_type="chain",
                input={
                    "tool_result_count": len(state_snapshot.get("tool_results", [])),
                    "has_retrieval": state_snapshot.get("retrieval_result") is not None,
                },
                output={"answer": state_update.get("answer", "")},
            )

    def complete(
        self,
        *,
        answer: str,
        tool_results: List[Dict[str, Any]],
        retrieval_result: Optional[Dict[str, Any]],
    ) -> None:
        if self._completed or self._failed or self._root_observation is None:
            return

        if hasattr(self._root_observation, "update"):
            self._root_observation.update(
                output={
                    "answer": answer,
                    "tool_results": tool_results,
                    "retrieval_result": retrieval_result,
                },
            )

        self._completed = True

    def fail(self, exc: BaseException) -> None:
        if self._failed or self._root_observation is None:
            return

        if hasattr(self._root_observation, "update"):
            self._root_observation.update(output={"error": str(exc)})

        self._failed = True

    def _record_observation(
        self,
        *,
        name: str,
        as_type: str,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._start_current_observation(
            name=name,
            as_type=as_type,
            input=input,
            output=output,
            metadata=metadata,
        ):
            return

    def _start_current_observation(self, **kwargs: Any) -> Any:
        try:
            return self.client.start_as_current_observation(**kwargs)
        except TypeError:
            kwargs.pop("user_id", None)
            return self.client.start_as_current_observation(**kwargs)

    def _safe_flush(self) -> None:
        flush = getattr(self.client, "flush", None)
        if callable(flush):
            flush()

    def _safe_get_current_trace_id(self) -> Optional[str]:
        getter = getattr(self.client, "get_current_trace_id", None)
        if not callable(getter):
            return None
        return getter()

    def _safe_get_trace_url(self) -> Optional[str]:
        getter = getattr(self.client, "get_trace_url", None)
        if not callable(getter):
            return None

        try:
            return getter()
        except TypeError:
            if self.trace_id is None:
                return None
            return getter(trace_id=self.trace_id)


@dataclass
class _LangfuseAgentExecutionTracer:
    settings: LangfuseSettings
    client: Any

    def describe(self) -> Dict[str, Any]:
        return {
            "provider": "langfuse",
            "enabled": True,
            "configured": True,
            "backend": "langfuse",
            "base_url": self.settings.base_url,
            "environment": self.settings.environment,
            "release": self.settings.release,
        }

    @contextmanager
    def trace_query(
        self,
        *,
        query: str,
        user_id: str,
        transport: str,
        orchestration_backend: str,
    ) -> Iterator[AgentExecutionTraceHandle]:
        handle = _LangfuseTraceHandle(
            client=self.client,
            query=query,
            user_id=user_id,
            transport=transport,
            orchestration_backend=orchestration_backend,
            settings=self.settings,
        )
        with handle:
            yield handle


def build_agent_execution_tracer(
    settings: LangfuseSettings,
) -> AgentExecutionTracer:
    if not settings.enabled:
        return NoOpAgentExecutionTracer(settings=settings)

    if Langfuse is None:
        return NoOpAgentExecutionTracer(
            settings=settings,
            backend="langfuse-sdk-unavailable",
        )

    return _LangfuseAgentExecutionTracer(
        settings=settings,
        client=_build_langfuse_client(settings),
    )


def _build_langfuse_client(settings: LangfuseSettings) -> Any:
    client_kwargs = {
        "public_key": settings.public_key,
        "secret_key": settings.secret_key,
    }

    try:
        return Langfuse(base_url=settings.base_url, **client_kwargs)
    except TypeError:  # pragma: no cover - compatibility with alternate SDK kwargs
        return Langfuse(host=settings.base_url, **client_kwargs)

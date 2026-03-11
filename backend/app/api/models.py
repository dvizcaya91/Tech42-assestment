from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language question for the agent.")
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional client conversation identifier to thread later LangGraph runs.",
    )


class StreamEvent(BaseModel):
    event: str
    sequence: int
    data: Dict[str, Any]

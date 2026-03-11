from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from app.tools.market_data import (
    retrieve_analyst_consensus,
    retrieve_historical_stock_price,
    retrieve_realtime_stock_price,
)


@dataclass
class ToolRegistry:
    tools: Dict[str, Callable[..., Dict[str, Any]]]

    @classmethod
    def default(cls) -> "ToolRegistry":
        return cls(
            tools={
                "retrieve_realtime_stock_price": retrieve_realtime_stock_price,
                "retrieve_analyst_consensus": retrieve_analyst_consensus,
                "retrieve_historical_stock_price": retrieve_historical_stock_price,
            }
        )

    def list_tools(self) -> List[str]:
        return list(self.tools)

    def get_tool(self, tool_name: str) -> Callable[..., Dict[str, Any]]:
        return self.tools[tool_name]

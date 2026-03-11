import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.tools.market_data import (
    retrieve_analyst_consensus,
    retrieve_realtime_stock_price,
)
from app.tools.registry import ToolRegistry
import app.tools.market_data as market_data


class _FakeTicker:
    def __init__(self, symbol: str):
        self.fast_info = {
            "lastPrice": 203.15,
            "currency": "USD",
            "marketState": "REGULAR",
            "previousClose": 202.01,
            "open": 201.25,
        }
        self.info = {"symbol": symbol}
        self.info.update(
            {
                "targetMeanPrice": 245.0,
                "targetLowPrice": 175.0,
                "targetHighPrice": 300.0,
                "numberOfAnalystOpinions": 62,
                "recommendationKey": "strong_buy",
                "recommendationMean": 1.34,
                "currentPrice": 203.15,
            }
        )


class _FakeYFinance:
    def __init__(self):
        self.requested_symbols = []

    def Ticker(self, symbol: str) -> _FakeTicker:
        self.requested_symbols.append(symbol)
        return _FakeTicker(symbol)


def test_realtime_stock_price_tool_returns_structured_yfinance_data(monkeypatch):
    fake_yfinance = _FakeYFinance()
    monkeypatch.setattr(market_data, "yf", fake_yfinance)

    result = retrieve_realtime_stock_price(" amzn ")

    assert fake_yfinance.requested_symbols == ["AMZN"]
    assert result == {
        "tool_name": "retrieve_realtime_stock_price",
        "stock_identifier": "AMZN",
        "price": 203.15,
        "currency": "USD",
        "market_state": "REGULAR",
        "previous_close": 202.01,
        "open_price": 201.25,
        "source": "yfinance",
    }


def test_realtime_stock_price_tool_requires_identifier():
    try:
        retrieve_realtime_stock_price("   ")
    except ValueError as exc:
        assert str(exc) == "stock_identifier must be provided."
    else:  # pragma: no cover - defensive guard for the assertion shape
        raise AssertionError("Expected retrieve_realtime_stock_price to reject blanks.")


def test_analyst_consensus_tool_returns_structured_yfinance_data(monkeypatch):
    fake_yfinance = _FakeYFinance()
    monkeypatch.setattr(market_data, "yf", fake_yfinance)

    result = retrieve_analyst_consensus(" amzn ")

    assert fake_yfinance.requested_symbols == ["AMZN"]
    assert result == {
        "tool_name": "retrieve_analyst_consensus",
        "stock_identifier": "AMZN",
        "target_mean_price": 245.0,
        "target_low_price": 175.0,
        "target_high_price": 300.0,
        "recommendation_key": "strong_buy",
        "recommendation_mean": 1.34,
        "analyst_count": 62,
        "current_price": 203.15,
        "source": "yfinance",
    }


def test_tool_registry_registers_realtime_stock_price_tool():
    registry = ToolRegistry.default()

    assert registry.list_tools() == [
        "retrieve_realtime_stock_price",
        "retrieve_analyst_consensus",
        "retrieve_historical_stock_price",
    ]
    assert registry.get_tool("retrieve_realtime_stock_price") is retrieve_realtime_stock_price
    assert registry.get_tool("retrieve_analyst_consensus") is retrieve_analyst_consensus

import sys
from datetime import date
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.tools.market_data import retrieve_historical_stock_price
from app.tools.registry import ToolRegistry
import app.tools.market_data as market_data


class _FakeHistoryRow:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


class _FakeHistoryFrame:
    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        return iter(self._rows)


class _FakeTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.history_requests = []

    def history(self, *, start: str, end: str, interval: str, auto_adjust: bool):
        self.history_requests.append(
            {
                "start": start,
                "end": end,
                "interval": interval,
                "auto_adjust": auto_adjust,
            }
        )
        return _FakeHistoryFrame(
            [
                (
                    date(2025, 10, 1),
                    _FakeHistoryRow(
                        {
                            "Open": 185.0,
                            "High": 188.5,
                            "Low": 183.8,
                            "Close": 187.2,
                            "Volume": 1250000,
                        }
                    ),
                ),
                (
                    date(2025, 12, 31),
                    _FakeHistoryRow(
                        {
                            "Open": 219.5,
                            "High": 221.1,
                            "Low": 217.4,
                            "Close": 220.2,
                            "Volume": 980000,
                        }
                    ),
                ),
            ]
        )


class _FakeSingleDayTicker(_FakeTicker):
    def history(self, *, start: str, end: str, interval: str, auto_adjust: bool):
        self.history_requests.append(
            {
                "start": start,
                "end": end,
                "interval": interval,
                "auto_adjust": auto_adjust,
            }
        )
        return _FakeHistoryFrame(
            [
                (
                    date(2025, 11, 3),
                    _FakeHistoryRow(
                        {
                            "Open": 199.0,
                            "High": 202.0,
                            "Low": 198.1,
                            "Close": 201.5,
                            "Volume": 770000,
                        }
                    ),
                )
            ]
        )


class _FakeYFinance:
    def __init__(self, ticker_cls=_FakeTicker):
        self.requested_symbols = []
        self.ticker_cls = ticker_cls
        self.tickers = []

    def Ticker(self, symbol: str):
        self.requested_symbols.append(symbol)
        ticker = self.ticker_cls(symbol)
        self.tickers.append(ticker)
        return ticker


def test_historical_stock_price_tool_returns_structured_yfinance_history(monkeypatch):
    fake_yfinance = _FakeYFinance()
    monkeypatch.setattr(market_data, "yf", fake_yfinance)

    result = retrieve_historical_stock_price(
        " amzn ",
        start_date="2025-10-01",
        end_date="2025-12-31",
    )

    assert fake_yfinance.requested_symbols == ["AMZN"]
    assert fake_yfinance.tickers[0].history_requests == [
        {
            "start": "2025-10-01",
            "end": "2026-01-01",
            "interval": "1d",
            "auto_adjust": False,
        }
    ]
    assert result == {
        "tool_name": "retrieve_historical_stock_price",
        "stock_identifier": "AMZN",
        "start_date": "2025-10-01",
        "end_date": "2025-12-31",
        "interval": "1d",
        "prices": [
            {
                "date": "2025-10-01",
                "open_price": 185.0,
                "high_price": 188.5,
                "low_price": 183.8,
                "close_price": 187.2,
                "volume": 1250000,
            },
            {
                "date": "2025-12-31",
                "open_price": 219.5,
                "high_price": 221.1,
                "low_price": 217.4,
                "close_price": 220.2,
                "volume": 980000,
            },
        ],
        "source": "yfinance",
    }


def test_historical_stock_price_tool_accepts_single_day_requests(monkeypatch):
    fake_yfinance = _FakeYFinance(ticker_cls=_FakeSingleDayTicker)
    monkeypatch.setattr(market_data, "yf", fake_yfinance)

    result = retrieve_historical_stock_price(
        "AMZN",
        start_date="2025-11-03",
    )

    assert fake_yfinance.tickers[0].history_requests == [
        {
            "start": "2025-11-03",
            "end": "2025-11-04",
            "interval": "1d",
            "auto_adjust": False,
        }
    ]
    assert result["start_date"] == "2025-11-03"
    assert result["end_date"] == "2025-11-03"
    assert result["prices"][0]["date"] == "2025-11-03"


def test_historical_stock_price_tool_requires_valid_date_order():
    try:
        retrieve_historical_stock_price(
            "AMZN",
            start_date="2025-12-31",
            end_date="2025-10-01",
        )
    except ValueError as exc:
        assert str(exc) == "end_date must be on or after start_date."
    else:  # pragma: no cover - defensive guard for the assertion shape
        raise AssertionError(
            "Expected retrieve_historical_stock_price to reject inverted dates."
        )


def test_tool_registry_registers_historical_stock_price_tool():
    registry = ToolRegistry.default()

    assert registry.list_tools() == [
        "retrieve_realtime_stock_price",
        "retrieve_analyst_consensus",
        "retrieve_historical_stock_price",
    ]
    assert (
        registry.get_tool("retrieve_historical_stock_price")
        is retrieve_historical_stock_price
    )

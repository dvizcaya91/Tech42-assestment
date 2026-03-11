from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - exercised in environments without extras installed
    yf = None


@dataclass(frozen=True)
class RealtimeStockPriceResult:
    tool_name: str
    stock_identifier: str
    price: float
    currency: Optional[str]
    market_state: Optional[str]
    previous_close: Optional[float]
    open_price: Optional[float]
    source: str = "yfinance"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalStockPricePoint:
    date: str
    open_price: Optional[float]
    high_price: Optional[float]
    low_price: Optional[float]
    close_price: Optional[float]
    volume: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalStockPriceResult:
    tool_name: str
    stock_identifier: str
    start_date: str
    end_date: str
    interval: str
    prices: List[Dict[str, Any]]
    source: str = "yfinance"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnalystConsensusResult:
    tool_name: str
    stock_identifier: str
    target_mean_price: Optional[float]
    target_low_price: Optional[float]
    target_high_price: Optional[float]
    recommendation_key: Optional[str]
    recommendation_mean: Optional[float]
    analyst_count: Optional[int]
    current_price: Optional[float]
    source: str = "yfinance"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _extract_value(
    sources: Iterable[Mapping[str, Any]],
    keys: Iterable[str],
) -> Optional[Any]:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value is not None:
                return value
    return None


def _extract_float(
    sources: Iterable[Mapping[str, Any]],
    keys: Iterable[str],
) -> Optional[float]:
    value = _extract_value(sources, keys)
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_text(
    sources: Iterable[Mapping[str, Any]],
    keys: Iterable[str],
) -> Optional[str]:
    value = _extract_value(sources, keys)
    if value is None:
        return None
    return str(value)


def _get_yfinance_client() -> Any:
    if yf is None:
        raise RuntimeError(
            "yfinance is required for market data tools. "
            "Install backend dependencies with `pip install -r requirements.txt`."
        )
    return yf


def _parse_iso_date(raw_value: str, field_name: str) -> date:
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.") from exc


def _normalize_history_date(index_value: Any) -> str:
    if hasattr(index_value, "date"):
        date_value = index_value.date()
        if isinstance(date_value, date):
            return date_value.isoformat()
    if isinstance(index_value, datetime):
        return index_value.date().isoformat()
    if isinstance(index_value, date):
        return index_value.isoformat()
    if hasattr(index_value, "isoformat"):
        iso_value = index_value.isoformat()
        if isinstance(iso_value, str):
            return iso_value.split("T", 1)[0]
    return str(index_value)


def _normalize_volume(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_int(
    sources: Iterable[Mapping[str, Any]],
    keys: Iterable[str],
) -> Optional[int]:
    value = _extract_value(sources, keys)
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iter_history_rows(history: Any) -> List[HistoricalStockPricePoint]:
    rows = []
    for index_value, row_value in history.iterrows():
        row_mapping = _mapping_or_empty(
            row_value.to_dict() if hasattr(row_value, "to_dict") else row_value
        )
        rows.append(
            HistoricalStockPricePoint(
                date=_normalize_history_date(index_value),
                open_price=_extract_float((row_mapping,), ("Open", "open")),
                high_price=_extract_float((row_mapping,), ("High", "high")),
                low_price=_extract_float((row_mapping,), ("Low", "low")),
                close_price=_extract_float((row_mapping,), ("Close", "close")),
                volume=_normalize_volume(
                    _extract_value((row_mapping,), ("Volume", "volume"))
                ),
            )
        )
    return rows


def retrieve_realtime_stock_price(stock_identifier: str) -> Dict[str, Any]:
    normalized_identifier = stock_identifier.strip().upper()
    if not normalized_identifier:
        raise ValueError("stock_identifier must be provided.")

    ticker = _get_yfinance_client().Ticker(normalized_identifier)
    fast_info = _mapping_or_empty(getattr(ticker, "fast_info", {}))
    info = _mapping_or_empty(getattr(ticker, "info", {}))
    sources = (fast_info, info)

    price = _extract_float(
        sources,
        (
            "lastPrice",
            "last_price",
            "regularMarketPrice",
            "regular_market_price",
            "currentPrice",
            "current_price",
        ),
    )
    if price is None:
        raise ValueError(
            f"Unable to determine a realtime price for '{normalized_identifier}'."
        )

    result = RealtimeStockPriceResult(
        tool_name="retrieve_realtime_stock_price",
        stock_identifier=normalized_identifier,
        price=price,
        currency=_extract_text(sources, ("currency",)),
        market_state=_extract_text(
            sources,
            (
                "marketState",
                "market_state",
            ),
        ),
        previous_close=_extract_float(
            sources,
            (
                "previousClose",
                "previous_close",
                "regularMarketPreviousClose",
                "regular_market_previous_close",
            ),
        ),
        open_price=_extract_float(
            sources,
            (
                "open",
                "regularMarketOpen",
                "regular_market_open",
            ),
        ),
    )
    return result.to_dict()


def retrieve_analyst_consensus(stock_identifier: str) -> Dict[str, Any]:
    normalized_identifier = stock_identifier.strip().upper()
    if not normalized_identifier:
        raise ValueError("stock_identifier must be provided.")

    ticker = _get_yfinance_client().Ticker(normalized_identifier)
    fast_info = _mapping_or_empty(getattr(ticker, "fast_info", {}))
    info = _mapping_or_empty(getattr(ticker, "info", {}))
    sources = (info, fast_info)

    target_mean_price = _extract_float(
        sources,
        (
            "targetMeanPrice",
            "target_mean_price",
        ),
    )
    analyst_count = _extract_int(
        sources,
        (
            "numberOfAnalystOpinions",
            "number_of_analyst_opinions",
        ),
    )
    if target_mean_price is None and analyst_count is None:
        raise ValueError(
            f"Unable to determine analyst consensus for '{normalized_identifier}'."
        )

    result = AnalystConsensusResult(
        tool_name="retrieve_analyst_consensus",
        stock_identifier=normalized_identifier,
        target_mean_price=target_mean_price,
        target_low_price=_extract_float(
            sources,
            (
                "targetLowPrice",
                "target_low_price",
            ),
        ),
        target_high_price=_extract_float(
            sources,
            (
                "targetHighPrice",
                "target_high_price",
            ),
        ),
        recommendation_key=_extract_text(
            sources,
            (
                "recommendationKey",
                "recommendation_key",
            ),
        ),
        recommendation_mean=_extract_float(
            sources,
            (
                "recommendationMean",
                "recommendation_mean",
            ),
        ),
        analyst_count=analyst_count,
        current_price=_extract_float(
            (fast_info, info),
            (
                "lastPrice",
                "last_price",
                "regularMarketPrice",
                "regular_market_price",
                "currentPrice",
                "current_price",
            ),
        ),
    )
    return result.to_dict()


def retrieve_historical_stock_price(
    stock_identifier: str,
    start_date: str,
    end_date: Optional[str] = None,
    interval: str = "1d",
) -> Dict[str, Any]:
    normalized_identifier = stock_identifier.strip().upper()
    if not normalized_identifier:
        raise ValueError("stock_identifier must be provided.")

    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = (
        _parse_iso_date(end_date, "end_date")
        if end_date is not None
        else normalized_start_date
    )
    if normalized_end_date < normalized_start_date:
        raise ValueError("end_date must be on or after start_date.")

    normalized_interval = interval.strip() or "1d"
    history_request_end_date = normalized_end_date + timedelta(days=1)

    ticker = _get_yfinance_client().Ticker(normalized_identifier)
    history = ticker.history(
        start=normalized_start_date.isoformat(),
        end=history_request_end_date.isoformat(),
        interval=normalized_interval,
        auto_adjust=False,
    )

    prices = _iter_history_rows(history)
    if not prices:
        raise ValueError(
            f"Unable to determine historical prices for '{normalized_identifier}'."
        )

    result = HistoricalStockPriceResult(
        tool_name="retrieve_historical_stock_price",
        stock_identifier=normalized_identifier,
        start_date=normalized_start_date.isoformat(),
        end_date=normalized_end_date.isoformat(),
        interval=normalized_interval,
        prices=[price.to_dict() for price in prices],
    )
    return result.to_dict()

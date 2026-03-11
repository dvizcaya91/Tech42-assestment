import asyncio
from datetime import date
import math
import re
import sys
from functools import lru_cache
from pathlib import Path

import pytest


pytest.importorskip("yfinance")


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.agent.service import AgentService
from app.retrieval.service import RetrievalService
from app.tools.registry import ToolRegistry
import yfinance as yf


REFERENCE_TODAY = date(2026, 3, 10)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _first_available_float(sources, keys):
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value is None:
                continue
            return float(value)
    raise AssertionError(f"Unable to find any of {keys} in direct yfinance data.")


@lru_cache(maxsize=1)
def _build_retrieval_service() -> RetrievalService:
    service = RetrievalService()
    service.sync_required_documents()
    return service


@lru_cache(maxsize=1)
def _document_text_by_title():
    service = _build_retrieval_service()
    return {
        document["title"]: _normalize_whitespace(document["content_text"])
        for document in service.build_retrieval_corpus()
    }


def _run_query(query: str):
    service = AgentService(
        tool_registry=ToolRegistry.default(),
        retrieval_service=_build_retrieval_service(),
        today=REFERENCE_TODAY,
    )
    return asyncio.run(service.run_query(query=query, user_id="acceptance-test"))


def _tool_observation(result, tool_name: str):
    for tool_result in result["tool_results"]:
        if tool_result["action"]["name"] == tool_name:
            return tool_result["observation"]
    raise AssertionError(f"Missing tool result for {tool_name}.")


def _assert_retrieval_excerpts_are_grounded(retrieval_result):
    documents = _document_text_by_title()
    for passage in retrieval_result["results"]:
        document_text = documents[passage["title"]]
        cleaned_excerpt = _normalize_whitespace(passage["excerpt"]).rstrip(".")
        if cleaned_excerpt.endswith("..."):
            cleaned_excerpt = cleaned_excerpt[:-3]
        assert cleaned_excerpt in document_text
        assert passage["source_url"].startswith("https://s2.q4cdn.com/299287126/")


def test_acceptance_current_price_uses_live_yfinance_data():
    result = _run_query("What is the stock price for Amazon right now?")

    observation = _tool_observation(result, "retrieve_realtime_stock_price")
    ticker = yf.Ticker("AMZN")
    direct_sources = (
        dict(getattr(ticker, "fast_info", {}) or {}),
        dict(getattr(ticker, "info", {}) or {}),
    )
    direct_price = _first_available_float(
        direct_sources,
        (
            "lastPrice",
            "last_price",
            "regularMarketPrice",
            "regular_market_price",
            "currentPrice",
            "current_price",
        ),
    )

    assert observation["stock_identifier"] == "AMZN"
    assert observation["source"] == "yfinance"
    assert observation["currency"] == "USD"
    assert observation["price"] > 0
    assert math.isclose(observation["price"], direct_price, rel_tol=0.05)
    assert f"${observation['price']:.2f}" in result["answer"]


def test_acceptance_q4_last_year_uses_live_yfinance_history():
    result = _run_query("What were the stock prices for Amazon in Q4 last year?")

    observation = _tool_observation(result, "retrieve_historical_stock_price")
    history = yf.Ticker("AMZN").history(
        start="2025-10-01",
        end="2026-01-01",
        interval="1d",
        auto_adjust=False,
    )

    assert observation["source"] == "yfinance"
    assert observation["start_date"] == "2025-10-01"
    assert observation["end_date"] == "2025-12-31"
    assert len(observation["prices"]) == len(history.index)
    assert observation["prices"][0]["date"] == history.index[0].date().isoformat()
    assert observation["prices"][-1]["date"] == history.index[-1].date().isoformat()
    assert math.isclose(
        observation["prices"][0]["close_price"],
        float(history.iloc[0]["Close"]),
        rel_tol=1e-9,
    )
    assert math.isclose(
        observation["prices"][-1]["close_price"],
        float(history.iloc[-1]["Close"]),
        rel_tol=1e-9,
    )
    assert "64 historical candles" in result["answer"]


def test_acceptance_compare_query_combines_yfinance_and_reports():
    result = _run_query(
        "Compare Amazon's recent stock performance to what analysts predicted in their reports"
    )

    realtime_observation = _tool_observation(result, "retrieve_realtime_stock_price")
    analyst_observation = _tool_observation(result, "retrieve_analyst_consensus")
    ticker = yf.Ticker("AMZN")
    direct_info = dict(getattr(ticker, "info", {}) or {})

    assert realtime_observation["source"] == "yfinance"
    assert analyst_observation["source"] == "yfinance"
    assert realtime_observation["price"] > 0
    assert analyst_observation["analyst_count"] == int(
        direct_info["numberOfAnalystOpinions"]
    )
    assert math.isclose(
        analyst_observation["target_mean_price"],
        float(direct_info["targetMeanPrice"]),
        rel_tol=1e-9,
    )
    assert "yfinance analyst mean target" in result["answer"]
    assert "Consensus recommendation" in result["answer"]


def test_acceptance_ai_business_query_combines_yfinance_and_reports():
    result = _run_query(
        "I'm researching AMZN give me the current price and any relevant information about their AI business"
    )

    observation = _tool_observation(result, "retrieve_realtime_stock_price")
    retrieval_result = result["retrieval_result"]

    assert observation["source"] == "yfinance"
    assert observation["price"] > 0
    assert retrieval_result["status"] == "ready"
    assert retrieval_result["result_count"] >= 1
    assert any(
        term in retrieval_result["formatted_context"]
        for term in ("AI", "Bedrock", "Trainium", "Anthropic", "Inferentia")
    )
    assert any(
        term in result["answer"]
        for term in ("Bedrock", "Trainium", "Anthropic", "Inferentia")
    )
    _assert_retrieval_excerpts_are_grounded(retrieval_result)


def test_acceptance_office_space_query_uses_required_amazon_report():
    result = _run_query(
        "What is the total amount of office space Amazon owned in North America in 2024?"
    )

    retrieval_result = result["retrieval_result"]

    assert result["tool_results"] == []
    assert retrieval_result["status"] == "ready"
    assert retrieval_result["results"][0]["title"] == "Amazon 2024 Annual Report"
    assert "Office space 29,551 9,104 North America" in retrieval_result["results"][0]["excerpt"]
    assert "office space" in retrieval_result["results"][0]["excerpt"].lower()
    _assert_retrieval_excerpts_are_grounded(retrieval_result)
    assert "9,104" in result["answer"]

import sys
from pathlib import Path
import zlib

import pytest


BACKEND_ROOT = Path(__file__).resolve().parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.retrieval.service import (
    AMAZON_REPORT_SOURCES,
    RetrievalService,
    _default_documents_directory,
)


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _write_cached_documents(tmp_path: Path) -> None:
    document_payloads = {
        "Amazon-2024-Annual-Report.pdf": (
            "Amazon 2024 Annual Report. In North America, Amazon owned and leased "
            "approximately 49.7 million square feet of office space in 2024. "
            "The annual report also highlights Amazon's AI business across AWS "
            "through Trainium, Bedrock, and Anthropic collaboration."
        ),
        "AMZN-Q3-2025-Earnings-Release.pdf": (
            "AMZN Q3 2025 Earnings Release. Analysts had predicted $1.58 in EPS for "
            "the quarter, while Amazon reported stronger operating income and cited "
            "generative AI demand for AWS services."
        ),
        "AMZN-Q2-2025-Earnings-Release.pdf": (
            "AMZN Q2 2025 Earnings Release. Amazon described continued growth in its "
            "AI business, noting Bedrock adoption and custom silicon with Trainium "
            "and Inferentia. Analysts expected margin expansion during the quarter."
        ),
    }

    for filename, content in document_payloads.items():
        (tmp_path / filename).write_bytes(content.encode("utf-8"))


def _build_minimal_pdf(text: str) -> bytes:
    stream = zlib.compress(
        (
            "BT\n/F1 12 Tf\n72 720 Td\n({text}) Tj\nET".format(text=text)
        ).encode("latin-1")
    )
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        + "<< /Length {length} /Filter /FlateDecode >>\n".format(length=len(stream)).encode(
            "ascii"
        )
        + b"stream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF\n"
    )


def test_retrieval_manifest_contains_exact_required_amazon_reports():
    assert [source.document_id for source in AMAZON_REPORT_SOURCES] == [
        "amazon_2024_annual_report",
        "amzn_q3_2025_earnings_release",
        "amzn_q2_2025_earnings_release",
    ]
    assert [source.title for source in AMAZON_REPORT_SOURCES] == [
        "Amazon 2024 Annual Report",
        "AMZN Q3 2025 Earnings Release",
        "AMZN Q2 2025 Earnings Release",
    ]
    assert [source.filename for source in AMAZON_REPORT_SOURCES] == [
        "Amazon-2024-Annual-Report.pdf",
        "AMZN-Q3-2025-Earnings-Release.pdf",
        "AMZN-Q2-2025-Earnings-Release.pdf",
    ]
    assert [source.source_url for source in AMAZON_REPORT_SOURCES] == [
        "https://s2.q4cdn.com/299287126/files/doc_financials/2025/ar/Amazon-2024-Annual-Report.pdf",
        "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q3/AMZN-Q3-2025-Earnings-Release.pdf",
        "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q2/AMZN-Q2-2025-Earnings-Release.pdf",
    ]


def test_default_documents_directory_uses_tmp_in_lambda(monkeypatch):
    monkeypatch.delenv("RETRIEVAL_DOCUMENTS_DIRECTORY", raising=False)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "aws-agentcore-stock-assistant")

    path = _default_documents_directory()

    assert path == Path("/tmp/aws-agentcore-stock-assistant-documents")


def test_default_documents_directory_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("RETRIEVAL_DOCUMENTS_DIRECTORY", str(tmp_path))
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

    path = _default_documents_directory()

    assert path == tmp_path


def test_retrieval_service_reports_required_documents(tmp_path):
    service = RetrievalService(documents_directory=tmp_path)

    description = service.describe()

    assert description["status"] == "configured"
    assert description["source_count"] == 3
    assert description["cached_source_count"] == 0
    assert description["indexed_document_count"] == 0
    assert description["documents_directory"] == str(tmp_path)
    assert [source["filename"] for source in description["sources"]] == [
        "Amazon-2024-Annual-Report.pdf",
        "AMZN-Q3-2025-Earnings-Release.pdf",
        "AMZN-Q2-2025-Earnings-Release.pdf",
    ]
    assert all(source["is_cached"] is False for source in description["sources"])


def test_retrieval_service_syncs_only_required_documents(tmp_path):
    payloads = {
        source.source_url: f"payload-for-{source.document_id}".encode("utf-8")
        for source in AMAZON_REPORT_SOURCES
    }
    requested_urls = []

    def fake_downloader(url: str) -> _FakeResponse:
        requested_urls.append(url)
        return _FakeResponse(payloads[url])

    service = RetrievalService(documents_directory=tmp_path)

    synced_documents = service.sync_required_documents(downloader=fake_downloader)
    loaded_documents = service.load_cached_documents()

    assert requested_urls == [source.source_url for source in AMAZON_REPORT_SOURCES]
    assert [document["filename"] for document in synced_documents] == [
        "Amazon-2024-Annual-Report.pdf",
        "AMZN-Q3-2025-Earnings-Release.pdf",
        "AMZN-Q2-2025-Earnings-Release.pdf",
    ]
    assert all(document["is_cached"] is True for document in synced_documents)
    assert [document["document_id"] for document in loaded_documents] == [
        "amazon_2024_annual_report",
        "amzn_q3_2025_earnings_release",
        "amzn_q2_2025_earnings_release",
    ]
    assert [document["content_bytes"] for document in loaded_documents] == [
        payloads[source.source_url] for source in AMAZON_REPORT_SOURCES
    ]


def test_retrieval_service_builds_ranked_context_for_assessment_queries(tmp_path):
    _write_cached_documents(tmp_path)
    service = RetrievalService(documents_directory=tmp_path)

    analyst_context = service.retrieve_context(
        "Compare Amazon's recent stock performance to what analysts predicted in their reports"
    )
    ai_context = service.retrieve_context(
        "I'm researching AMZN give me the current price and any relevant information about their AI business"
    )
    office_context = service.retrieve_context(
        "What is the total amount of office space Amazon owned in North America in 2024?"
    )

    assert analyst_context["status"] == "ready"
    assert analyst_context["result_count"] >= 1
    assert analyst_context["results"][0]["title"] == "AMZN Q3 2025 Earnings Release"
    assert "Analysts had predicted" in analyst_context["results"][0]["excerpt"]
    assert "Retrieved Amazon report context" in analyst_context["formatted_context"]

    assert ai_context["status"] == "ready"
    assert ai_context["result_count"] >= 1
    assert "AI business" in ai_context["formatted_context"]
    assert any(
        "Bedrock" in result["excerpt"] or "Trainium" in result["excerpt"]
        for result in ai_context["results"]
    )

    assert office_context["status"] == "ready"
    assert office_context["results"][0]["title"] == "Amazon 2024 Annual Report"
    assert "49.7 million square feet of office space" in office_context["results"][0]["excerpt"]
    assert "north, office, owned, space" in office_context["formatted_context"]


def test_retrieval_service_auto_syncs_documents_before_querying(tmp_path):
    payloads = {
        source.source_url: (
            "Amazon 2024 Annual Report. Office space 29,551 9,104 North America. "
            "Amazon AI business includes Bedrock and Trainium."
            if source.document_id == "amazon_2024_annual_report"
            else (
                "AMZN Q3 2025 Earnings Release. Financial Guidance. "
                "Anthropic and Trainium2 were highlighted."
                if source.document_id == "amzn_q3_2025_earnings_release"
                else "AMZN Q2 2025 Earnings Release. Bedrock AgentCore and Nova."
            )
        ).encode("utf-8")
        for source in AMAZON_REPORT_SOURCES
    }

    def fake_downloader(url: str) -> _FakeResponse:
        return _FakeResponse(payloads[url])

    service = RetrievalService(documents_directory=tmp_path)
    service.sync_required_documents = lambda downloader=None: RetrievalService.sync_required_documents(  # type: ignore[method-assign]
        service,
        downloader=fake_downloader,
    )

    office_context = service.retrieve_context(
        "What is the total amount of office space Amazon owned in North America in 2024?"
    )

    assert office_context["status"] == "ready"
    assert office_context["results"][0]["title"] == "Amazon 2024 Annual Report"
    assert "9,104 North America" in office_context["results"][0]["excerpt"]
    assert all((tmp_path / source.filename).is_file() for source in AMAZON_REPORT_SOURCES)


def test_retrieval_service_extracts_text_from_cached_pdf_streams(tmp_path):
    annual_report_path = tmp_path / "Amazon-2024-Annual-Report.pdf"
    q3_path = tmp_path / "AMZN-Q3-2025-Earnings-Release.pdf"
    q2_path = tmp_path / "AMZN-Q2-2025-Earnings-Release.pdf"

    annual_report_path.write_bytes(
        _build_minimal_pdf(
            "Amazon owned 49.7 million square feet of office space in North America."
        )
    )
    q3_path.write_bytes(
        _build_minimal_pdf(
            "Analysts predicted stronger retail revenue in the quarter."
        )
    )
    q2_path.write_bytes(
        _build_minimal_pdf(
            "Amazon highlighted Bedrock and Trainium as AI business drivers."
        )
    )

    service = RetrievalService(documents_directory=tmp_path)

    office_context = service.retrieve_context(
        "What is the total amount of office space Amazon owned in North America in 2024?"
    )
    ai_context = service.retrieve_context("Tell me about Amazon's AI business")

    assert office_context["status"] == "ready"
    assert "49.7 million square feet of office space" in office_context["results"][0]["excerpt"]
    assert ai_context["status"] == "ready"
    assert "Bedrock and Trainium" in ai_context["formatted_context"]


def test_retrieval_service_extracts_real_pdf_text_without_garbage_chunks():
    service = RetrievalService()

    office_context = service.retrieve_context(
        "What is the total amount of office space Amazon owned in North America in 2024?"
    )
    ai_context = service.retrieve_context(
        "I'm researching AMZN give me the current price and any relevant information about their AI business"
    )

    assert office_context["status"] == "ready"
    assert "Office space 29,551 9,104 North America" in office_context["results"][0]["excerpt"]
    assert "\\u00" not in office_context["results"][0]["excerpt"]
    assert "u00b8" not in office_context["results"][0]["excerpt"]

    assert ai_context["status"] == "ready"
    assert any(
        term in ai_context["results"][0]["excerpt"]
        for term in ("Trainium2", "Amazon Bedrock", "Anthropic")
    )
    assert "\\u00" not in ai_context["results"][0]["excerpt"]
    assert "u00b8" not in ai_context["results"][0]["excerpt"]

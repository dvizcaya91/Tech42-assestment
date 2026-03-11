from dataclasses import asdict, dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable, Dict, Iterable, List, Optional, Set
from urllib.request import urlopen
import zlib

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional until runtime dependency is installed
    PdfReader = None


@dataclass(frozen=True)
class SourceDocumentDefinition:
    document_id: str
    title: str
    filename: str
    source_url: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class IngestedSourceDocument:
    document_id: str
    title: str
    filename: str
    source_url: str
    local_path: str
    is_cached: bool
    size_bytes: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievedPassage:
    document_id: str
    title: str
    filename: str
    source_url: str
    local_path: str
    excerpt: str
    score: float
    matched_terms: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


AMAZON_REPORT_SOURCES = (
    SourceDocumentDefinition(
        document_id="amazon_2024_annual_report",
        title="Amazon 2024 Annual Report",
        filename="Amazon-2024-Annual-Report.pdf",
        source_url=(
            "https://s2.q4cdn.com/299287126/files/doc_financials/2025/ar/"
            "Amazon-2024-Annual-Report.pdf"
        ),
    ),
    SourceDocumentDefinition(
        document_id="amzn_q3_2025_earnings_release",
        title="AMZN Q3 2025 Earnings Release",
        filename="AMZN-Q3-2025-Earnings-Release.pdf",
        source_url=(
            "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q3/"
            "AMZN-Q3-2025-Earnings-Release.pdf"
        ),
    ),
    SourceDocumentDefinition(
        document_id="amzn_q2_2025_earnings_release",
        title="AMZN Q2 2025 Earnings Release",
        filename="AMZN-Q2-2025-Earnings-Release.pdf",
        source_url=(
            "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q2/"
            "AMZN-Q2-2025-Earnings-Release.pdf"
        ),
    ),
)

_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_STREAM_PATTERN = re.compile(
    rb"<<(?P<dictionary>.*?)>>\s*stream\r?\n(?P<data>.*?)\r?\nendstream",
    re.DOTALL,
)
_STOPWORDS = {
    "a",
    "about",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "give",
    "how",
    "i",
    "in",
    "is",
    "it",
    "last",
    "me",
    "of",
    "on",
    "or",
    "right",
    "recent",
    "recently",
    "researching",
    "the",
    "their",
    "to",
    "up",
    "was",
    "were",
    "what",
    "with",
    "year",
}
_QUERY_EXPANSIONS = {
    "analyst": {
        "analyst",
        "analysts",
        "consensus",
        "estimate",
        "estimates",
        "expectation",
        "expectations",
        "forecast",
        "guidance",
        "outlook",
        "predict",
        "predicted",
        "prediction",
        "predictions",
    },
    "predicted": {
        "analyst",
        "analysts",
        "consensus",
        "estimate",
        "estimates",
        "expectation",
        "forecast",
        "guidance",
        "outlook",
        "predicted",
        "projection",
        "projections",
    },
    "reports": {
        "earnings",
        "guidance",
        "outlook",
        "release",
        "report",
        "reports",
    },
    "ai": {
        "ai",
        "anthropic",
        "artificial",
        "bedrock",
        "business",
        "generative",
        "inferentia",
        "intelligence",
        "nova",
        "trainium",
    },
    "business": {
        "ai",
        "anthropic",
        "aws",
        "bedrock",
        "business",
        "cloud",
        "generative",
        "nova",
        "trainium",
    },
    "office": {
        "campus",
        "corporate",
        "foot",
        "feet",
        "headquarters",
        "lease",
        "leased",
        "north",
        "office",
        "owned",
        "real",
        "space",
        "square",
    },
    "space": {
        "foot",
        "feet",
        "leased",
        "north",
        "office",
        "owned",
        "space",
        "square",
    },
    "owned": {"foot", "feet", "office", "owned", "space", "square"},
    "north": {"america", "north", "office", "space"},
    "america": {"america", "north", "office", "space"},
}
_AI_PASSAGE_TERMS = {
    "agent",
    "agentcore",
    "ai",
    "alexa",
    "anthropic",
    "bedrock",
    "deepfleet",
    "genai",
    "generative",
    "inferentia",
    "nova",
    "sagemaker",
    "trainium",
    "trainium2",
}
_AI_PRODUCT_TERMS = {
    "agentcore",
    "anthropic",
    "bedrock",
    "deepfleet",
    "inferentia",
    "nova",
    "sagemaker",
    "trainium",
    "trainium2",
}


def _default_documents_directory() -> Path:
    configured_directory = os.getenv("RETRIEVAL_DOCUMENTS_DIRECTORY")
    if configured_directory:
        return Path(configured_directory)

    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp") / "aws-agentcore-stock-assistant-documents"

    return Path(__file__).resolve().parent / "source_documents"


def _pdftotext_binary() -> Optional[str]:
    return shutil.which("pdftotext")


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _tokenize(value: str) -> Set[str]:
    return {
        token
        for token in _WORD_PATTERN.findall(value.lower())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _expand_query_terms(query: str) -> Set[str]:
    expanded_terms = set()
    base_terms = _tokenize(query)
    for term in base_terms:
        expanded_terms.add(term)
        expanded_terms.update(_QUERY_EXPANSIONS.get(term, set()))
    return expanded_terms


def _sentence_chunks(text: str, max_sentences: int = 2) -> List[str]:
    sentences = [
        _normalize_whitespace(sentence)
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if _normalize_whitespace(sentence)
    ]
    if not sentences:
        return []

    chunks = []
    for start in range(len(sentences)):
        chunk = " ".join(sentences[start : start + max_sentences]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _paragraph_chunks(text: str) -> List[str]:
    paragraphs = [
        _normalize_whitespace(paragraph)
        for paragraph in re.split(r"\n\s*\n", text)
        if _normalize_whitespace(paragraph)
    ]
    return paragraphs


def _truncate_excerpt(text: str, limit: int = 360) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _is_pdf_octal_digit(character: str) -> bool:
    return character in "01234567"


def _decode_pdf_literal_string(raw_value: str) -> str:
    decoded_characters = []
    index = 0
    while index < len(raw_value):
        character = raw_value[index]
        if character != "\\":
            decoded_characters.append(character)
            index += 1
            continue

        index += 1
        if index >= len(raw_value):
            break

        escaped = raw_value[index]
        escape_map = {
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "b": "\b",
            "f": "\f",
            "(": "(",
            ")": ")",
            "\\": "\\",
        }
        if escaped in escape_map:
            decoded_characters.append(escape_map[escaped])
            index += 1
            continue

        if _is_pdf_octal_digit(escaped):
            octal_digits = [escaped]
            index += 1
            while (
                index < len(raw_value)
                and len(octal_digits) < 3
                and _is_pdf_octal_digit(raw_value[index])
            ):
                octal_digits.append(raw_value[index])
                index += 1
            decoded_characters.append(chr(int("".join(octal_digits), 8)))
            continue

        decoded_characters.append(escaped)
        index += 1

    return "".join(decoded_characters)


def _extract_pdf_strings(text: str) -> List[str]:
    strings = []
    current = []
    depth = 0
    escaped = False

    for character in text:
        if depth == 0:
            if character == "(":
                depth = 1
                current = []
            continue

        if escaped:
            current.append("\\" + character)
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == "(":
            depth += 1
            current.append(character)
            continue

        if character == ")":
            depth -= 1
            if depth == 0:
                decoded = _normalize_whitespace(
                    _decode_pdf_literal_string("".join(current))
                )
                if decoded:
                    strings.append(decoded)
                current = []
            else:
                current.append(character)
            continue

        current.append(character)

    return strings


def _extract_text_from_pdf_bytes(content_bytes: bytes) -> str:
    extracted_segments = []
    for match in _STREAM_PATTERN.finditer(content_bytes):
        stream_dictionary = match.group("dictionary")
        stream_data = match.group("data")
        if b"/FlateDecode" in stream_dictionary:
            try:
                stream_data = zlib.decompress(stream_data)
            except zlib.error:
                continue

        decoded_stream = stream_data.decode("latin-1", errors="ignore")
        string_segments = _extract_pdf_strings(decoded_stream)
        if string_segments:
            extracted_segments.extend(string_segments)
            continue

        printable_segments = re.findall(
            r"[A-Za-z0-9][A-Za-z0-9 ,.%$:/&;'\-]{4,}",
            decoded_stream,
        )
        extracted_segments.extend(_normalize_whitespace(segment) for segment in printable_segments)

    return _normalize_whitespace(" ".join(segment for segment in extracted_segments if segment))


def _extract_text_from_pdf_path(pdf_path: Path) -> str:
    pdftotext_binary = _pdftotext_binary()
    if pdftotext_binary is None:
        return ""

    try:
        result = subprocess.run(
            [pdftotext_binary, "-layout", "-nopgbrk", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""

    return _normalize_whitespace(result.stdout)


def _extract_text_with_pypdf(
    content_bytes: bytes,
    local_path: Optional[Path] = None,
) -> str:
    if PdfReader is None:
        return ""

    try:
        reader = PdfReader(str(local_path)) if local_path is not None else PdfReader(BytesIO(content_bytes))
    except Exception:
        return ""

    extracted_pages = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text:
            extracted_pages.append(page_text)

    return _normalize_whitespace(" ".join(extracted_pages))


def _extract_document_text(
    content_bytes: bytes,
    local_path: Optional[Path] = None,
) -> str:
    if content_bytes.startswith(b"%PDF"):
        pdf_text = _extract_text_with_pypdf(
            content_bytes,
            local_path=local_path,
        )
        if pdf_text:
            return pdf_text

    if local_path is not None and local_path.suffix.lower() == ".pdf":
        pdf_text = _extract_text_from_pdf_path(local_path)
        if pdf_text:
            return pdf_text

    if content_bytes.startswith(b"%PDF"):
        pdf_text = _extract_text_from_pdf_bytes(content_bytes)
        if pdf_text:
            return pdf_text

    for encoding in ("utf-8", "latin-1"):
        try:
            return _normalize_whitespace(content_bytes.decode(encoding))
        except UnicodeDecodeError:
            continue

    return _normalize_whitespace(content_bytes.decode("utf-8", errors="ignore"))


class RetrievalService:
    def __init__(self, documents_directory: Optional[Path] = None):
        self.documents_directory = (
            documents_directory
            if documents_directory is not None
            else _default_documents_directory()
        )

    def required_sources(self) -> List[Dict[str, str]]:
        return [source.to_dict() for source in AMAZON_REPORT_SOURCES]

    def ingest_documents(self) -> List[Dict[str, Any]]:
        self.documents_directory.mkdir(parents=True, exist_ok=True)

        ingested_documents = []
        for source in AMAZON_REPORT_SOURCES:
            local_path = self.documents_directory / source.filename
            ingested_documents.append(
                IngestedSourceDocument(
                    document_id=source.document_id,
                    title=source.title,
                    filename=source.filename,
                    source_url=source.source_url,
                    local_path=str(local_path),
                    is_cached=local_path.is_file(),
                    size_bytes=local_path.stat().st_size if local_path.is_file() else None,
                ).to_dict()
            )
        return ingested_documents

    def sync_required_documents(
        self,
        downloader: Optional[Callable[[str], Any]] = None,
    ) -> List[Dict[str, Any]]:
        download = downloader if downloader is not None else urlopen
        synced_documents = []

        for document in self.ingest_documents():
            local_path = Path(document["local_path"])
            if not local_path.is_file():
                with download(document["source_url"]) as response:
                    local_path.write_bytes(response.read())

            synced_documents.append(
                IngestedSourceDocument(
                    document_id=document["document_id"],
                    title=document["title"],
                    filename=document["filename"],
                    source_url=document["source_url"],
                    local_path=str(local_path),
                    is_cached=True,
                    size_bytes=local_path.stat().st_size,
                ).to_dict()
            )

        return synced_documents

    def load_cached_documents(self) -> List[Dict[str, Any]]:
        loaded_documents = []
        for document in self.ingest_documents():
            local_path = Path(document["local_path"])
            if not local_path.is_file():
                continue

            loaded_documents.append(
                {
                    "document_id": document["document_id"],
                    "title": document["title"],
                    "filename": document["filename"],
                    "source_url": document["source_url"],
                    "local_path": document["local_path"],
                    "content_bytes": local_path.read_bytes(),
                }
            )
        return loaded_documents

    def _ensure_required_documents_available(self) -> List[Dict[str, Any]]:
        loaded_documents = self.load_cached_documents()
        if len(loaded_documents) == len(AMAZON_REPORT_SOURCES):
            return loaded_documents

        try:
            self.sync_required_documents()
        except Exception:
            return loaded_documents

        return self.load_cached_documents()

    def build_retrieval_corpus(self, auto_sync: bool = False) -> List[Dict[str, Any]]:
        corpus = []
        documents = (
            self._ensure_required_documents_available()
            if auto_sync
            else self.load_cached_documents()
        )
        for document in documents:
            text = _extract_document_text(
                document["content_bytes"],
                local_path=Path(document["local_path"]),
            )
            if not text:
                continue

            chunks = _paragraph_chunks(text)
            if len(chunks) <= 1:
                chunks = _sentence_chunks(text)
            if not chunks:
                chunks = [text]

            corpus.append(
                {
                    "document_id": document["document_id"],
                    "title": document["title"],
                    "filename": document["filename"],
                    "source_url": document["source_url"],
                    "local_path": document["local_path"],
                    "content_text": text,
                    "chunks": chunks,
                }
            )
        return corpus

    def retrieve_context(self, query: str, limit: int = 3) -> Dict[str, Any]:
        query_terms = _expand_query_terms(query)
        ranked_passages = []

        for document in self.build_retrieval_corpus(auto_sync=True):
            title_terms = _tokenize(document["title"])
            for chunk in document["chunks"]:
                chunk_terms = _tokenize(chunk)
                if "ai" in query_terms and not (chunk_terms & _AI_PASSAGE_TERMS):
                    continue
                matched_terms = sorted(query_terms & (chunk_terms | title_terms))
                if not matched_terms:
                    continue

                score = float(len(matched_terms))
                phrase_bonus = 0.0
                chunk_lower = chunk.lower()
                if "ai" in query_terms and (chunk_terms & _AI_PASSAGE_TERMS):
                    phrase_bonus += 3.0
                if "ai" in query_terms and (chunk_terms & _AI_PRODUCT_TERMS):
                    phrase_bonus += 2.5
                if "north america" in chunk_lower and "north" in query_terms and "america" in query_terms:
                    phrase_bonus += 1.5
                if "office space" in chunk_lower and "office" in query_terms and "space" in query_terms:
                    phrase_bonus += 1.5
                if "generative ai" in chunk_lower and "ai" in query_terms:
                    phrase_bonus += 1.5
                if "analyst" in chunk_lower and (
                    "analyst" in query_terms or "predicted" in query_terms
                ):
                    phrase_bonus += 1.5

                ranked_passages.append(
                    RetrievedPassage(
                        document_id=document["document_id"],
                        title=document["title"],
                        filename=document["filename"],
                        source_url=document["source_url"],
                        local_path=document["local_path"],
                        excerpt=_truncate_excerpt(chunk),
                        score=round(score + phrase_bonus, 2),
                        matched_terms=matched_terms,
                    ).to_dict()
                )

        ranked_passages.sort(
            key=lambda passage: (
                -float(passage["score"]),
                passage["title"],
                passage["excerpt"],
            )
        )

        top_passages = ranked_passages[:limit]
        return {
            "query": query,
            "status": "ready" if top_passages else "no_matches",
            "result_count": len(top_passages),
            "results": top_passages,
            "formatted_context": self._format_context(query=query, passages=top_passages),
        }

    def _format_context(
        self,
        query: str,
        passages: Iterable[Dict[str, Any]],
    ) -> str:
        passage_list = list(passages)
        if not passage_list:
            return (
                "No matching report context was found in the cached Amazon assessment "
                "documents for query: {query}"
            ).format(query=query)

        context_lines = [
            "Retrieved Amazon report context for query: {query}".format(query=query)
        ]
        for index, passage in enumerate(passage_list, start=1):
            context_lines.append(
                "[{index}] {title} | matched_terms={matched_terms} | score={score}".format(
                    index=index,
                    title=passage["title"],
                    matched_terms=", ".join(passage["matched_terms"]),
                    score=passage["score"],
                )
            )
            context_lines.append(passage["excerpt"])

        return "\n".join(context_lines)

    def describe(self) -> Dict[str, object]:
        sources = self.ingest_documents()
        cached_documents = [
            source for source in sources if bool(source.get("is_cached"))
        ]
        retrieval_corpus = self.build_retrieval_corpus()
        return {
            "status": "configured",
            "source_count": len(sources),
            "cached_source_count": len(cached_documents),
            "indexed_document_count": len(retrieval_corpus),
            "documents_directory": str(self.documents_directory),
            "sources": sources,
        }

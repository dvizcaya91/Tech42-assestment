import json
from pathlib import Path


NOTEBOOK_PATH = (
    Path(__file__).resolve().parent
    / "notebooks"
    / "agentcore_stock_assistant_demo.ipynb"
)


def _load_notebook() -> dict:
    return json.loads(NOTEBOOK_PATH.read_text())


def _notebook_source() -> str:
    notebook = _load_notebook()
    return "\n".join("".join(cell.get("source", [])) for cell in notebook.get("cells", []))


def test_assessment_demo_notebook_exists_and_has_code_cells():
    notebook = _load_notebook()

    assert NOTEBOOK_PATH.is_file()
    assert notebook["nbformat"] == 4
    assert any(cell.get("cell_type") == "code" for cell in notebook["cells"])
    assert any(cell.get("cell_type") == "markdown" for cell in notebook["cells"])


def test_assessment_demo_notebook_covers_auth_queries_and_langfuse_trace_outputs():
    source = _notebook_source()

    assert '"aws"' in source
    assert '"cognito-idp"' in source
    assert '"initiate-auth"' in source
    assert "USER_PASSWORD_AUTH" in source
    assert "COGNITO_USER_POOL_CLIENT_ID" in source
    assert "AGENT_QUERY_URL" in source
    assert '"Authorization": f"Bearer {access_token}"' in source
    assert "application/x-ndjson" in source
    assert 'event.get("event") == "metadata"' in source
    assert 'event.get("event") == "message"' in source
    assert 'event.get("event") == "complete"' in source
    assert "trace_id" in source
    assert "trace_url" in source
    assert "Langfuse trace metadata" in source
    assert "What is the stock price for Amazon right now?" in source
    assert "What were the stock prices for Amazon in Q4 last year?" in source
    assert "Compare Amazon's recent stock performance to what analysts predicted in their reports" in source
    assert "I'm researching AMZN give me the current price and any relevant information about their AI business" in source
    assert "What is the total amount of office space Amazon owned in North America in 2024?" in source

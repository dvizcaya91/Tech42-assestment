# Assessment Backend

This directory contains the Python FastAPI backend scaffold for the stock assistant assessment.

## Layout

- `app/main.py` defines the FastAPI entrypoint.
- `app/api/` contains the HTTP layer and dependency wiring.
- `app/auth/` validates Cognito bearer tokens using deployment-provided settings.
- `app/agent/` contains the LangGraph ReAct orchestration service.
- `app/observability/` contains the Langfuse configuration and tracing adapter for agent execution.
- `app/tools/` contains finance tool registration and yfinance-backed market data tools.
- `app/retrieval/` contains the Amazon report ingestion setup and later retrieval components.

## Agent Orchestration

`app/agent/service.py` composes a LangGraph-backed ReAct-style workflow around the existing backend capabilities. The graph plans whether a query needs realtime pricing, historical pricing, retrieval over the required Amazon reports, or a combination of those steps, then synthesizes a single answer for the API layer. Both `run_query(...)` and the FastAPI streaming path consume LangGraph node updates through `.astream()` so tool and retrieval events reach clients incrementally.

When Langfuse is configured, the same streamed execution also records a root `agent_query` trace plus child observations for planning, tool execution, retrieval, and answer synthesis. The integration is optional at import time so local tests can still run without the Langfuse SDK installed.

Today the graph is deterministic so it remains testable offline, but it already has access to:

- `retrieve_realtime_stock_price`
- `retrieve_historical_stock_price`
- `RetrievalService.retrieve_context(...)`

This covers the assessment question types for current Amazon price, Q4 last-year prices, analyst-report comparisons, AI-business context, and Amazon's 2024 North America office-space figures.

## Finance Tooling

The backend tool registry currently exposes:

- `retrieve_realtime_stock_price`, which accepts a stock identifier such as `AMZN` and returns structured realtime market data from `yfinance`.
- `retrieve_historical_stock_price`, which accepts a stock identifier plus `YYYY-MM-DD` `start_date` and optional `end_date` inputs, then returns structured historical candles from `yfinance` for later agent streaming steps such as "Q4 last year" comparisons.

## Retrieval Corpus

The retrieval layer is pinned to exactly these three assignment documents and no others:

- `Amazon 2024 Annual Report`
- `AMZN Q3 2025 Earnings Release`
- `AMZN Q2 2025 Earnings Release`

`app/retrieval/service.py` defines the canonical manifest, exposes ingestion metadata to the agent layer, and can sync the PDFs into `app/retrieval/source_documents/` from the assignment-provided source URLs when network access is available. In AWS Lambda, retrieval caches those PDFs under `/tmp/aws-agentcore-stock-assistant-documents` because the deployed code package is read-only; set `RETRIEVAL_DOCUMENTS_DIRECTORY` to override that cache location.

After the PDFs are cached, `RetrievalService.retrieve_context(...)` builds a lightweight retrieval corpus from the three reports, ranks relevant excerpts for a user query, and returns both structured `results` and a `formatted_context` string that can be passed into later agent reasoning steps.

## Query Endpoint

The protected agent endpoint is `POST /query`, matching the Terraform `agent_query_route_path` default. Send a JSON body with a `query` field:

```json
{"query": "What is the stock price for Amazon right now?"}
```

The route returns `application/x-ndjson` and streams one JSON event per line. Each event includes `event`, `sequence`, and `data` fields so later stories can forward LangGraph `.astream()` output without changing the client contract. The current graph execution forwards `.astream()` node updates as reasoning, tool-result, retrieval-result, and final message events through that envelope.

The opening `metadata` event also includes a `trace` object. When Langfuse tracing is enabled, that object carries the Langfuse `trace_id` and `trace_url` for the streamed request so evaluators and the notebook can jump directly to the recorded execution in Langfuse Cloud.

## Cognito Configuration

Export the Terraform outputs before starting the backend so the API validates tokens against the deployed Cognito user pool instead of hard-coded values:

```bash
export COGNITO_USER_POOL_ID="$(terraform -chdir=../terraform output -raw cognito_user_pool_id)"
export COGNITO_USER_POOL_CLIENT_ID="$(terraform -chdir=../terraform output -raw cognito_user_pool_client_id)"
export COGNITO_USER_POOL_ISSUER_URL="$(terraform -chdir=../terraform output -raw cognito_user_pool_issuer_url)"
```

The API expects an `Authorization: Bearer <token>` header on protected routes and rejects missing, invalid, or expired Cognito tokens with `401 Unauthorized`.

## Langfuse Configuration

Export Langfuse settings before starting the backend to send traces to Langfuse Cloud Free Tier without hard-coded secrets:

```bash
export LANGFUSE_PUBLIC_KEY="<langfuse-public-key>"
export LANGFUSE_SECRET_KEY="<langfuse-secret-key>"
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"
export LANGFUSE_TRACING_ENABLED="true"
export LANGFUSE_ENVIRONMENT="assessment"
export LANGFUSE_RELEASE="aws-agentcore-stock-assistant"
```

If `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are present, tracing is enabled automatically even without `LANGFUSE_TRACING_ENABLED`. The backend flushes Langfuse at the end of each request so deployed streamed invocations persist their traces before the runtime goes idle.

## Local Run

Install the backend dependencies and start the application with Uvicorn:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

For the AWS runtime deployment path, `app.main` also exposes `app.main.handler` via Mangum so the same FastAPI app can run behind the Agentcore-facing Lambda/API Gateway integration defined in Terraform.


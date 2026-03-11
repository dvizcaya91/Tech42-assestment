from pathlib import Path
import py_compile


def test_assestment_directory_structure_exists():
    root = Path(__file__).resolve().parent

    assert root.is_dir()
    assert (root / "README.md").is_file()
    assert (root / "terraform").is_dir()
    assert (root / "backend").is_dir()
    assert (root / "notebooks").is_dir()


def test_terraform_scaffold_files_exist():
    terraform_root = Path(__file__).resolve().parent / "terraform"

    assert (terraform_root / "README.md").is_file()
    assert (terraform_root / "versions.tf").is_file()
    assert (terraform_root / "main.tf").is_file()
    assert (terraform_root / "variables.tf").is_file()
    assert (terraform_root / "outputs.tf").is_file()


def test_terraform_scaffold_sets_default_region_and_documents_plan_flow():
    terraform_root = Path(__file__).resolve().parent / "terraform"

    variables_tf = (terraform_root / "variables.tf").read_text()
    readme = (terraform_root / "README.md").read_text()

    assert 'variable "aws_region"' in variables_tf
    assert 'default     = "us-west-1"' in variables_tf
    assert "terraform init" in readme
    assert "terraform plan" in readme


def test_terraform_cognito_resources_and_outputs_exist():
    terraform_root = Path(__file__).resolve().parent / "terraform"

    main_tf = (terraform_root / "main.tf").read_text()
    variables_tf = (terraform_root / "variables.tf").read_text()
    outputs_tf = (terraform_root / "outputs.tf").read_text()
    readme = (terraform_root / "README.md").read_text()

    assert 'resource "aws_cognito_user_pool" "api_users"' in main_tf
    assert 'resource "aws_cognito_user_pool_client" "api_consumer"' in main_tf
    assert 'resource "aws_cognito_user_pool_domain" "api_users"' in main_tf
    assert 'variable "cognito_domain_prefix"' in variables_tf
    assert 'variable "cognito_callback_urls"' in variables_tf
    assert 'variable "cognito_logout_urls"' in variables_tf
    assert 'output "cognito_user_pool_id"' in outputs_tf
    assert 'output "cognito_user_pool_client_id"' in outputs_tf
    assert 'output "cognito_user_pool_issuer_url"' in outputs_tf
    assert 'output "cognito_oauth_token_url"' in outputs_tf
    assert "Cognito resources" in readme


def test_terraform_runtime_hosting_resources_and_outputs_exist():
    terraform_root = Path(__file__).resolve().parent / "terraform"

    main_tf = (terraform_root / "main.tf").read_text()
    variables_tf = (terraform_root / "variables.tf").read_text()
    outputs_tf = (terraform_root / "outputs.tf").read_text()
    versions_tf = (terraform_root / "versions.tf").read_text()
    readme = (terraform_root / "README.md").read_text()
    build_script = (terraform_root / "scripts" / "build_backend_package.sh").read_text()
    runtime_requirements = (
        Path(__file__).resolve().parent / "backend" / "requirements.runtime.txt"
    ).read_text()

    assert 'source  = "hashicorp/archive"' in versions_tf
    assert 'resource "aws_ecr_repository" "backend_image"' in main_tf
    assert 'resource "aws_s3_bucket" "agent_runtime_artifacts"' in main_tf
    assert 'resource "terraform_data" "agent_runtime_package_build"' in main_tf
    assert 'resource "aws_lambda_function" "agent_runtime"' in main_tf
    assert 'resource "aws_apigatewayv2_api" "agent_runtime"' in main_tf
    assert 'resource "aws_apigatewayv2_authorizer" "cognito_jwt"' in main_tf
    assert 'resource "aws_apigatewayv2_route" "agent_query"' in main_tf
    assert 'resource "aws_lambda_permission" "agent_runtime_api_gateway"' in main_tf
    assert 'variable "agent_query_route_path"' in variables_tf
    assert 'variable "agent_runtime_environment_variables"' in variables_tf
    assert 'variable "agent_runtime_memory_size"' in variables_tf
    assert 'variable "agent_runtime_timeout_seconds"' in variables_tf
    assert 'output "backend_ecr_repository_url"' in outputs_tf
    assert 'output "agent_runtime_function_name"' in outputs_tf
    assert 'output "agent_runtime_invoke_url"' in outputs_tf
    assert 'output "agent_runtime_query_url"' in outputs_tf
    assert "Runtime hosting resources" in readme
    assert "terraform apply" in readme
    assert "--requirement \"$BACKEND_RUNTIME_REQUIREMENTS\"" in build_script
    assert "--platform manylinux2014_x86_64" in build_script
    assert "cp -R \"$BACKEND_SOURCE_DIR/app\" \"$BACKEND_BUILD_DIR/app\"" in build_script
    assert "mangum" in runtime_requirements
    assert "yfinance" in runtime_requirements


def test_backend_scaffold_files_exist():
    backend_root = Path(__file__).resolve().parent / "backend"

    assert (backend_root / "README.md").is_file()
    assert (backend_root / "requirements.txt").is_file()
    assert (backend_root / "requirements.runtime.txt").is_file()
    assert (Path(__file__).resolve().parent / "test_agent_service.py").is_file()
    assert (Path(__file__).resolve().parent / "test_query_api.py").is_file()
    assert (backend_root / "app" / "__init__.py").is_file()
    assert (backend_root / "app" / "main.py").is_file()
    assert (backend_root / "app" / "api" / "__init__.py").is_file()
    assert (backend_root / "app" / "api" / "dependencies.py").is_file()
    assert (backend_root / "app" / "api" / "models.py").is_file()
    assert (backend_root / "app" / "api" / "routes.py").is_file()
    assert (backend_root / "app" / "auth" / "__init__.py").is_file()
    assert (backend_root / "app" / "auth" / "config.py").is_file()
    assert (backend_root / "app" / "auth" / "exceptions.py").is_file()
    assert (backend_root / "app" / "auth" / "service.py").is_file()
    assert (backend_root / "app" / "agent" / "__init__.py").is_file()
    assert (backend_root / "app" / "agent" / "service.py").is_file()
    assert (backend_root / "app" / "observability" / "__init__.py").is_file()
    assert (backend_root / "app" / "observability" / "config.py").is_file()
    assert (backend_root / "app" / "observability" / "langfuse.py").is_file()
    assert (backend_root / "app" / "tools" / "__init__.py").is_file()
    assert (backend_root / "app" / "tools" / "market_data.py").is_file()
    assert (backend_root / "app" / "tools" / "registry.py").is_file()
    assert (backend_root / "app" / "retrieval" / "__init__.py").is_file()
    assert (backend_root / "app" / "retrieval" / "service.py").is_file()
    assert (backend_root / "app" / "retrieval" / "source_documents" / "README.md").is_file()


def test_backend_fastapi_entrypoint_and_layer_separation_exist():
    backend_root = Path(__file__).resolve().parent / "backend"

    readme = (backend_root / "README.md").read_text()
    requirements = (backend_root / "requirements.txt").read_text()
    main_py = (backend_root / "app" / "main.py").read_text()
    dependencies_py = (backend_root / "app" / "api" / "dependencies.py").read_text()
    models_py = (backend_root / "app" / "api" / "models.py").read_text()
    routes_py = (backend_root / "app" / "api" / "routes.py").read_text()
    auth_config_py = (backend_root / "app" / "auth" / "config.py").read_text()
    auth_service_py = (backend_root / "app" / "auth" / "service.py").read_text()
    agent_service_py = (backend_root / "app" / "agent" / "service.py").read_text()
    observability_config_py = (
        backend_root / "app" / "observability" / "config.py"
    ).read_text()
    observability_langfuse_py = (
        backend_root / "app" / "observability" / "langfuse.py"
    ).read_text()
    tool_registry_py = (backend_root / "app" / "tools" / "registry.py").read_text()
    market_data_py = (backend_root / "app" / "tools" / "market_data.py").read_text()
    retrieval_service_py = (backend_root / "app" / "retrieval" / "service.py").read_text()
    retrieval_docs_readme = (
        backend_root / "app" / "retrieval" / "source_documents" / "README.md"
    ).read_text()

    assert "uvicorn app.main:app --reload" in readme
    assert "terraform -chdir=../terraform output -raw cognito_user_pool_id" in readme
    assert "terraform -chdir=../terraform output -raw cognito_user_pool_client_id" in readme
    assert "terraform -chdir=../terraform output -raw cognito_user_pool_issuer_url" in readme
    assert "app.main.handler" in readme
    assert "Authorization: Bearer <token>" in readme
    assert "fastapi" in requirements
    assert "langfuse" in requirements
    assert "mangum" in requirements
    assert "PyJWT[crypto]" in requirements
    assert "langgraph" in requirements
    assert "uvicorn" in requirements
    assert "yfinance" in requirements
    assert "from fastapi import FastAPI" in main_py
    assert "def create_app() -> FastAPI:" in main_py
    assert "app.include_router(api_router)" in main_py
    assert "app = create_app()" in main_py
    assert 'handler = Mangum(app, lifespan="off") if Mangum is not None else None' in main_py
    assert "def get_cognito_settings() -> CognitoSettings:" in dependencies_py
    assert "def get_token_verifier() -> CognitoTokenVerifier:" in dependencies_py
    assert "def get_langfuse_settings() -> LangfuseSettings:" in dependencies_py
    assert "def get_agent_execution_tracer() -> AgentExecutionTracer:" in dependencies_py
    assert "def require_authenticated_user(" in dependencies_py
    assert 'detail="Missing bearer token."' in dependencies_py
    assert "status.HTTP_401_UNAUTHORIZED" in dependencies_py
    assert "AgentService" in dependencies_py
    assert "ToolRegistry.default()" in dependencies_py
    assert "RetrievalService()" in dependencies_py
    assert "execution_tracer=get_agent_execution_tracer()" in dependencies_py
    assert "class QueryRequest(BaseModel)" in models_py
    assert "class StreamEvent(BaseModel)" in models_py
    assert "@router.get(\"/health\")" in routes_py
    assert "@router.post(\"/query\")" in routes_py
    assert "APIRouter(dependencies=[Depends(require_authenticated_user)])" in routes_py
    assert "Depends(get_agent_service)" in routes_py
    assert "StreamingResponse" in routes_py
    assert 'media_type="application/x-ndjson"' in routes_py
    assert "def _stream_agent_events(" in routes_py
    assert "COGNITO_USER_POOL_ID" in auth_config_py
    assert "COGNITO_USER_POOL_CLIENT_ID" in auth_config_py
    assert "COGNITO_USER_POOL_ISSUER_URL" in auth_config_py
    assert '.well-known/jwks.json' in auth_config_py
    assert "PyJWKClient" in auth_service_py
    assert "ExpiredSignatureError" in auth_service_py
    assert 'algorithms=["RS256"]' in auth_service_py
    assert 'token_use == "access"' in auth_service_py
    assert 'token_use == "id"' in auth_service_py
    assert "class AgentService" in agent_service_py
    assert "class AgentStreamEvent" in agent_service_py
    assert "StateGraph" in agent_service_py
    assert 'workflow.add_node("plan"' in agent_service_py
    assert 'workflow.add_node("execute_tools"' in agent_service_py
    assert 'workflow.add_node("retrieve_context"' in agent_service_py
    assert 'workflow.add_node("answer"' in agent_service_py
    assert "def run_query(" in agent_service_py
    assert "async def stream_query(" in agent_service_py
    assert "execution_tracer" in agent_service_py
    assert ".astream(" in agent_service_py
    assert '"observability": self.execution_tracer.describe()' in agent_service_py
    assert '"trace": trace_handle.trace_metadata()' in agent_service_py
    assert "trace_handle.record_graph_update(" in agent_service_py
    assert 'event="reasoning"' in agent_service_py
    assert 'event="tool_result"' in agent_service_py
    assert 'event="retrieval_result"' in agent_service_py
    assert '"supports_langgraph_astream": True' in agent_service_py
    assert '"agent": "langgraph-react"' in agent_service_py
    assert "react_style" in agent_service_py
    assert "retrieve_realtime_stock_price" in readme
    assert "retrieve_historical_stock_price" in readme
    assert "LangGraph-backed ReAct-style workflow" in readme
    assert "RetrievalService.retrieve_context(...)" in readme
    assert "Amazon 2024 Annual Report" in readme
    assert "AMZN Q3 2025 Earnings Release" in readme
    assert "AMZN Q2 2025 Earnings Release" in readme
    assert "RetrievalService.retrieve_context" in readme
    assert "formatted_context" in readme
    assert "LANGFUSE_PUBLIC_KEY" in readme
    assert "LANGFUSE_SECRET_KEY" in readme
    assert "LANGFUSE_BASE_URL" in readme
    assert "LANGFUSE_TRACING_ENABLED" in readme
    assert "trace_id" in readme
    assert "trace_url" in readme
    assert "Langfuse Cloud" in readme
    assert "class LangfuseSettings" in observability_config_py
    assert "LANGFUSE_PUBLIC_KEY" in observability_config_py
    assert "LANGFUSE_SECRET_KEY" in observability_config_py
    assert "LANGFUSE_BASE_URL" in observability_config_py
    assert "LANGFUSE_HOST" in observability_config_py
    assert "LANGFUSE_TRACING_ENABLED" in observability_config_py
    assert "class NoOpAgentExecutionTracer" in observability_langfuse_py
    assert "class _LangfuseTraceHandle" in observability_langfuse_py
    assert "start_as_current_observation" in observability_langfuse_py
    assert 'name="agent_query"' in observability_langfuse_py
    assert "def build_agent_execution_tracer(" in observability_langfuse_py
    assert "flush()" in observability_langfuse_py
    assert "class ToolRegistry" in tool_registry_py
    assert '"retrieve_realtime_stock_price": retrieve_realtime_stock_price' in tool_registry_py
    assert '"retrieve_historical_stock_price": retrieve_historical_stock_price' in tool_registry_py
    assert "def get_tool(" in tool_registry_py
    assert "import yfinance as yf" in market_data_py
    assert "class RealtimeStockPriceResult" in market_data_py
    assert "class HistoricalStockPriceResult" in market_data_py
    assert "def retrieve_realtime_stock_price(" in market_data_py
    assert "def retrieve_historical_stock_price(" in market_data_py
    assert 'tool_name="retrieve_realtime_stock_price"' in market_data_py
    assert 'tool_name="retrieve_historical_stock_price"' in market_data_py
    assert "class RetrievalService" in retrieval_service_py
    assert "class SourceDocumentDefinition" in retrieval_service_py
    assert "class IngestedSourceDocument" in retrieval_service_py
    assert "class RetrievedPassage" in retrieval_service_py
    assert "AMAZON_REPORT_SOURCES" in retrieval_service_py
    assert "Amazon-2024-Annual-Report.pdf" in retrieval_service_py
    assert "AMZN-Q3-2025-Earnings-Release.pdf" in retrieval_service_py
    assert "AMZN-Q2-2025-Earnings-Release.pdf" in retrieval_service_py
    assert "def sync_required_documents(" in retrieval_service_py
    assert "def load_cached_documents(" in retrieval_service_py
    assert "def build_retrieval_corpus(" in retrieval_service_py
    assert "def retrieve_context(" in retrieval_service_py
    assert '"formatted_context"' in retrieval_service_py
    assert "Store only the required Amazon source PDFs" in retrieval_docs_readme


def test_assessment_deployment_guide_documents_deploy_run_and_invocation_flow():
    root = Path(__file__).resolve().parent
    readme = (root / "README.md").read_text()

    assert "terraform init" in readme
    assert "terraform apply" in readme
    assert "agent_runtime_query_url" in readme
    assert "cognito_oauth_token_url" in readme
    assert "admin-create-user" in readme
    assert "initiate-auth" in readme
    assert "uvicorn app.main:app --reload" in readme
    assert "Authorization: Bearer <token>" in readme
    assert "application/x-ndjson" in readme


def test_backend_python_files_compile():
    backend_root = Path(__file__).resolve().parent / "backend"

    for python_file in backend_root.rglob("*.py"):
        py_compile.compile(str(python_file), doraise=True)

# AWS Agentcore Stock Assistant Assessment

This directory contains the deployable assets for the assessment:

- `terraform/` provisions Cognito, the initial runtime surface, and shared deployment outputs.
- `backend/` contains the FastAPI application that serves the authenticated streaming `POST /query` endpoint.
- `notebooks/` is reserved for evaluator-facing notebook deliverables.

## Prerequisites

- AWS credentials with permission to manage Cognito, API Gateway, Lambda, IAM, CloudWatch Logs, and ECR in `us-west-1`
- Terraform 1.6+ and the AWS CLI
- Python 3.11+ for the backend

## 1. Deploy the AWS infrastructure

Initialize and review the Terraform plan:

```bash
cd assestment/terraform
terraform init
terraform plan \
  -var="project_name=aws-agentcore-stock-assistant" \
  -var="environment=dev"
```

Apply the stack when the plan looks correct:

```bash
cd assestment/terraform
terraform apply \
  -var="project_name=aws-agentcore-stock-assistant" \
  -var="environment=dev"
```

This provisions:

- An Amazon Cognito user pool, app client, and hosted UI domain for authenticated users
- An ECR repository for the FastAPI backend image
- A Cognito-protected API Gateway HTTP API on `POST /query`
- A Lambda-hosted FastAPI runtime built from the backend source tree and deployed by Terraform

The Cognito hosted-domain label is derived from the project and environment names, but Cognito reserved words such as `aws` are rewritten in that label automatically. If you pass `cognito_domain_prefix` manually, avoid reserved words there as well.

## 2. Capture the deployment outputs

The evaluator needs the Terraform outputs below to authenticate and invoke the deployed runtime:

```bash
export AWS_REGION="$(terraform -chdir=assestment/terraform output -raw aws_region)"
export COGNITO_USER_POOL_ID="$(terraform -chdir=assestment/terraform output -raw cognito_user_pool_id)"
export COGNITO_USER_POOL_CLIENT_ID="$(terraform -chdir=assestment/terraform output -raw cognito_user_pool_client_id)"
export COGNITO_USER_POOL_ISSUER_URL="$(terraform -chdir=assestment/terraform output -raw cognito_user_pool_issuer_url)"
export COGNITO_OAUTH_AUTHORIZE_URL="$(terraform -chdir=assestment/terraform output -raw cognito_oauth_authorize_url)"
export COGNITO_OAUTH_TOKEN_URL="$(terraform -chdir=assestment/terraform output -raw cognito_oauth_token_url)"
export AGENT_QUERY_METHOD="$(terraform -chdir=assestment/terraform output -raw agent_runtime_query_method)"
export AGENT_QUERY_URL="$(terraform -chdir=assestment/terraform output -raw agent_runtime_query_url)"
```

Output usage:

- `agent_runtime_query_url`: the deployed HTTPS endpoint to call
- `agent_runtime_query_method`: the HTTP verb the client must use
- `cognito_user_pool_client_id`: the Cognito app client used for user login
- `cognito_oauth_authorize_url` and `cognito_oauth_token_url`: the hosted OAuth endpoints for browser or notebook flows
- `cognito_user_pool_issuer_url`: the JWT issuer the FastAPI backend validates against

## 3. Create an evaluator user and fetch a Cognito token

Create a test user in the deployed user pool:

```bash
export EVALUATOR_EMAIL="evaluator@example.com"
export EVALUATOR_PASSWORD="TempPassw0rd!"

aws cognito-idp admin-create-user \
  --region "$AWS_REGION" \
  --user-pool-id "$COGNITO_USER_POOL_ID" \
  --username "$EVALUATOR_EMAIL" \
  --user-attributes Name=email,Value="$EVALUATOR_EMAIL" Name=email_verified,Value=true \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --region "$AWS_REGION" \
  --user-pool-id "$COGNITO_USER_POOL_ID" \
  --username "$EVALUATOR_EMAIL" \
  --password "$EVALUATOR_PASSWORD" \
  --permanent
```

Exchange those credentials for an access token:

```bash
export ACCESS_TOKEN="$(
  aws cognito-idp initiate-auth \
    --region "$AWS_REGION" \
    --client-id "$COGNITO_USER_POOL_CLIENT_ID" \
    --auth-flow USER_PASSWORD_AUTH \
    --auth-parameters USERNAME="$EVALUATOR_EMAIL",PASSWORD="$EVALUATOR_PASSWORD" \
    --query 'AuthenticationResult.AccessToken' \
    --output text
)"
```

If the evaluator prefers a browser-based OAuth flow instead of AWS CLI authentication, reuse `cognito_oauth_authorize_url` and `cognito_oauth_token_url` from the Terraform outputs.

## 4. Run the FastAPI backend locally

Install the backend dependencies:

```bash
cd assestment/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Export the deployment-backed configuration before starting the service:

```bash
export COGNITO_USER_POOL_ID="$(terraform -chdir=../terraform output -raw cognito_user_pool_id)"
export COGNITO_USER_POOL_CLIENT_ID="$(terraform -chdir=../terraform output -raw cognito_user_pool_client_id)"
export COGNITO_USER_POOL_ISSUER_URL="$(terraform -chdir=../terraform output -raw cognito_user_pool_issuer_url)"
```

Optional Langfuse configuration for trace capture:

```bash
export LANGFUSE_PUBLIC_KEY="<langfuse-public-key>"
export LANGFUSE_SECRET_KEY="<langfuse-secret-key>"
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"
export LANGFUSE_TRACING_ENABLED="true"
```

Start the backend:

```bash
uvicorn app.main:app --reload
```

## 5. Invoke the authenticated query endpoint

Against the locally running FastAPI service:

```bash
curl -N \
  -X POST "http://127.0.0.1:8000/query" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the stock price for Amazon right now?"}'
```

Against the deployed runtime surface:

```bash
curl -N \
  -X "$AGENT_QUERY_METHOD" "$AGENT_QUERY_URL" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the stock price for Amazon right now?"}'
```

Both flows use the same request contract:

- Method: `POST`
- Path: `/query`
- Header: `Authorization: Bearer <token>`
- Body: `{"query":"<question>"}`  

The response is newline-delimited JSON (`application/x-ndjson`) with `event`, `sequence`, and `data` fields. When Langfuse is enabled, the opening `metadata` event also includes the trace identifiers needed to inspect the run in Langfuse Cloud.

## 6. Deployed runtime notes

`terraform apply` builds the Lambda package from `assestment/backend/requirements.runtime.txt` plus `assestment/backend/app/`, injects the deployed Cognito settings into the function environment, and publishes the archive to the FastAPI-backed runtime behind API Gateway. Keep using the same local backend flow when you want iterative development, but the deployed `AGENT_QUERY_URL` now serves the real FastAPI application instead of a placeholder response.

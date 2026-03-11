# Terraform Scaffold

This directory contains the Terraform project scaffold for the AWS Agentcore stock assistant assessment.

## Files

- `versions.tf`: Terraform and provider requirements.
- `main.tf`: Shared locals, the AWS provider configuration, Cognito authentication resources, and the runtime-hosting stack.
- `variables.tf`: Deployment inputs with `us-west-1` as the default region plus Cognito and runtime-hosting settings.
- `outputs.tf`: Shared deployment outputs plus the Cognito and runtime endpoint values needed by the backend and notebook flow.
- `scripts/build_backend_package.sh`: Local build helper that installs the Lambda runtime dependencies and stages the FastAPI application package for Terraform.

## Initialize Terraform

```bash
cd assestment/terraform
terraform init
```

## Review the execution plan

```bash
cd assestment/terraform
terraform plan \
  -var="project_name=aws-agentcore-stock-assistant" \
  -var="environment=dev"
```

To override the generated Cognito hosted UI domain or notebook callback URLs during planning, add variables such as:

```bash
terraform plan \
  -var="project_name=aws-agentcore-stock-assistant" \
  -var="environment=dev" \
  -var="cognito_domain_prefix=agentcore-stock-assistant-dev" \
  -var='cognito_callback_urls=["http://localhost:8888/callback"]' \
  -var='cognito_logout_urls=["http://localhost:8888/logout"]'
```

Avoid Cognito reserved words such as `aws` in `cognito_domain_prefix`. The module now rewrites reserved tokens in the generated default domain label, but explicit overrides should still use a clean prefix like `agentcore-stock-assistant-dev`.

To adjust the initial runtime surface during planning, add variables such as:

```bash
terraform plan \
  -var="project_name=aws-agentcore-stock-assistant" \
  -var="environment=dev" \
  -var="agent_query_route_path=/query" \
  -var="agent_runtime_memory_size=512"
```

## Cognito resources

This story provisions:

- An Amazon Cognito user pool with email-based sign-in and password policies.
- A Cognito app client configured for user authentication and OAuth code flow.
- A Cognito hosted UI domain for notebook or browser-based login flows.

Key outputs include the user pool ID, app client ID, issuer URL, hosted UI OAuth endpoints, and the initial runtime endpoint values consumed by later backend and notebook stories.

## Runtime hosting resources

This story adds the runtime infrastructure needed to stand up the deployed Cognito-protected FastAPI service for the assessment:

- An Amazon ECR repository for the FastAPI backend image that later stories will build and publish.
- An S3 artifact bucket, a CloudWatch log group, and an IAM execution role for the Lambda runtime.
- A Terraform-driven packaging step that installs the runtime dependencies from `assestment/backend/requirements.runtime.txt`, copies the FastAPI `app/` package, uploads the resulting archive to S3, and deploys it to Lambda with the Cognito configuration injected as environment variables.
- An Amazon API Gateway HTTP API that fronts the runtime target, protects `POST /query` with the Cognito JWT issuer/client, and exposes notebook-ready invoke URLs as Terraform outputs.

`terraform apply` now builds and deploys the actual FastAPI runtime instead of a placeholder target, so the notebook-facing `POST /query` endpoint and the local backend share the same application code path through `app.main.handler`.

output "aws_region" {
  description = "AWS region that backend deployment scripts and evaluator notebooks should target."
  value       = var.aws_region
}

output "deployment_environment" {
  description = "Environment name shared by downstream deployment steps."
  value       = var.environment
}

output "resource_name_prefix" {
  description = "Prefix to reuse when naming Cognito, runtime, and related assessment resources."
  value       = local.name_prefix
}

output "default_tags" {
  description = "Common Terraform tags applied to assessment resources."
  value       = local.common_tags
}

output "cognito_user_pool_id" {
  description = "Amazon Cognito user pool identifier for backend token validation and notebook authentication."
  value       = aws_cognito_user_pool.api_users.id
}

output "cognito_user_pool_arn" {
  description = "Amazon Cognito user pool ARN for IAM and deployment integrations."
  value       = aws_cognito_user_pool.api_users.arn
}

output "cognito_user_pool_client_id" {
  description = "Cognito app client identifier used by notebook and other API consumers."
  value       = aws_cognito_user_pool_client.api_consumer.id
}

output "cognito_user_pool_domain" {
  description = "Hosted Cognito domain base URL used for browser-based user authentication flows."
  value       = "https://${aws_cognito_user_pool_domain.api_users.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "cognito_user_pool_issuer_url" {
  description = "JWT issuer URL the backend can use to validate Cognito-issued tokens."
  value       = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.api_users.id}"
}

output "cognito_oauth_authorize_url" {
  description = "Hosted UI authorization endpoint for notebook-driven login flows."
  value       = "https://${aws_cognito_user_pool_domain.api_users.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/authorize"
}

output "cognito_oauth_token_url" {
  description = "Hosted UI token endpoint for notebook-driven token exchange."
  value       = "https://${aws_cognito_user_pool_domain.api_users.domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/token"
}

output "backend_ecr_repository_name" {
  description = "Amazon ECR repository name that stores the FastAPI backend image for runtime deployment."
  value       = aws_ecr_repository.backend_image.name
}

output "backend_ecr_repository_url" {
  description = "Amazon ECR repository URL used by deployment automation when publishing the FastAPI backend image."
  value       = aws_ecr_repository.backend_image.repository_url
}

output "agent_runtime_execution_role_arn" {
  description = "IAM role ARN attached to the initial runtime target and reusable by later deployment steps."
  value       = aws_iam_role.agent_runtime_execution.arn
}

output "agent_runtime_function_name" {
  description = "Lambda function name serving the deployed FastAPI runtime."
  value       = aws_lambda_function.agent_runtime.function_name
}

output "agent_runtime_http_api_id" {
  description = "HTTP API identifier fronting the agent runtime."
  value       = aws_apigatewayv2_api.agent_runtime.id
}

output "agent_runtime_invoke_url" {
  description = "Base invoke URL for the Cognito-protected agent runtime API."
  value       = aws_apigatewayv2_stage.agent_runtime.invoke_url
}

output "agent_runtime_query_method" {
  description = "HTTP method notebook clients should use when invoking the agent query endpoint."
  value       = "POST"
}

output "agent_runtime_query_url" {
  description = "Cognito-protected agent query URL intended for notebook and evaluator invocation flows."
  value       = "${trimsuffix(aws_apigatewayv2_stage.agent_runtime.invoke_url, "/")}${local.agent_query_route_path}"
}

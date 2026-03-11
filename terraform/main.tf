locals {
  name_prefix                    = "${var.project_name}-${var.environment}"
  raw_cognito_domain_prefix      = lower(coalesce(var.cognito_domain_prefix, local.name_prefix))
  sanitized_cognito_domain_label = replace(local.raw_cognito_domain_prefix, "/[^a-z0-9-]/", "-")
  reserved_safe_cognito_label    = replace(local.sanitized_cognito_domain_label, "aws", "agt")
  cognito_domain_prefix          = trim(substr(replace(local.reserved_safe_cognito_label, "/-+/", "-"), 0, 63), "-")
  agent_query_route_path         = startswith(var.agent_query_route_path, "/") ? var.agent_query_route_path : "/${var.agent_query_route_path}"
  backend_source_root            = abspath("${path.module}/../backend")
  backend_build_directory        = "/tmp/${local.name_prefix}-backend-lambda-build"
  backend_package_zip_path       = "/tmp/${local.name_prefix}-backend-lambda.zip"
  backend_runtime_source_files = concat(
    [
      for file in fileset(local.backend_source_root, "app/**") :
      "${local.backend_source_root}/${file}"
      if !strcontains(file, "__pycache__/")
    ],
    [
      "${local.backend_source_root}/requirements.runtime.txt",
      "${path.module}/scripts/build_backend_package.sh",
    ]
  )
  backend_runtime_source_hash = sha256(
    join(
      "",
      [
        for file in local.backend_runtime_source_files :
        filesha256(file)
      ]
    )
  )
  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.additional_tags
  )
}

data "aws_caller_identity" "current" {}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

resource "aws_cognito_user_pool" "api_users" {
  name                     = "${local.name_prefix}-users"
  auto_verified_attributes = ["email"]
  deletion_protection      = var.cognito_deletion_protection
  mfa_configuration        = "OFF"
  username_attributes      = ["email"]

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
  }
}

resource "aws_cognito_user_pool_client" "api_consumer" {
  name                                 = "${local.name_prefix}-client"
  user_pool_id                         = aws_cognito_user_pool.api_users.id
  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  supported_identity_providers         = ["COGNITO"]
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  callback_urls                        = var.cognito_callback_urls
  logout_urls                          = var.cognito_logout_urls

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_pool_domain" "api_users" {
  domain       = local.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.api_users.id
}

resource "aws_ecr_repository" "backend_image" {
  name                 = "${local.name_prefix}-backend"
  image_tag_mutability = var.backend_image_tag_mutability

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_s3_bucket" "agent_runtime_artifacts" {
  bucket        = "${local.name_prefix}-lambda-artifacts-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "agent_runtime_artifacts" {
  bucket = aws_s3_bucket.agent_runtime_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudwatch_log_group" "agent_runtime" {
  name              = "/aws/lambda/${local.name_prefix}-agent-runtime"
  retention_in_days = var.agent_runtime_log_retention_days
}

resource "aws_iam_role" "agent_runtime_execution" {
  name = "${local.name_prefix}-agent-runtime-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "agent_runtime_basic_execution" {
  role       = aws_iam_role.agent_runtime_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "terraform_data" "agent_runtime_package_build" {
  triggers_replace = [local.backend_runtime_source_hash]

  provisioner "local-exec" {
    command     = "bash ${path.module}/scripts/build_backend_package.sh"
    interpreter = ["/bin/bash", "-c"]
    working_dir = path.module

    environment = {
      BACKEND_SOURCE_DIR           = local.backend_source_root
      BACKEND_BUILD_DIR            = local.backend_build_directory
      BACKEND_RUNTIME_REQUIREMENTS = "${local.backend_source_root}/requirements.runtime.txt"
    }
  }
}

data "archive_file" "agent_runtime" {
  type        = "zip"
  source_dir  = local.backend_build_directory
  output_path = local.backend_package_zip_path

  depends_on = [terraform_data.agent_runtime_package_build]
}

resource "aws_s3_object" "agent_runtime_package" {
  bucket = aws_s3_bucket.agent_runtime_artifacts.id
  key    = "lambda/${local.backend_runtime_source_hash}.zip"
  source = data.archive_file.agent_runtime.output_path
  etag   = data.archive_file.agent_runtime.output_md5

  depends_on = [
    aws_s3_bucket_public_access_block.agent_runtime_artifacts,
    data.archive_file.agent_runtime,
  ]
}

moved {
  from = aws_lambda_function.agent_runtime_placeholder
  to   = aws_lambda_function.agent_runtime
}

moved {
  from = aws_apigatewayv2_integration.agent_runtime_placeholder
  to   = aws_apigatewayv2_integration.agent_runtime
}

resource "aws_lambda_function" "agent_runtime" {
  function_name    = "${local.name_prefix}-agent-runtime"
  role             = aws_iam_role.agent_runtime_execution.arn
  handler          = "app.main.handler"
  runtime          = "python3.11"
  s3_bucket        = aws_s3_bucket.agent_runtime_artifacts.id
  s3_key           = aws_s3_object.agent_runtime_package.key
  source_code_hash = data.archive_file.agent_runtime.output_base64sha256
  timeout          = var.agent_runtime_timeout_seconds
  memory_size      = var.agent_runtime_memory_size

  environment {
    variables = merge(
      {
        PROJECT_NAME                 = var.project_name
        ENVIRONMENT                  = var.environment
        COGNITO_USER_POOL_ID         = aws_cognito_user_pool.api_users.id
        COGNITO_USER_POOL_CLIENT_ID  = aws_cognito_user_pool_client.api_consumer.id
        COGNITO_USER_POOL_ISSUER_URL = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.api_users.id}"
      },
      var.agent_runtime_environment_variables
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.agent_runtime,
    aws_iam_role_policy_attachment.agent_runtime_basic_execution,
    aws_s3_object.agent_runtime_package,
  ]
}

resource "aws_apigatewayv2_api" "agent_runtime" {
  name          = "${local.name_prefix}-agent-runtime"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_authorizer" "cognito_jwt" {
  api_id           = aws_apigatewayv2_api.agent_runtime.id
  name             = "${local.name_prefix}-cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.api_consumer.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.api_users.id}"
  }
}

resource "aws_apigatewayv2_integration" "agent_runtime" {
  api_id                 = aws_apigatewayv2_api.agent_runtime.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.agent_runtime.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "agent_query" {
  api_id             = aws_apigatewayv2_api.agent_runtime.id
  route_key          = "POST ${local.agent_query_route_path}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito_jwt.id
  target             = "integrations/${aws_apigatewayv2_integration.agent_runtime.id}"
}

resource "aws_apigatewayv2_stage" "agent_runtime" {
  api_id      = aws_apigatewayv2_api.agent_runtime.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "agent_runtime_api_gateway" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_runtime.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.agent_runtime.execution_arn}/*/*"
}

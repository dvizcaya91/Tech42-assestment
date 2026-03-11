variable "aws_region" {
  description = "AWS region used for this assessment deployment."
  type        = string
  default     = "us-west-1"
}

variable "project_name" {
  description = "Stable project identifier used to build AWS resource names."
  type        = string
  default     = "aws-agentcore-stock-assistant"
}

variable "environment" {
  description = "Deployment environment suffix applied to resource names."
  type        = string
  default     = "dev"
}

variable "additional_tags" {
  description = "Optional extra tags merged into the default Terraform tags."
  type        = map(string)
  default     = {}
}

variable "cognito_domain_prefix" {
  description = "Optional Cognito hosted UI domain prefix override; defaults to a sanitized project/environment name and rewrites reserved Cognito tokens such as aws."
  type        = string
  default     = null
}

variable "cognito_callback_urls" {
  description = "Callback URLs allowed for the Cognito app client OAuth flow."
  type        = list(string)
  default     = ["http://localhost:8501/callback"]
}

variable "cognito_logout_urls" {
  description = "Logout URLs allowed for the Cognito app client OAuth flow."
  type        = list(string)
  default     = ["http://localhost:8501/logout"]
}

variable "cognito_deletion_protection" {
  description = "Deletion protection mode for the Cognito user pool."
  type        = string
  default     = "ACTIVE"
}

variable "backend_image_tag_mutability" {
  description = "Tag mutability mode for the ECR repository that will store the FastAPI backend image."
  type        = string
  default     = "MUTABLE"
}

variable "agent_runtime_memory_size" {
  description = "Memory size in MB for the placeholder runtime target fronted by API Gateway until the FastAPI container is deployed."
  type        = number
  default     = 512
}

variable "agent_runtime_timeout_seconds" {
  description = "Execution timeout for the placeholder runtime target."
  type        = number
  default     = 30
}

variable "agent_runtime_log_retention_days" {
  description = "Retention period for runtime logs written to CloudWatch Logs."
  type        = number
  default     = 14
}

variable "agent_runtime_environment_variables" {
  description = "Additional environment variables merged into the deployed FastAPI Lambda runtime."
  type        = map(string)
  default     = {}
}

variable "agent_query_route_path" {
  description = "HTTP path exposed to authenticated clients for agent query requests."
  type        = string
  default     = "/query"
}

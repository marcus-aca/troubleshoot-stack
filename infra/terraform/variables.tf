variable "region" {
  type        = string
  description = "AWS region for all resources."
  default     = "us-west-2"
}


variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC."
  default     = "10.10.0.0/16"
}

variable "az_count" {
  type        = number
  description = "Number of availability zones to use."
  default     = 2
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for public subnets."
  default     = ["10.10.0.0/24", "10.10.1.0/24"]
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks for private subnets."
  default     = ["10.10.10.0/24", "10.10.11.0/24"]
}

variable "ecs_cluster_name" {
  type        = string
  description = "ECS cluster name."
  default     = "troubleshooter"
}

variable "ecs_env_vars" {
  type        = map(string)
  description = "Plaintext environment variables for the ECS task."
  default     = {}
}

variable "llm_mode" {
  type        = string
  description = "LLM mode for the API service (bedrock or stub)."
  default     = "bedrock"
}

variable "bedrock_model_id" {
  type        = string
  description = "Bedrock model id to use for LLM calls."
  default     = "openai.gpt-oss-20b-1:0"
}

variable "llm_cost_per_1k_tokens" {
  type        = number
  description = "Cost per 1K tokens in USD for the active model."
  default     = 0.002
}

variable "cw_metrics_enabled" {
  type        = bool
  description = "Enable CloudWatch metrics emission from the API service."
  default     = true
}

variable "cw_metrics_namespace" {
  type        = string
  description = "CloudWatch metrics namespace for LLM observability."
  default     = "Troubleshooter/LLM"
}

variable "ecr_repository_name" {
  type        = string
  description = "ECR repository name for the API image."
  default     = "troubleshooter-api"
}

variable "ecr_max_image_count" {
  type        = number
  description = "Max number of images to retain in the ECR repository."
  default     = 30
}

variable "ecr_image_tag_mutability" {
  type        = string
  description = "ECR image tag mutability (MUTABLE or IMMUTABLE)."
  default     = "MUTABLE"
}

variable "ecr_force_delete" {
  type        = bool
  description = "Force delete ECR repository (deletes images)."
  default     = false
}

variable "ecs_container_image" {
  type        = string
  description = "Container image URI for the API service."
  default     = "placeholder"
}

variable "ecs_cpu" {
  type        = number
  description = "ECS task CPU units."
  default     = 512
}

variable "ecs_memory" {
  type        = number
  description = "ECS task memory (MiB)."
  default     = 1024
}

variable "ecs_port" {
  type        = number
  description = "Container port for the API service."
  default     = 8080
}

variable "ecs_desired_count" {
  type        = number
  description = "Desired ECS task count."
  default     = 2
}

variable "ecs_min_capacity" {
  type        = number
  description = "Minimum ECS task count for autoscaling."
  default     = 1
}

variable "ecs_max_capacity" {
  type        = number
  description = "Maximum ECS task count for autoscaling."
  default     = 4
}

variable "ecs_cpu_target_value" {
  type        = number
  description = "Target CPU utilization percentage for ECS autoscaling."
  default     = 50
}

variable "ecs_alb_listener_port" {
  type        = number
  description = "ALB listener port for the ECS service."
  default     = 80
}

variable "pgvector_enabled" {
  type        = bool
  description = "Enable pgvector sidecar container for ephemeral semantic caching."
  default     = false
}

variable "pgvector_image" {
  type        = string
  description = "Container image URI for the pgvector sidecar."
  default     = "pgvector/pgvector:pg16"
}

variable "pgvector_port" {
  type        = number
  description = "Container port for the pgvector sidecar."
  default     = 5432
}

variable "pgvector_env_vars" {
  type        = map(string)
  description = "Environment variables for the pgvector sidecar."
  default = {
    POSTGRES_DB       = "troubleshooter_cache"
    POSTGRES_USER     = "postgres"
    POSTGRES_PASSWORD = "postgres"
  }
}

variable "pgvector_env_vars_secret_arns" {
  type        = list(string)
  description = "Secret ARNs to inject as environment variables into the pgvector sidecar."
  default     = []
}

variable "ecs_task_role_name" {
  type        = string
  description = "IAM task role name for ECS tasks."
  default     = "troubleshooter-task"
}

variable "ecs_execution_role_name" {
  type        = string
  description = "IAM execution role name for ECS tasks."
  default     = "troubleshooter-exec"
}

variable "openapi_spec_path" {
  type        = string
  description = "Path to the OpenAPI spec file."
  default     = "../../docs/openapi.json"
}

variable "api_stage_name" {
  type        = string
  description = "API Gateway stage name."
  default     = "dev"
}

variable "api_usage_plans" {
  type = list(object({
    name        = string
    rate_limit  = number
    burst_limit = number
  }))
  description = "Usage plans for API Gateway."
  default = [
    {
      name        = "default"
      rate_limit  = 100
      burst_limit = 200
    }
  ]
}

variable "api_custom_domain_name" {
  type        = string
  description = "Custom domain name for API Gateway."
  default     = null
}

variable "api_custom_domain_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the API Gateway custom domain."
  default     = null
}

variable "api_custom_domain_hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for DNS validation."
  default     = null
}

variable "api_custom_domain_base_path" {
  type        = string
  description = "Base path mapping for the API Gateway custom domain."
  default     = ""
}

variable "api_endpoint_type" {
  type        = string
  description = "API Gateway custom domain endpoint type (REGIONAL or EDGE)."
  default     = "REGIONAL"
}

variable "api_security_policy" {
  type        = string
  description = "TLS version for the API Gateway custom domain."
  default     = "TLS_1_2"
}

variable "api_cors_allow_origin" {
  type        = string
  description = "Allowed CORS origin for the API (e.g., https://ts-demo.marcus-aca.com)."
  default     = ""
}

variable "session_table_name" {
  type        = string
  description = "DynamoDB table name for sessions."
  default     = "troubleshooter-sessions"
}

variable "inputs_table_name" {
  type        = string
  description = "DynamoDB table name for raw inputs."
  default     = "troubleshooter-inputs"
}

variable "conversation_events_table_name" {
  type        = string
  description = "DynamoDB table name for conversation events."
  default     = "troubleshooter-conversation-events"
}

variable "conversation_state_table_name" {
  type        = string
  description = "DynamoDB table name for conversation state."
  default     = "troubleshooter-conversation-state"
}

variable "conversation_ttl_seconds" {
  type        = number
  description = "TTL in seconds for conversation events/state."
  default     = 604800
}

variable "budget_table_name" {
  type        = string
  description = "DynamoDB table name for budgets."
  default     = "troubleshooter-budgets"
}

variable "budget_enabled" {
  type        = bool
  description = "Enable budget enforcement in the API service."
  default     = true
}

variable "budget_token_limit" {
  type        = number
  description = "Token budget per 15-minute window."
  default     = 20000
}

variable "budget_window_minutes" {
  type        = number
  description = "Window size in minutes for token budget enforcement."
  default     = 15
}

variable "uploads_bucket_name" {
  type        = string
  description = "Uploads bucket name."
  default     = "troubleshooter-uploads"
}

variable "artifacts_bucket_name" {
  type        = string
  description = "Artifacts bucket name."
  default     = "troubleshooter-artifacts"
}

variable "outputs_bucket_name" {
  type        = string
  description = "S3 bucket for generated outputs (reports, eval)."
  default     = "troubleshooter-outputs"
}

variable "frontend_bucket_name" {
  type        = string
  description = "S3 bucket for static frontend assets."
  default     = "troubleshooter-frontend"
}

variable "frontend_cloudfront_enabled" {
  type        = bool
  description = "Enable CloudFront distribution for the frontend."
  default     = true
}

variable "frontend_cloudfront_price_class" {
  type        = string
  description = "CloudFront price class for the frontend distribution."
  default     = "PriceClass_100"
}

variable "frontend_cloudfront_default_root_object" {
  type        = string
  description = "Default root object for the frontend distribution."
  default     = "index.html"
}

variable "frontend_cloudfront_custom_domain_name" {
  type        = string
  description = "Optional custom domain name for the frontend CloudFront distribution."
  default     = null
  validation {
    condition     = var.frontend_cloudfront_custom_domain_name == null || var.frontend_cloudfront_custom_domain_name != ""
    error_message = "frontend_cloudfront_custom_domain_name must be null or a non-empty string."
  }
}

variable "frontend_cloudfront_certificate_arn" {
  type        = string
  description = "ACM certificate ARN (us-east-1) for the frontend CloudFront distribution."
  default     = null
  validation {
    condition     = var.frontend_cloudfront_certificate_arn == null || var.frontend_cloudfront_certificate_arn != ""
    error_message = "frontend_cloudfront_certificate_arn must be null or a non-empty string."
  }
}

variable "frontend_cloudfront_hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for the frontend custom domain."
  default     = null
}

variable "frontend_cloudfront_minimum_tls_version" {
  type        = string
  description = "Minimum TLS version for the frontend CloudFront distribution."
  default     = "TLSv1.2_2021"
}

variable "frontend_cloudfront_validate_custom_domain" {
  type        = bool
  description = "Require a custom domain to supply a certificate ARN."
  default     = true
}

variable "observability_log_retention_in_days" {
  type        = number
  description = "Retention period in days for observability log groups."
  default     = 14
}

variable "apigw_p95_latency_threshold_ms" {
  type        = number
  description = "Alarm threshold (ms) for API Gateway p95 latency."
  default     = 1000
}

variable "apigw_5xx_error_rate_threshold_percent" {
  type        = number
  description = "Alarm threshold (%) for API Gateway 5xx error rate."
  default     = 5
}

variable "alarm_actions" {
  type        = list(string)
  description = "Alarm action ARNs (SNS, PagerDuty, etc)."
  default     = []
}

variable "alarm_ok_actions" {
  type        = list(string)
  description = "OK action ARNs for alarms."
  default     = []
}

variable "custom_metrics_namespace" {
  type        = string
  description = "Namespace for custom application metrics."
  default     = "Troubleshooter/LLM"
}

variable "bedrock_model_arns" {
  type        = list(string)
  description = "Bedrock model ARNs allowed for ECS task invocation."
  default     = []
}

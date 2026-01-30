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

variable "budget_table_name" {
  type        = string
  description = "DynamoDB table name for budgets."
  default     = "troubleshooter-budgets"
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

variable "bedrock_model_arns" {
  type        = list(string)
  description = "Bedrock model ARNs allowed for ECS task invocation."
  default     = []
}

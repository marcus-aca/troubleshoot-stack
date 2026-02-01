variable "cluster_name" {
  type        = string
  description = "ECS cluster name."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID for the ECS service."
}

variable "subnet_ids_private" {
  type        = list(string)
  description = "Private subnet IDs for the service."
}

variable "subnet_ids_public" {
  type        = list(string)
  description = "Public subnet IDs for the load balancer if used."
}

variable "container_image" {
  type        = string
  description = "Container image URI."
}

variable "cpu" {
  type        = number
  description = "Task CPU units."
}

variable "memory" {
  type        = number
  description = "Task memory (MiB)."
}

variable "port" {
  type        = number
  description = "Container port."
}

variable "desired_count" {
  type        = number
  description = "Desired task count."
}

variable "min_capacity" {
  type        = number
  description = "Minimum task count for autoscaling."
  default     = 1
}

variable "max_capacity" {
  type        = number
  description = "Maximum task count for autoscaling."
  default     = 4
}

variable "cpu_target_value" {
  type        = number
  description = "Target CPU utilization percentage for autoscaling."
  default     = 50
}

variable "env_vars_secret_arns" {
  type        = list(string)
  description = "Secret ARNs to inject as environment variables."
  default     = []
}

variable "env_vars" {
  type        = map(string)
  description = "Plaintext environment variables to inject into the task."
  default     = {}
}

variable "task_role_arn" {
  type        = string
  description = "IAM task role ARN."
}

variable "execution_role_arn" {
  type        = string
  description = "IAM execution role ARN."
}

variable "alb_enabled" {
  type        = bool
  description = "Whether to provision an ALB."
  default     = true
}

variable "alb_listener_port" {
  type        = number
  description = "ALB listener port."
  default     = 80
}

variable "log_group_name" {
  type        = string
  description = "CloudWatch log group name for ECS task logs."
  default     = null
}

variable "log_retention_in_days" {
  type        = number
  description = "Retention period in days for the ECS log group."
  default     = 14
}

variable "pgvector_enabled" {
  type        = bool
  description = "Enable a pgvector sidecar container for ephemeral semantic caching."
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

variable "otel_enabled" {
  type        = bool
  description = "Enable OpenTelemetry collector sidecar and tracing."
  default     = false
}

variable "otel_collector_image" {
  type        = string
  description = "OTel collector container image."
  default     = "public.ecr.aws/aws-observability/aws-otel-collector:latest"
}

variable "otel_service_name" {
  type        = string
  description = "Service name for tracing."
  default     = "troubleshooter-api"
}

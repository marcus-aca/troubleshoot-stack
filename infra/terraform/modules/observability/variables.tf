variable "names" {
  type        = map(string)
  description = "Friendly names for observability resources."
  default     = {}
}

variable "log_groups" {
  type        = list(string)
  description = "Log group names to create or manage."
  default     = []
}

variable "manage_log_groups" {
  type        = bool
  description = "Whether to create/manage log groups."
  default     = true
}

variable "log_retention_in_days" {
  type        = number
  description = "Retention period in days for managed log groups."
  default     = 14
}

variable "api_gateway_name" {
  type        = string
  description = "API Gateway REST API name for metrics."
}

variable "api_gateway_stage" {
  type        = string
  description = "API Gateway stage name for metrics."
}

variable "alb_arn_suffix" {
  type        = string
  description = "ALB ARN suffix for metrics (app/...)."
  default     = null
}

variable "target_group_arn_suffix" {
  type        = string
  description = "Target group ARN suffix for metrics (targetgroup/...)."
  default     = null
}

variable "ecs_cluster_name" {
  type        = string
  description = "ECS cluster name for metrics."
}

variable "ecs_service_name" {
  type        = string
  description = "ECS service name for metrics."
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

variable "ok_actions" {
  type        = list(string)
  description = "OK action ARNs for alarms."
  default     = []
}

variable "custom_metrics_namespace" {
  type        = string
  description = "Namespace for custom application metrics."
  default     = "Troubleshooter"
}

variable "cache_hit_metric_name" {
  type        = string
  description = "Metric name for cache hit rate."
  default     = "CacheHitRate"
}

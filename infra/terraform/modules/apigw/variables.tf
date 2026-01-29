variable "openapi_spec_path" {
  type        = string
  description = "Path to the OpenAPI spec file."
}

variable "alb_dns_name" {
  type        = string
  description = "ALB DNS name for proxy integrations."
  default     = null
}

variable "alb_listener_port" {
  type        = number
  description = "ALB listener port for proxy integrations."
  default     = 80
}

variable "stage_name" {
  type        = string
  description = "API Gateway stage name."
}

variable "usage_plans" {
  type = list(object({
    name        = string
    rate_limit  = number
    burst_limit = number
  }))
  description = "Usage plans to configure on the API."
  default     = []
}

variable "log_retention_in_days" {
  type        = number
  description = "CloudWatch log retention in days for API Gateway access logs."
  default     = 14
}

variable "rest_api_name" {
  type        = string
  description = "Override name for the REST API."
  default     = null
}

variable "access_log_group_name" {
  type        = string
  description = "CloudWatch log group name for API Gateway access logs."
  default     = null
}

variable "manage_log_group" {
  type        = bool
  description = "Whether to create/manage the API Gateway access log group."
  default     = true
}

variable "custom_domain_name" {
  type        = string
  description = "Custom domain name for API Gateway (optional)."
  default     = null
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the custom domain (required if custom_domain_name is set)."
  default     = null
}

variable "hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for DNS validation (required if custom_domain_name is set)."
  default     = null
}

variable "base_path" {
  type        = string
  description = "Base path mapping for the custom domain."
  default     = ""
}

variable "endpoint_type" {
  type        = string
  description = "Endpoint type for the custom domain (REGIONAL or EDGE)."
  default     = "REGIONAL"
}

variable "security_policy" {
  type        = string
  description = "TLS version for the custom domain."
  default     = "TLS_1_2"
}

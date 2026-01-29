variable "function_name" {
  type        = string
  description = "Lambda function name."
}

variable "handler" {
  type        = string
  description = "Lambda handler."
}

variable "runtime" {
  type        = string
  description = "Lambda runtime."
}

variable "memory_mb" {
  type        = number
  description = "Lambda memory size in MB."
}

variable "timeout_s" {
  type        = number
  description = "Lambda timeout in seconds."
}

variable "env_vars" {
  type        = map(string)
  description = "Environment variables for the Lambda function."
  default     = {}
}

variable "role_arn" {
  type        = string
  description = "IAM role ARN for the Lambda function."
}

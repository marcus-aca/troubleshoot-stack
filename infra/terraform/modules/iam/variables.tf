variable "ecs_task_role_name" {
  type        = string
  description = "ECS task role name."
  default     = "troubleshooter-task"
}

variable "ecs_execution_role_name" {
  type        = string
  description = "ECS execution role name."
  default     = "troubleshooter-exec"
}

variable "task_policy_json" {
  type        = string
  description = "Optional inline policy JSON for the ECS task role."
  default     = null
}

variable "s3_bucket_arns" {
  type        = list(string)
  description = "S3 bucket ARNs the task role can access."
  default     = []
}

variable "dynamodb_table_arns" {
  type        = list(string)
  description = "DynamoDB table ARNs the task role can access."
  default     = []
}

variable "bedrock_model_arns" {
  type        = list(string)
  description = "Bedrock model ARNs the task role can invoke."
  default     = []
}

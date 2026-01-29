variable "region" {
  type        = string
  description = "AWS region for the bootstrap resources."
  default     = "us-west-2"
}

variable "state_bucket_name" {
  type        = string
  description = "S3 bucket name for Terraform remote state."
  default     = "troubleshooter-terraform-state"
}

variable "lock_table_name" {
  type        = string
  description = "DynamoDB table name for Terraform state locking."
  default     = "troubleshooter-terraform-locks"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to bootstrap resources."
  default = {
    Project = "troubleshoot-stack"
    Stack   = "bootstrap"
  }
}

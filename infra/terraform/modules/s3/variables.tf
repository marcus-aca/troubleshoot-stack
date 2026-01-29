variable "bucket_name" {
  type        = string
  description = "S3 bucket name."
}

variable "lifecycle_rules" {
  type        = list(any)
  description = "Lifecycle rules for the bucket."
  default     = []
}

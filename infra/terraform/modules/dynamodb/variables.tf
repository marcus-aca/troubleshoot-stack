variable "table_name" {
  type        = string
  description = "DynamoDB table name."
}

variable "hash_key" {
  type        = string
  description = "Partition key attribute name."
}

variable "range_key" {
  type        = string
  description = "Sort key attribute name (optional)."
  default     = null
}

variable "billing_mode" {
  type        = string
  description = "Billing mode (PAY_PER_REQUEST or PROVISIONED)."
  default     = "PAY_PER_REQUEST"
}

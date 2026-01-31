variable "enabled" {
  type        = bool
  description = "Whether to create the CloudFront distribution."
  default     = true
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket name for the frontend assets."
}

variable "bucket_arn" {
  type        = string
  description = "S3 bucket ARN for the frontend assets."
}

variable "bucket_regional_domain_name" {
  type        = string
  description = "S3 bucket regional domain name for the origin."
}

variable "default_root_object" {
  type        = string
  description = "Default root object for CloudFront."
  default     = "index.html"
}

variable "price_class" {
  type        = string
  description = "CloudFront price class."
  default     = "PriceClass_100"
}

variable "custom_domain_name" {
  type        = string
  description = "Optional custom domain name for the distribution."
  default     = null
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN (must be in us-east-1) for the custom domain."
  default     = null
}

variable "hosted_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for the custom domain (optional)."
  default     = null
}

variable "minimum_protocol_version" {
  type        = string
  description = "Minimum TLS protocol version for the viewer certificate."
  default     = "TLSv1.2_2021"
}

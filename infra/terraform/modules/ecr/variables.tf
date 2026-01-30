variable "repository_name" {
  type        = string
  description = "ECR repository name."
}

variable "image_tag_mutability" {
  type        = string
  description = "ECR image tag mutability (MUTABLE or IMMUTABLE)."
  default     = "MUTABLE"
}

variable "max_image_count" {
  type        = number
  description = "Number of images to retain."
  default     = 30
}

variable "force_delete" {
  type        = bool
  description = "Whether to force delete the repository (deletes images)."
  default     = false
}

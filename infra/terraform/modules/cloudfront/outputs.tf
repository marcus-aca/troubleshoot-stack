output "distribution_id" {
  description = "CloudFront distribution ID."
  value       = var.enabled ? aws_cloudfront_distribution.this[0].id : null
}

output "distribution_arn" {
  description = "CloudFront distribution ARN."
  value       = var.enabled ? aws_cloudfront_distribution.this[0].arn : null
}

output "distribution_domain_name" {
  description = "CloudFront distribution domain name."
  value       = var.enabled ? aws_cloudfront_distribution.this[0].domain_name : null
}

output "oac_id" {
  description = "Origin Access Control ID."
  value       = aws_cloudfront_origin_access_control.this.id
}

output "rest_api_id" {
  description = "API Gateway REST API ID."
  value       = aws_api_gateway_rest_api.this.id
}

output "rest_api_name" {
  description = "API Gateway REST API name."
  value       = aws_api_gateway_rest_api.this.name
}

output "access_log_group_name" {
  description = "CloudWatch log group name for API Gateway access logs."
  value       = local.access_log_group_name
}

output "invoke_url" {
  description = "Invoke URL for the deployed stage."
  value       = aws_api_gateway_stage.this.invoke_url
}

output "api_keys" {
  description = "Map of API key names to key values."
  value       = { for name, key in aws_api_gateway_api_key.plan : name => key.value }
  sensitive   = true
}

output "custom_domain_name" {
  description = "Custom domain name configured for API Gateway."
  value       = var.custom_domain_name
}

output "custom_domain_target" {
  description = "Target domain name for the API Gateway custom domain."
  value = try(
    aws_api_gateway_domain_name.this[0].regional_domain_name,
    aws_api_gateway_domain_name.this[0].cloudfront_domain_name,
    null
  )
}

output "certificate_arn" {
  description = "ACM certificate ARN used for the custom domain."
  value       = try(aws_api_gateway_domain_name.this[0].certificate_arn, null)
}

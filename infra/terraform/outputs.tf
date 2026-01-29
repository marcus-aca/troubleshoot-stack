output "apigw_invoke_url" {
  description = "API Gateway invoke URL."
  value       = module.apigw.invoke_url
}

output "apigw_api_keys" {
  description = "API Gateway API keys."
  value       = module.apigw.api_keys
  sensitive   = true
}

output "apigw_custom_domain_name" {
  description = "API Gateway custom domain name."
  value       = module.apigw.custom_domain_name
}

output "apigw_custom_domain_target" {
  description = "API Gateway custom domain target."
  value       = module.apigw.custom_domain_target
}

output "apigw_custom_domain_certificate_arn" {
  description = "ACM certificate ARN used for the API Gateway custom domain."
  value       = module.apigw.certificate_arn
}

output "ecs_alb_dns_name" {
  description = "ECS ALB DNS name."
  value       = module.ecs_service.alb_dns_name
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN."
  value       = module.iam.ecs_task_role_arn
}

output "ecs_execution_role_arn" {
  description = "ECS execution role ARN."
  value       = module.iam.ecs_execution_role_arn
}

output "outputs_bucket_name" {
  description = "S3 bucket for generated outputs."
  value       = module.outputs_bucket.bucket_name
}

output "frontend_bucket_name" {
  description = "S3 bucket for frontend assets."
  value       = module.frontend_bucket.bucket_name
}

output "sessions_table_name" {
  description = "DynamoDB sessions table name."
  value       = module.sessions_table.name
}

output "inputs_table_name" {
  description = "DynamoDB inputs table name."
  value       = module.inputs_table.name
}

output "observability_dashboard_url" {
  description = "CloudWatch dashboard URL for observability."
  value       = module.observability.dashboard_url
}

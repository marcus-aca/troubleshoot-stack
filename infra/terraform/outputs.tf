output "apigw_invoke_url" {
  description = "API Gateway invoke URL."
  value       = module.apigw.invoke_url
}

output "aws_region" {
  description = "AWS region for the stack."
  value       = var.region
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

output "api_cors_allow_origin" {
  description = "Allowed CORS origin for the API Gateway."
  value       = var.api_cors_allow_origin
}

output "api_custom_domain_base_path" {
  description = "Base path for the API Gateway custom domain."
  value       = var.api_custom_domain_base_path
}

output "ecs_alb_dns_name" {
  description = "ECS ALB DNS name."
  value       = module.ecs_service.alb_dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = var.ecs_cluster_name
}

output "ecs_service_name" {
  description = "ECS service name."
  value       = "${var.ecs_cluster_name}-service"
}

output "ecs_task_role_arn" {
  description = "ECS task role ARN."
  value       = module.iam.ecs_task_role_arn
}

output "ecs_execution_role_arn" {
  description = "ECS execution role ARN."
  value       = module.iam.ecs_execution_role_arn
}

output "ecr_repository_url" {
  description = "ECR repository URL for the API image."
  value       = module.ecr.repository_url
}

output "outputs_bucket_name" {
  description = "S3 bucket for generated outputs."
  value       = module.outputs_bucket.bucket_name
}

output "frontend_bucket_name" {
  description = "S3 bucket for frontend assets."
  value       = module.frontend_bucket.bucket_name
}

output "frontend_cloudfront_domain_name" {
  description = "CloudFront domain name for the frontend."
  value       = module.frontend_cloudfront.distribution_domain_name
}

output "frontend_cloudfront_distribution_id" {
  description = "CloudFront distribution ID for the frontend."
  value       = module.frontend_cloudfront.distribution_id
}

output "sessions_table_name" {
  description = "DynamoDB sessions table name."
  value       = module.sessions_table.name
}

output "inputs_table_name" {
  description = "DynamoDB inputs table name."
  value       = module.inputs_table.name
}

output "conversation_events_table_name" {
  description = "DynamoDB conversation events table name."
  value       = module.conversation_events_table.name
}

output "conversation_state_table_name" {
  description = "DynamoDB conversation state table name."
  value       = module.conversation_state_table.name
}

output "observability_dashboard_url" {
  description = "CloudWatch dashboard URL for observability."
  value       = module.observability.dashboard_url
}

output "xray_service_map_url" {
  description = "AWS X-Ray service map URL."
  value       = "https://${var.region}.console.aws.amazon.com/xray/home?region=${var.region}#/service-map"
}

output "cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}

output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.this.name
}

output "alb_dns_name" {
  description = "ALB DNS name when ALB is enabled."
  value       = var.alb_enabled ? aws_lb.this[0].dns_name : null
}

output "alb_arn_suffix" {
  description = "ALB ARN suffix for CloudWatch metrics."
  value       = var.alb_enabled ? aws_lb.this[0].arn_suffix : null
}

output "target_group_arn_suffix" {
  description = "Target group ARN suffix for CloudWatch metrics."
  value       = var.alb_enabled ? aws_lb_target_group.this[0].arn_suffix : null
}

output "nlb_dns_name" {
  description = "NLB DNS name when NLB is enabled."
  value       = null
}

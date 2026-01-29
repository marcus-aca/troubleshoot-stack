output "ecs_task_role_arn" {
  description = "ECS task role ARN."
  value       = aws_iam_role.ecs_task.arn
}

output "ecs_execution_role_arn" {
  description = "ECS execution role ARN."
  value       = aws_iam_role.ecs_execution.arn
}

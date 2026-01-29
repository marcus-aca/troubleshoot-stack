output "table_arn" {
  description = "DynamoDB table ARN."
  value       = aws_dynamodb_table.this.arn
}

output "name" {
  description = "DynamoDB table name."
  value       = var.table_name
}

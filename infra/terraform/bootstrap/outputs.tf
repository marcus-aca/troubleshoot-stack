output "state_bucket_name" {
  description = "Name of the Terraform state bucket."
  value       = aws_s3_bucket.state.bucket
}

output "lock_table_name" {
  description = "Name of the Terraform lock table."
  value       = aws_dynamodb_table.locks.name
}

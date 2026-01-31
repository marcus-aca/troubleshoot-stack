output "bucket_arn" {
  description = "S3 bucket ARN."
  value       = aws_s3_bucket.this.arn
}

output "bucket_name" {
  description = "S3 bucket name."
  value       = aws_s3_bucket.this.bucket
}

output "bucket_regional_domain_name" {
  description = "Regional domain name for the S3 bucket."
  value       = aws_s3_bucket.this.bucket_regional_domain_name
}

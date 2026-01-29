output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}

output "subnet_ids_public" {
  description = "Public subnet IDs."
  value       = [for subnet in aws_subnet.public : subnet.id]
}

output "subnet_ids_private" {
  description = "Private subnet IDs."
  value       = [for subnet in aws_subnet.private : subnet.id]
}

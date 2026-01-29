# Terraform bootstrap (remote state)

Creates the S3 bucket and DynamoDB table used for Terraform remote state.

## Usage

```bash
terraform init
terraform plan -out tfplan
terraform apply tfplan
```

## Outputs
- state_bucket_name
- lock_table_name

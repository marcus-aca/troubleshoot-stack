# iam module

Creates IAM roles and policies used by services.

## Inputs
- `ecs_task_role_name`
- `ecs_execution_role_name`
- `task_policy_json` (optional)
- `s3_bucket_arns`
- `dynamodb_table_arns`
- `bedrock_model_arns`

## Outputs
- `ecs_task_role_arn`
- `ecs_execution_role_arn`

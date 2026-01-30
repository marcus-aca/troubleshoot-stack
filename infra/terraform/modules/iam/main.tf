locals {
  ecs_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  dynamodb_arns = compact([for arn in var.dynamodb_table_arns : trimspace(tostring(arn))])
  dynamodb_policy_statement = length(local.dynamodb_arns) == 0 ? [] : [
    {
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ]
      Resource = local.dynamodb_arns
    }
  ]

  s3_bucket_arns_clean = compact([for arn in var.s3_bucket_arns : trimspace(tostring(arn))])
  s3_resources = concat(
    local.s3_bucket_arns_clean,
    [for arn in local.s3_bucket_arns_clean : "${arn}/*"]
  )

  s3_policy_statement = length(local.s3_bucket_arns_clean) == 0 ? [] : [
    {
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]
      Resource = local.s3_resources
    }
  ]

  bedrock_arns = compact([for arn in var.bedrock_model_arns : trimspace(tostring(arn))])
  bedrock_policy_statement = length(local.bedrock_arns) == 0 ? [] : [
    {
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ]
      Resource = local.bedrock_arns
    }
  ]

  cloudwatch_metrics_statement = [
    {
      Effect = "Allow"
      Action = [
        "cloudwatch:PutMetricData"
      ]
      Resource = "*"
    }
  ]

  task_policy_statements = concat(
    local.dynamodb_policy_statement,
    local.s3_policy_statement,
    local.bedrock_policy_statement,
    local.cloudwatch_metrics_statement
  )

  task_policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = local.task_policy_statements
  })
}

resource "aws_iam_role" "ecs_task" {
  name               = var.ecs_task_role_name
  assume_role_policy = local.ecs_assume_role_policy
}

resource "aws_iam_role_policy" "ecs_task_inline" {
  name   = "${var.ecs_task_role_name}-inline"
  role   = aws_iam_role.ecs_task.id
  policy = var.task_policy_json == null ? local.task_policy_document : var.task_policy_json
}

resource "aws_iam_role" "ecs_execution" {
  name               = var.ecs_execution_role_name
  assume_role_policy = local.ecs_assume_role_policy
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

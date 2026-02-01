locals {
  spec_body     = templatefile(var.openapi_spec_path, {
    alb_dns_name      = var.alb_dns_name
    alb_listener_port = var.alb_listener_port
    cors_allow_origin = var.cors_allow_origin
  })
  spec_hash     = sha256(local.spec_body)
  stage_log_key = replace(var.stage_name, "/[^a-zA-Z0-9-_]/", "-")
  rest_api_name = coalesce(var.rest_api_name, "troubleshooter-${local.stage_log_key}")
  domain_enabled = var.custom_domain_name != null
  create_cert    = local.domain_enabled && var.certificate_arn == null && !local.is_edge
  is_regional    = upper(var.endpoint_type) == "REGIONAL"
  is_edge        = upper(var.endpoint_type) == "EDGE"
  access_log_group_name = coalesce(var.access_log_group_name, "/aws/apigateway/${local.rest_api_name}-${local.stage_log_key}")
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
resource "aws_cloudwatch_log_group" "access_logs" {
  count             = var.manage_log_group ? 1 : 0
  name              = local.access_log_group_name
  retention_in_days = var.log_retention_in_days
}

resource "aws_iam_role" "apigw_logging" {
  name = "apigw-logging-${local.stage_log_key}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "apigw_logging" {
  name = "apigw-logging-${local.stage_log_key}"
  role = aws_iam_role.apigw_logging.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents",
          "logs:GetLogEvents",
          "logs:FilterLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_api_gateway_account" "this" {
  cloudwatch_role_arn = aws_iam_role.apigw_logging.arn
}

resource "aws_api_gateway_rest_api" "this" {
  name = local.rest_api_name
  body = local.spec_body
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = local.spec_hash
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name
  xray_tracing_enabled = var.xray_tracing_enabled

  access_log_settings {
    destination_arn = format(
      "arn:aws:logs:%s:%s:log-group:%s",
      data.aws_region.current.name,
      data.aws_caller_identity.current.account_id,
      local.access_log_group_name
    )
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      userAgent      = "$context.identity.userAgent"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      responseLength = "$context.responseLength"
    })
  }

  depends_on = [aws_api_gateway_account.this]
}

resource "aws_api_gateway_usage_plan" "this" {
  for_each = { for plan in var.usage_plans : plan.name => plan }

  name = each.value.name

  api_stages {
    api_id = aws_api_gateway_rest_api.this.id
    stage  = aws_api_gateway_stage.this.stage_name
  }

  throttle_settings {
    rate_limit  = each.value.rate_limit
    burst_limit = each.value.burst_limit
  }
}

resource "aws_api_gateway_api_key" "plan" {
  for_each = aws_api_gateway_usage_plan.this

  name = "${each.key}-key"
}

resource "aws_api_gateway_usage_plan_key" "plan" {
  for_each = aws_api_gateway_usage_plan.this

  key_id        = aws_api_gateway_api_key.plan[each.key].id
  key_type      = "API_KEY"
  usage_plan_id = each.value.id
}

resource "aws_api_gateway_domain_name" "this" {
  count = local.domain_enabled ? 1 : 0

  domain_name     = var.custom_domain_name
  security_policy = var.security_policy

  endpoint_configuration {
    types = [var.endpoint_type]
  }

  regional_certificate_arn = local.is_regional ? (
    local.create_cert ? aws_acm_certificate_validation.this[0].certificate_arn : var.certificate_arn
  ) : null

  certificate_arn = local.is_edge ? var.certificate_arn : null

  lifecycle {
    precondition {
      condition     = !local.is_edge || var.certificate_arn != null
      error_message = "EDGE domains require an ACM certificate ARN (in us-east-1)."
    }
    precondition {
      condition     = !local.is_edge || !local.create_cert
      error_message = "EDGE domains do not support certificate requests in this module."
    }
  }
}

resource "aws_api_gateway_base_path_mapping" "this" {
  count = local.domain_enabled ? 1 : 0

  api_id      = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  domain_name = aws_api_gateway_domain_name.this[0].domain_name
  base_path   = var.base_path != "" ? var.base_path : null
}

resource "aws_route53_record" "custom_domain" {
  count   = local.domain_enabled && var.hosted_zone_id != null ? 1 : 0
  zone_id = var.hosted_zone_id
  name    = var.custom_domain_name
  type    = "A"

  alias {
    name                   = local.is_edge ? aws_api_gateway_domain_name.this[0].cloudfront_domain_name : aws_api_gateway_domain_name.this[0].regional_domain_name
    zone_id                = local.is_edge ? aws_api_gateway_domain_name.this[0].cloudfront_zone_id : aws_api_gateway_domain_name.this[0].regional_zone_id
    evaluate_target_health = false
  }
}

resource "aws_acm_certificate" "this" {
  count = local.create_cert ? 1 : 0

  domain_name       = var.custom_domain_name
  validation_method = "DNS"

  lifecycle {
    precondition {
      condition     = var.hosted_zone_id != null
      error_message = "hosted_zone_id must be set to request and DNS-validate a certificate."
    }
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.create_cert ? {
    for dvo in aws_acm_certificate.this[0].domain_validation_options :
    dvo.domain_name => dvo
  } : {}

  zone_id = var.hosted_zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  ttl     = 60
  records = [each.value.resource_record_value]
}

resource "aws_acm_certificate_validation" "this" {
  count = local.create_cert ? 1 : 0

  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

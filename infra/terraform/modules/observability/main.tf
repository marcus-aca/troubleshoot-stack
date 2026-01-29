data "aws_region" "current" {}
data "aws_cloudwatch_log_groups" "existing" {
  log_group_name_prefix = "/"
}

locals {
  dashboard_name = coalesce(lookup(var.names, "dashboard", null), "troubleshooter-${var.api_gateway_stage}")
  stage_log_key  = replace(var.api_gateway_stage, "/[^a-zA-Z0-9-_]/", "-")
  base_widgets = jsonencode([
    {
      type   = "metric"
      x      = 0
      y      = 0
      width  = 12
      height = 6
      properties = {
        title   = "API Gateway Latency (p50/p95/p99)"
        view    = "timeSeries"
        stacked = false
        region  = data.aws_region.current.name
        period  = 60
        metrics = [
          ["AWS/ApiGateway", "Latency", "ApiName", var.api_gateway_name, "Stage", var.api_gateway_stage, { stat = "p50" }],
          [".", "Latency", ".", ".", ".", ".", { stat = "p95" }],
          [".", "Latency", ".", ".", ".", ".", { stat = "p99" }]
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 0
      width  = 12
      height = 6
      properties = {
        title   = "API Gateway Requests & Errors"
        view    = "timeSeries"
        stacked = false
        region  = data.aws_region.current.name
        period  = 60
        metrics = [
          ["AWS/ApiGateway", "Count", "ApiName", var.api_gateway_name, "Stage", var.api_gateway_stage, { stat = "Sum" }],
          [".", "4XXError", ".", ".", ".", ".", { stat = "Sum" }],
          [".", "5XXError", ".", ".", ".", ".", { stat = "Sum" }]
        ]
      }
    },
    {
      type   = "metric"
      x      = 0
      y      = 6
      width  = 12
      height = 6
      properties = {
        title   = "ECS Tasks Desired vs Running"
        view    = "timeSeries"
        stacked = false
        region  = data.aws_region.current.name
        period  = 60
        metrics = [
          ["AWS/ECS", "DesiredTaskCount", "ClusterName", var.ecs_cluster_name, "ServiceName", var.ecs_service_name, { stat = "Average" }],
          [".", "RunningTaskCount", ".", ".", ".", ".", { stat = "Average" }]
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 6
      width  = 12
      height = 6
      properties = {
        title   = "Cache Hit Rate"
        view    = "timeSeries"
        stacked = false
        region  = data.aws_region.current.name
        period  = 60
        metrics = [
          [var.custom_metrics_namespace, var.cache_hit_metric_name, { stat = "Average" }]
        ]
      }
    }
  ])
  alb_widgets = jsonencode([
    {
      type   = "metric"
      x      = 0
      y      = 12
      width  = 12
      height = 6
      properties = {
        title   = "ALB Target Response Time (p50/p95/p99)"
        view    = "timeSeries"
        stacked = false
        region  = data.aws_region.current.name
        period  = 60
        metrics = [
          ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.target_group_arn_suffix, { stat = "p50" }],
          [".", "TargetResponseTime", ".", ".", ".", ".", { stat = "p95" }],
          [".", "TargetResponseTime", ".", ".", ".", ".", { stat = "p99" }]
        ]
      }
    },
    {
      type   = "metric"
      x      = 12
      y      = 12
      width  = 12
      height = 6
      properties = {
        title   = "ALB 5XX Errors"
        view    = "timeSeries"
        stacked = false
        region  = data.aws_region.current.name
        period  = 60
        metrics = [
          ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.target_group_arn_suffix, { stat = "Sum" }],
          ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", var.alb_arn_suffix, { stat = "Sum" }]
        ]
      }
    }
  ])
  widgets_json = var.alb_arn_suffix != null && var.target_group_arn_suffix != null ? format(
    "%s,%s",
    substr(local.base_widgets, 1, length(local.base_widgets) - 2),
    substr(local.alb_widgets, 1, length(local.alb_widgets) - 2)
  ) : substr(local.base_widgets, 1, length(local.base_widgets) - 2)
  dashboard_body = format("{\"widgets\":[%s]}", local.widgets_json)
}

resource "aws_cloudwatch_log_group" "managed" {
  for_each          = var.manage_log_groups ? setsubtract(toset(var.log_groups), toset(data.aws_cloudwatch_log_groups.existing.log_group_names)) : toset([])
  name              = each.value
  retention_in_days = var.log_retention_in_days
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = local.dashboard_name
  dashboard_body = local.dashboard_body
}

resource "aws_cloudwatch_metric_alarm" "apigw_latency_p95" {
  alarm_name          = "${local.stage_log_key}-apigw-p95-latency"
  alarm_description   = "API Gateway p95 latency above ${var.apigw_p95_latency_threshold_ms}ms."
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.apigw_p95_latency_threshold_ms
  evaluation_periods  = 5
  datapoints_to_alarm = 5
  period              = 60
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions

  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  extended_statistic  = "p95"
  dimensions = {
    ApiName = var.api_gateway_name
    Stage   = var.api_gateway_stage
  }
}

resource "aws_cloudwatch_metric_alarm" "apigw_5xx_error_rate" {
  alarm_name          = "${local.stage_log_key}-apigw-5xx-rate"
  alarm_description   = "API Gateway 5xx error rate above ${var.apigw_5xx_error_rate_threshold_percent}%."
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.apigw_5xx_error_rate_threshold_percent
  evaluation_periods  = 5
  datapoints_to_alarm = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions

  metric_query {
    id          = "m1"
    return_data = false
    metric {
      namespace   = "AWS/ApiGateway"
      metric_name = "5XXError"
      period      = 60
      stat        = "Sum"
      dimensions = {
        ApiName = var.api_gateway_name
        Stage   = var.api_gateway_stage
      }
    }
  }

  metric_query {
    id          = "m2"
    return_data = false
    metric {
      namespace   = "AWS/ApiGateway"
      metric_name = "Count"
      period      = 60
      stat        = "Sum"
      dimensions = {
        ApiName = var.api_gateway_name
        Stage   = var.api_gateway_stage
      }
    }
  }

  metric_query {
    id          = "e1"
    expression  = "IF(m2>0, 100*m1/m2, 0)"
    label       = "5XXErrorRate"
    return_data = true
  }
}

resource "aws_cloudwatch_metric_alarm" "ecs_task_mismatch" {
  alarm_name          = "${local.stage_log_key}-ecs-task-mismatch"
  alarm_description   = "ECS running task count is below desired."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.ok_actions

  metric_query {
    id          = "m1"
    return_data = false
    metric {
      namespace   = "AWS/ECS"
      metric_name = "DesiredTaskCount"
      period      = 60
      stat        = "Average"
      dimensions = {
        ClusterName = var.ecs_cluster_name
        ServiceName = var.ecs_service_name
      }
    }
  }

  metric_query {
    id          = "m2"
    return_data = false
    metric {
      namespace   = "AWS/ECS"
      metric_name = "RunningTaskCount"
      period      = 60
      stat        = "Average"
      dimensions = {
        ClusterName = var.ecs_cluster_name
        ServiceName = var.ecs_service_name
      }
    }
  }

  metric_query {
    id          = "e1"
    expression  = "m1 - m2"
    label       = "DesiredMinusRunning"
    return_data = true
  }
}

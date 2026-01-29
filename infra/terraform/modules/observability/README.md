# observability module

Creates CloudWatch log groups, dashboards, and alarms.

## Inputs
- `names`
- `api_gateway_name`
- `api_gateway_stage`
- `alb_arn_suffix`
- `target_group_arn_suffix`
- `ecs_cluster_name`
- `ecs_service_name`
- `apigw_p95_latency_threshold_ms`
- `apigw_5xx_error_rate_threshold_percent`
- `alarm_actions`
- `ok_actions`
- `custom_metrics_namespace`
- `cache_hit_metric_name`

## Outputs
- `dashboard_url`
- `dashboard_name`

## Notes
This module provisions dashboards and alarms and can manage log groups.

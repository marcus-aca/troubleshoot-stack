# ecs_service module

Creates an ECS Fargate service with optional load balancer.

## Inputs
- `cluster_name`
- `vpc_id`
- `subnet_ids_private`
- `subnet_ids_public`
- `container_image`
- `cpu`
- `memory`
- `port`
- `desired_count`
- `env_vars_secret_arns`
- `task_role_arn`
- `execution_role_arn`
- `alb_enabled`
- `alb_listener_port`

## Outputs
- `cluster_arn`
- `service_name`
- `alb_dns_name`
- `nlb_dns_name`

## Notes
This module is currently a scaffold; wire resources in later steps.

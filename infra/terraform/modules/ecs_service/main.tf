locals {
  log_group_name = coalesce(var.log_group_name, "/ecs/${var.cluster_name}")
}

data "aws_region" "current" {}
data "aws_cloudwatch_log_groups" "existing" {
  log_group_name_prefix = local.log_group_name
}

locals {
  log_group_exists = contains(data.aws_cloudwatch_log_groups.existing.log_group_names, local.log_group_name)
}

resource "aws_cloudwatch_log_group" "service" {
  count             = local.log_group_exists ? 0 : 1
  name              = local.log_group_name
  retention_in_days = var.log_retention_in_days
}

resource "aws_ecs_cluster" "this" {
  name = var.cluster_name
}

resource "aws_security_group" "service" {
  name        = "${var.cluster_name}-service"
  description = "ECS service security group"
  vpc_id      = var.vpc_id
}

resource "aws_security_group" "alb" {
  count       = var.alb_enabled ? 1 : 0
  name        = "${var.cluster_name}-alb"
  description = "ALB security group"
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "alb_ingress" {
  count             = var.alb_enabled ? 1 : 0
  type              = "ingress"
  from_port         = var.alb_listener_port
  to_port           = var.alb_listener_port
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb[0].id
}

resource "aws_security_group_rule" "alb_egress" {
  count             = var.alb_enabled ? 1 : 0
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.alb[0].id
}

resource "aws_security_group_rule" "service_ingress" {
  count                    = var.alb_enabled ? 1 : 0
  type                     = "ingress"
  from_port                = var.port
  to_port                  = var.port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.service.id
  source_security_group_id = aws_security_group.alb[0].id
}

resource "aws_security_group_rule" "service_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.service.id
}

resource "aws_lb" "this" {
  count              = var.alb_enabled ? 1 : 0
  name               = "${var.cluster_name}-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[0].id]
  subnets            = var.subnet_ids_public
}

resource "aws_lb_target_group" "this" {
  count       = var.alb_enabled ? 1 : 0
  name        = "${var.cluster_name}-tg"
  port        = var.port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
}

resource "aws_lb_listener" "http" {
  count             = var.alb_enabled ? 1 : 0
  load_balancer_arn = aws_lb.this[0].arn
  port              = var.alb_listener_port
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this[0].arn
  }
}

resource "aws_ecs_task_definition" "this" {
  family                   = "${var.cluster_name}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  task_role_arn            = var.task_role_arn
  execution_role_arn       = var.execution_role_arn

  container_definitions = jsonencode([
    {
      name  = "api"
      image = var.container_image
      portMappings = [
        {
          containerPort = var.port
          protocol      = "tcp"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = local.log_group_name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "api"
        }
      }
      secrets = [
        for arn in var.env_vars_secret_arns : {
          name      = basename(arn)
          valueFrom = arn
        }
      ]
    }
  ])
}

resource "aws_ecs_service" "this" {
  name            = "${var.cluster_name}-service"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.subnet_ids_private
    security_groups = [aws_security_group.service.id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = var.alb_enabled ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.this[0].arn
      container_name   = "api"
      container_port   = var.port
    }
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_appautoscaling_target" "ecs" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "ecs_cpu" {
  name               = "${var.cluster_name}-cpu-target"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = var.cpu_target_value

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

locals {
  stage_log_key          = replace(var.api_stage_name, "/[^a-zA-Z0-9-_]/", "-")
  apigw_name             = "troubleshooter-${local.stage_log_key}"
  apigw_access_log_group = "/aws/apigateway/${local.apigw_name}-${local.stage_log_key}"
  ecs_log_group_name     = "/ecs/${var.ecs_cluster_name}"
  ecs_service_name       = "${var.ecs_cluster_name}-service"
}

module "vpc" {
  source = "./modules/vpc"

  cidr                 = var.vpc_cidr
  az_count             = var.az_count
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

module "ecr" {
  source = "./modules/ecr"

  repository_name      = var.ecr_repository_name
  max_image_count      = var.ecr_max_image_count
  image_tag_mutability = var.ecr_image_tag_mutability
  force_delete         = var.ecr_force_delete
}

module "ecs_service" {
  source = "./modules/ecs_service"

  cluster_name         = var.ecs_cluster_name
  vpc_id               = module.vpc.vpc_id
  subnet_ids_private   = module.vpc.subnet_ids_private
  subnet_ids_public    = module.vpc.subnet_ids_public
  container_image      = var.ecs_container_image
  cpu                  = var.ecs_cpu
  memory               = var.ecs_memory
  port                 = var.ecs_port
  desired_count        = var.ecs_desired_count
  min_capacity         = var.ecs_min_capacity
  max_capacity         = var.ecs_max_capacity
  cpu_target_value     = var.ecs_cpu_target_value
  env_vars_secret_arns = []
  env_vars = merge(
    {
      USE_DYNAMODB      = "true"
      SESSION_TABLE     = var.session_table_name
      INPUTS_TABLE      = var.inputs_table_name
      INPUT_TTL_SECONDS = "86400"
      AWS_REGION        = var.region
    },
    var.ecs_env_vars
  )
  task_role_arn         = module.iam.ecs_task_role_arn
  execution_role_arn    = module.iam.ecs_execution_role_arn
  alb_enabled           = true
  alb_listener_port     = var.ecs_alb_listener_port
  log_group_name        = local.ecs_log_group_name
  log_retention_in_days = var.observability_log_retention_in_days
}

module "iam" {
  source = "./modules/iam"

  ecs_task_role_name      = var.ecs_task_role_name
  ecs_execution_role_name = var.ecs_execution_role_name
  dynamodb_table_arns = [
    module.sessions_table.table_arn,
    module.inputs_table.table_arn
  ]
  s3_bucket_arns = [
    module.outputs_bucket.bucket_arn,
    module.frontend_bucket.bucket_arn
  ]
  bedrock_model_arns = var.bedrock_model_arns
}

module "sessions_table" {
  source = "./modules/dynamodb"

  table_name   = var.session_table_name
  hash_key     = "conversation_id"
  range_key    = null
  billing_mode = "PAY_PER_REQUEST"
}

module "inputs_table" {
  source = "./modules/dynamodb"

  table_name   = var.inputs_table_name
  hash_key     = "input_id"
  range_key    = null
  billing_mode = "PAY_PER_REQUEST"
}

module "outputs_bucket" {
  source = "./modules/s3"

  bucket_name     = var.outputs_bucket_name
  lifecycle_rules = []
}

module "frontend_bucket" {
  source = "./modules/s3"

  bucket_name     = var.frontend_bucket_name
  lifecycle_rules = []
}

module "apigw" {
  source = "./modules/apigw"

  openapi_spec_path     = var.openapi_spec_path
  rest_api_name         = local.apigw_name
  access_log_group_name = local.apigw_access_log_group
  manage_log_group      = true
  alb_dns_name          = module.ecs_service.alb_dns_name
  alb_listener_port     = var.ecs_alb_listener_port
  stage_name            = var.api_stage_name
  usage_plans           = var.api_usage_plans
  log_retention_in_days = var.observability_log_retention_in_days

  custom_domain_name = var.api_custom_domain_name
  certificate_arn    = var.api_custom_domain_certificate_arn
  hosted_zone_id     = var.api_custom_domain_hosted_zone_id
  base_path          = var.api_custom_domain_base_path

}

module "observability" {
  source = "./modules/observability"

  names = {
    dashboard = "troubleshooter-${var.api_stage_name}"
  }

  api_gateway_name                       = local.apigw_name
  api_gateway_stage                      = var.api_stage_name
  alb_arn_suffix                         = module.ecs_service.alb_arn_suffix
  target_group_arn_suffix                = module.ecs_service.target_group_arn_suffix
  ecs_cluster_name                       = var.ecs_cluster_name
  ecs_service_name                       = local.ecs_service_name
  apigw_p95_latency_threshold_ms         = var.apigw_p95_latency_threshold_ms
  apigw_5xx_error_rate_threshold_percent = var.apigw_5xx_error_rate_threshold_percent
  alarm_actions                          = var.alarm_actions
  ok_actions                             = var.alarm_ok_actions
}

region = "us-west-2"

vpc_cidr             = "10.10.0.0/16"
az_count             = 2
public_subnet_cidrs  = ["10.10.0.0/24", "10.10.1.0/24"]
private_subnet_cidrs = ["10.10.10.0/24", "10.10.11.0/24"]

ecs_cluster_name        = "troubleshooter"
ecs_container_image     = "placeholder"
ecs_cpu                 = 512
ecs_memory              = 1024
ecs_port                = 8080
ecs_desired_count       = 1
ecs_alb_listener_port   = 80
ecs_task_role_name      = "troubleshooter-task"
ecs_execution_role_name = "troubleshooter-exec"

openapi_spec_path = "../../docs/openapi.json"
api_stage_name    = "live"
api_usage_plans = [
  {
    name        = "default"
    rate_limit  = 100
    burst_limit = 200
  }
]

# Optional custom domain configuration
api_custom_domain_name            = "troubleshooter.marcus-aca.com"
api_custom_domain_certificate_arn = null
api_custom_domain_hosted_zone_id  = "Z01139631W9XQ087YCOF9"
api_custom_domain_base_path       = ""

session_table_name = "troubleshooter-sessions"
inputs_table_name  = "troubleshooter-inputs"
budget_table_name  = "troubleshooter-budgets"

uploads_bucket_name   = "troubleshooter-uploads"
artifacts_bucket_name = "troubleshooter-artifacts"
outputs_bucket_name   = "troubleshooter-outputs"
frontend_bucket_name  = "troubleshooter-frontend"

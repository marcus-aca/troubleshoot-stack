region = "us-west-2"

vpc_cidr             = "10.10.0.0/16"
az_count             = 2
public_subnet_cidrs  = ["10.10.0.0/24", "10.10.1.0/24"]
private_subnet_cidrs = ["10.10.10.0/24", "10.10.11.0/24"]

ecs_cluster_name         = "troubleshooter"
ecs_container_image      = "744352336217.dkr.ecr.us-west-2.amazonaws.com/troubleshooter-api:latest"
ecr_repository_name      = "troubleshooter-api"
ecr_max_image_count      = 30
ecr_image_tag_mutability = "MUTABLE"
ecr_force_delete         = true
ecs_env_vars             = {}
bedrock_model_arns = [
  "arn:aws:bedrock:us-west-2::foundation-model/openai.gpt-oss-20b-1:0",
  "arn:aws:bedrock:us-west-2::foundation-model/amazon.titan-embed-text-v2:0"
]
bedrock_model_id        = "openai.gpt-oss-20b-1:0"
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
api_cors_allow_origin      = "https://ts-demo.marcus-aca.com"
apigw_xray_tracing_enabled = true

pgvector_enabled = true

otel_enabled      = true
otel_service_name = "troubleshooter-api"

# Optional custom domain configuration
api_custom_domain_name            = "troubleshooter.marcus-aca.com"
api_custom_domain_certificate_arn = "arn:aws:acm:us-east-1:744352336217:certificate/453324c5-6446-4f8f-b2b4-ed550ac5c19f"
api_custom_domain_hosted_zone_id  = "Z01139631W9XQ087YCOF9"
api_custom_domain_base_path       = "live"
api_endpoint_type                 = "EDGE"

session_table_name             = "troubleshooter-sessions"
inputs_table_name              = "troubleshooter-inputs"
conversation_events_table_name = "troubleshooter-conversation-events"
conversation_state_table_name  = "troubleshooter-conversation-state"
conversation_ttl_seconds       = 604800
budget_table_name              = "troubleshooter-budgets"
budget_enabled                 = true
budget_token_limit             = 3000
budget_window_minutes          = 15

uploads_bucket_name   = "troubleshooter-uploads"
artifacts_bucket_name = "troubleshooter-artifacts"
outputs_bucket_name   = "troubleshooter-outputs"
frontend_bucket_name  = "troubleshooter-frontend"

# Frontend CloudFront configuration
frontend_cloudfront_enabled            = true
frontend_cloudfront_custom_domain_name = "ts-demo.marcus-aca.com"
frontend_cloudfront_certificate_arn    = "arn:aws:acm:us-east-1:744352336217:certificate/453324c5-6446-4f8f-b2b4-ed550ac5c19f"
frontend_cloudfront_hosted_zone_id     = "Z01139631W9XQ087YCOF9"

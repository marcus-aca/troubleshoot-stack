# apigw module

Creates API Gateway REST API resources using an OpenAPI spec.

## Inputs
- `openapi_spec_path`
- `alb_dns_name`
- `alb_listener_port`
- `stage_name`
- `usage_plans`
- `log_retention_in_days`
- `custom_domain_name`
- `certificate_arn`
- `hosted_zone_id`
- `base_path`
- `endpoint_type`
- `security_policy`

## Outputs
- `rest_api_id`
- `invoke_url`
- `api_keys`

## Notes
If `custom_domain_name` is set and `certificate_arn` is null, the module requests an ACM certificate and performs DNS validation using `hosted_zone_id`.

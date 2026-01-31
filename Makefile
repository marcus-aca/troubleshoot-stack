AWS_PROFILE ?= pi
TF_DIR := infra/terraform
API_DIR := services/api
FRONTEND_DIR := frontend

ECR_REPO := $(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw ecr_repository_url 2>/dev/null)
AWS_REGION := $(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw aws_region 2>/dev/null)
FRONTEND_BUCKET := $(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw frontend_bucket_name 2>/dev/null)
CLOUDFRONT_DIST_ID := $(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw frontend_cloudfront_distribution_id 2>/dev/null)

.PHONY: push-api login-ecr build-api test-api-parser test-api tf-apply tf-destroy build-frontend deploy-frontend frontend-env

login-ecr:
	@if [ -z "$(ECR_REPO)" ]; then echo "ECR repo not found. Run terraform apply in $(TF_DIR)."; exit 1; fi
	@if [ -z "$(AWS_REGION)" ]; then echo "AWS region not found. Run terraform apply in $(TF_DIR)."; exit 1; fi
	AWS_PROFILE=$(AWS_PROFILE) aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(ECR_REPO)

build-api:
	cd $(API_DIR) && docker build -t troubleshooter-api:latest .

push-api:
	@$(MAKE) login-ecr
	@$(MAKE) build-api
	@if [ -z "$(ECR_REPO)" ]; then echo "ECR repo not found. Run terraform apply in $(TF_DIR)."; exit 1; fi
	docker tag troubleshooter-api:latest $(ECR_REPO):latest
	docker push $(ECR_REPO):latest
	@if [ -z "$(AWS_REGION)" ]; then echo "AWS region not found. Run terraform apply in $(TF_DIR)."; exit 1; fi
	@CLUSTER_NAME=$(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw ecs_cluster_name 2>/dev/null); \
	SERVICE_NAME=$(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw ecs_service_name 2>/dev/null); \
	if [ -z "$$CLUSTER_NAME" ] || [ -z "$$SERVICE_NAME" ]; then \
		echo "ECS cluster/service not found. Run terraform apply in $(TF_DIR)."; exit 1; \
	fi; \
	AWS_PROFILE=$(AWS_PROFILE) aws ecs update-service \
		--region $(AWS_REGION) \
		--cluster $$CLUSTER_NAME \
		--service $$SERVICE_NAME \
		--force-new-deployment \
		--output text >/dev/null

test-api-parser:
	python3 -m unittest services/api/tests/test_parser.py

test-api:
	python3 -m unittest discover services/api/tests

build-frontend:
	cd $(FRONTEND_DIR) && npm install && npm run build

deploy-frontend:
	@if [ -z "$(FRONTEND_BUCKET)" ]; then echo "Frontend bucket not found. Run terraform apply in $(TF_DIR)."; exit 1; fi
	@$(MAKE) build-frontend
	AWS_PROFILE=$(AWS_PROFILE) aws s3 sync $(FRONTEND_DIR)/dist s3://$(FRONTEND_BUCKET) --delete
	@if [ -z "$(CLOUDFRONT_DIST_ID)" ]; then echo "CloudFront distribution not found. Run terraform apply in $(TF_DIR)."; exit 1; fi
	AWS_PROFILE=$(AWS_PROFILE) aws cloudfront create-invalidation --distribution-id $(CLOUDFRONT_DIST_ID) --paths "/*"

frontend-env:
	@API_DOMAIN=$$(AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw apigw_custom_domain_name 2>/dev/null); \
	API_BASE_PATH=$$(AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw api_custom_domain_base_path 2>/dev/null); \
	if [ -z "$$API_DOMAIN" ] || [ "$$API_DOMAIN" = "null" ]; then \
		API_URL=$$(AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw apigw_invoke_url 2>/dev/null); \
	else \
		API_URL="https://$$API_DOMAIN"; \
	fi; \
	if [ -n "$$API_BASE_PATH" ] && [ "$$API_BASE_PATH" != "null" ]; then \
		API_URL="$$API_URL/$$API_BASE_PATH"; \
	fi; \
	if ! command -v jq >/dev/null 2>&1; then echo "jq is required to parse API keys."; exit 1; fi; \
	API_KEY=$$(AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -json apigw_api_keys 2>/dev/null | jq -r 'to_entries | if length>0 then .[0].value else "" end' | tr -d \"\\r\"); \
	if [ -z "$$API_URL" ]; then echo \"API URL not found. Run terraform apply in $(TF_DIR).\"; exit 1; fi; \
	if [ -z "$$API_KEY" ]; then echo \"API key not found. Run terraform apply in $(TF_DIR).\"; exit 1; fi; \
	printf "VITE_API_BASE_URL=%s\nVITE_API_KEY=%s\n" "$$API_URL" "$$API_KEY" > $(FRONTEND_DIR)/.env; \
	echo \"Wrote $(FRONTEND_DIR)/.env\"

tf-apply:
	AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) init && AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) apply -auto-approve

tf-destroy:
	AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) destroy -auto-approve

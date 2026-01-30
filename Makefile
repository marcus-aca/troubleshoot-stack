AWS_PROFILE ?= pi
TF_DIR := infra/terraform
API_DIR := services/api

ECR_REPO := $(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw ecr_repository_url 2>/dev/null)
AWS_REGION := $(shell AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) output -raw aws_region 2>/dev/null)

.PHONY: push-api login-ecr build-api test-api-parser tf-apply tf-destroy

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

tf-apply:
	AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) init && AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) apply -auto-approve

tf-destroy:
	AWS_PROFILE=$(AWS_PROFILE) terraform -chdir=$(TF_DIR) destroy -auto-approve

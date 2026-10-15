#!/usr/bin/env bash
# ==============================================================================
# Deployment Script for Privacy Detection Service (https://pii-phi.hekma.ai)
# ==============================================================================

set -e

# Configuration (Override via environment variables if needed)
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
ECR_REPO_NAME="${ECR_REPO_NAME:-privacy-detection-service}"
ECS_CLUSTER_NAME="${ECS_CLUSTER_NAME:-privacy-detection-cluster-production}"
ECS_SERVICE_NAME="${ECS_SERVICE_NAME:-privacy-detection-service-production}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "============================================================"
echo " Deploying Privacy Detection Service to https://pii-phi.hekma.ai "
echo "============================================================"

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "Fetching AWS Account ID from active AWS credentials..."
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query "Account" --output text)
fi

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo "AWS Account ID: ${AWS_ACCOUNT_ID}"
echo "AWS Region:     ${AWS_REGION}"
echo "ECR URI:        ${ECR_URI}:${IMAGE_TAG}"
echo "------------------------------------------------------------"

# 1. Ensure ECR Repository Exists
echo "Step 1: Checking AWS ECR repository..."
aws ecr describe-repositories --repository-names "${ECR_REPO_NAME}" --region "${AWS_REGION}" > /dev/null 2>&1 || \
aws ecr create-repository --repository-name "${ECR_REPO_NAME}" --region "${AWS_REGION}"

# 2. Login to ECR
echo "Step 2: Authenticating Docker with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# 3. Build Docker Image
echo "Step 3: Building production Docker image (with RoBERTa model weights)..."
docker build -t "${ECR_REPO_NAME}:${IMAGE_TAG}" .

# 4. Tag & Push Docker Image
echo "Step 4: Tagging and pushing to ECR..."
docker tag "${ECR_REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

# 5. Force ECS Service Deployment
echo "Step 5: Updating ECS Fargate service..."
aws ecs update-service \
    --cluster "${ECS_CLUSTER_NAME}" \
    --service "${ECS_SERVICE_NAME}" \
    --force-new-deployment \
    --region "${AWS_REGION}" || echo "Note: If ECS service is not yet created, deploy via CloudFormation first."

echo "============================================================"
echo " Deployment process completed!"
echo " Service domain: https://pii-phi.hekma.ai"
echo " Health check:   https://pii-phi.hekma.ai/health"
echo " Readiness:      https://pii-phi.hekma.ai/ready"
echo "============================================================"

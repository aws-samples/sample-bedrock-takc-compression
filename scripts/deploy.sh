#!/bin/bash

# TAKC CDK Deployment Script
# Automates the deployment of Task-Aware Knowledge Compression system using AWS CDK

set -e

echo "🚀 Starting TAKC CDK deployment..."

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CDK_DIR="$PROJECT_ROOT/cdk"
SRC_DIR="$PROJECT_ROOT/src"
DIST_DIR="$PROJECT_ROOT/dist"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v cdk &> /dev/null; then
        log_error "AWS CDK is not installed. Please install CDK first:"
        log_error "  npm install -g aws-cdk"
        exit 1
    fi
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install AWS CLI first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed. Please install Python 3 first."
        exit 1
    fi
    
    log_info "Prerequisites check passed ✓"
}

# Install Python dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Install CDK dependencies
    cd "$CDK_DIR"
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    
    source .venv/bin/activate
    pip install -q -r requirements.txt
    
    log_info "Dependencies installed ✓"
}

# Bootstrap CDK (if needed)
bootstrap_cdk() {
    log_info "Checking CDK bootstrap status..."
    
    cd "$CDK_DIR"
    source .venv/bin/activate
    
    # Get AWS account and region
    AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Check if already bootstrapped
    if aws cloudformation describe-stacks --stack-name CDKToolkit --region "$AWS_REGION" &> /dev/null; then
        log_info "CDK already bootstrapped ✓"
    else
        log_info "Bootstrapping CDK for account $AWS_ACCOUNT in region $AWS_REGION..."
        CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT CDK_DEFAULT_REGION=$AWS_REGION cdk bootstrap
        log_info "CDK bootstrapped ✓"
    fi
}

# Deploy infrastructure
deploy_infrastructure() {
    log_info "Deploying infrastructure with CDK..."
    
    cd "$CDK_DIR"
    source .venv/bin/activate
    
    # Get AWS account and region
    AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Deploy CDK stack
    CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT CDK_DEFAULT_REGION=$AWS_REGION cdk deploy --require-approval never
    
    log_info "Infrastructure deployed ✓"
}

# Get stack outputs
get_stack_outputs() {
    log_info "Retrieving stack outputs..."
    
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Get outputs from CloudFormation
    API_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name TakcStack \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    S3_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name TakcStack \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DataBucketName`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    REDIS_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name TakcStack \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`RedisEndpoint`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$API_ENDPOINT" ]; then
        log_info "API Endpoint: $API_ENDPOINT"
    fi
    
    if [ -n "$S3_BUCKET" ]; then
        log_info "S3 Bucket: $S3_BUCKET"
    fi
    
    if [ -n "$REDIS_ENDPOINT" ]; then
        log_info "Redis Endpoint: $REDIS_ENDPOINT"
    fi
}

# Test deployment
test_deployment() {
    log_info "Testing deployment..."
    
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Get API endpoint
    API_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name TakcStack \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$API_ENDPOINT" ]; then
        log_warn "Could not retrieve API endpoint for testing"
        return
    fi
    
    # Test API
    log_info "Testing API endpoint..."
    TEST_RESULT=$(curl -s -X POST "${API_ENDPOINT}query" \
        -H "Content-Type: application/json" \
        -d '{"query": "Test query", "task_type": "financial-analysis"}' || echo "")
    
    if [[ "$TEST_RESULT" == *"response"* ]] || [[ "$TEST_RESULT" == *"error"* ]]; then
        log_info "API endpoint is responding ✓"
    else
        log_warn "API test inconclusive: $TEST_RESULT"
    fi
}

# Main deployment function
main() {
    log_info "TAKC CDK Deployment Starting..."
    
    check_prerequisites
    install_dependencies
    bootstrap_cdk
    deploy_infrastructure
    get_stack_outputs
    test_deployment
    
    log_info "🎉 TAKC deployment completed successfully!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Upload your data to the S3 bucket (raw-data/ prefix)"
    log_info "2. Data will be automatically processed and compressed"
    log_info "3. Query the system via the API endpoint"
    log_info ""
    log_info "Note: CDK automatically bundled Lambda functions during deployment."
    log_info "See cdk/README.md for detailed usage instructions."
}

# Run main function
main "$@"

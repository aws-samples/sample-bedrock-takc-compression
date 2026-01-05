#!/bin/bash

# TAKC CDK Destroy Script
# Automates the destruction of all AWS resources created by the TAKC CDK system

set -e

echo "🧨 Starting TAKC resource destruction..."

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CDK_DIR="$PROJECT_ROOT/cdk"

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
    
    log_info "Prerequisites check passed ✓"
}

# Get resource information before destruction
get_resource_info() {
    log_info "Getting resource information before destruction..."
    
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Get stack outputs
    if aws cloudformation describe-stacks --stack-name TakcStack --region "$AWS_REGION" &> /dev/null; then
        S3_BUCKET=$(aws cloudformation describe-stacks \
            --stack-name TakcStack \
            --region "$AWS_REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`DataBucketName`].OutputValue' \
            --output text 2>/dev/null || echo "")
        
        API_ENDPOINT=$(aws cloudformation describe-stacks \
            --stack-name TakcStack \
            --region "$AWS_REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
            --output text 2>/dev/null || echo "")
        
        if [ -n "$S3_BUCKET" ]; then
            log_info "S3 Bucket to be destroyed: $S3_BUCKET"
        fi
        
        if [ -n "$API_ENDPOINT" ]; then
            log_info "API Gateway to be destroyed: $API_ENDPOINT"
        fi
    else
        log_warn "Stack not found or already destroyed"
    fi
}

# Clean S3 bucket before destruction
clean_s3_bucket() {
    log_info "Cleaning S3 bucket before destruction..."
    
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Get S3 bucket name
    S3_BUCKET=$(aws cloudformation describe-stacks \
        --stack-name TakcStack \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DataBucketName`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$S3_BUCKET" ]; then
        # Try to find bucket by prefix
        S3_BUCKET=$(aws s3 ls | grep takc-processed-data | awk '{print $3}' | head -1 || echo "")
    fi
    
    if [ -n "$S3_BUCKET" ]; then
        log_info "Emptying S3 bucket: $S3_BUCKET"
        
        # Check if bucket exists
        if aws s3 ls "s3://$S3_BUCKET" &> /dev/null; then
            # Delete all objects and versions
            log_info "Deleting all objects and versions..."
            aws s3 rm "s3://$S3_BUCKET" --recursive
            
            # Delete all versions if versioning is enabled
            aws s3api list-object-versions \
                --bucket "$S3_BUCKET" \
                --output json 2>/dev/null | \
                jq -r '.Versions[]? | .Key + " " + .VersionId' 2>/dev/null | \
                while read key version; do
                    aws s3api delete-object \
                        --bucket "$S3_BUCKET" \
                        --key "$key" \
                        --version-id "$version" 2>/dev/null || true
                done
            
            # Delete delete markers
            aws s3api list-object-versions \
                --bucket "$S3_BUCKET" \
                --output json 2>/dev/null | \
                jq -r '.DeleteMarkers[]? | .Key + " " + .VersionId' 2>/dev/null | \
                while read key version; do
                    aws s3api delete-object \
                        --bucket "$S3_BUCKET" \
                        --key "$key" \
                        --version-id "$version" 2>/dev/null || true
                done
            
            log_info "S3 bucket emptied ✓"
        else
            log_warn "S3 bucket does not exist or is already deleted"
        fi
    else
        log_warn "No S3 bucket found"
    fi
}

# Destroy infrastructure
destroy_infrastructure() {
    log_info "Destroying infrastructure with CDK..."
    
    cd "$CDK_DIR"
    
    # Activate virtual environment if it exists
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    # Get AWS account and region
    AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Destroy CDK stack
    CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT CDK_DEFAULT_REGION=$AWS_REGION cdk destroy --force
    
    log_info "Infrastructure destroyed ✓"
}

# Verify destruction
verify_destruction() {
    log_info "Verifying resource destruction..."
    
    AWS_REGION=$(aws configure get region || echo "us-east-1")
    
    # Check if stack still exists
    if aws cloudformation describe-stacks --stack-name TakcStack --region "$AWS_REGION" &> /dev/null; then
        log_warn "Stack might still exist. Check AWS Console."
    else
        log_info "Stack verified deleted ✓"
    fi
    
    # Check if S3 bucket still exists
    S3_BUCKET=$(aws s3 ls | grep takc-processed-data | awk '{print $3}' | head -1 || echo "")
    if [ -n "$S3_BUCKET" ]; then
        log_warn "S3 bucket might still exist: $S3_BUCKET"
        log_warn "You may need to manually delete it from the AWS console"
    else
        log_info "S3 bucket verified deleted ✓"
    fi
    
    # Check if Lambda functions still exist
    LAMBDA_FUNCTIONS=$(aws lambda list-functions \
        --query "Functions[?contains(FunctionName, 'takc-')].FunctionName" \
        --output text 2>/dev/null || echo "")
    if [ -n "$LAMBDA_FUNCTIONS" ]; then
        log_warn "Some Lambda functions might still exist: $LAMBDA_FUNCTIONS"
    else
        log_info "Lambda functions verified deleted ✓"
    fi
    
    log_info "Destruction verification completed"
}

# Clean local files
clean_local_files() {
    log_info "Cleaning local files..."
    
    # Remove CDK output directory
    rm -rf "$CDK_DIR/cdk.out"
    
    # Remove dist directory contents (keep .gitkeep)
    if [ -d "$PROJECT_ROOT/dist" ]; then
        find "$PROJECT_ROOT/dist" -type f ! -name '.gitkeep' -delete
    fi
    
    log_info "Local files cleaned ✓"
}

# Main destruction function
main() {
    log_info "TAKC CDK Destruction Starting..."
    
    # Ask for confirmation
    read -p "⚠️  This will destroy all TAKC resources in AWS. Are you sure? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Destruction cancelled."
        exit 0
    fi
    
    check_prerequisites
    get_resource_info
    clean_s3_bucket
    destroy_infrastructure
    verify_destruction
    clean_local_files
    
    log_info "🎉 TAKC destruction completed successfully!"
    log_info ""
    log_info "If any resources could not be automatically destroyed, please check"
    log_info "the AWS Management Console and delete them manually."
}

# Run main function
main "$@"

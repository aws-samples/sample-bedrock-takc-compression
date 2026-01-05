# TAKC Deployment Guide

## Prerequisites

Before deploying TAKC, ensure you have the following:

### Required Tools
- **Node.js** >= 18.0 (for AWS CDK)
- **AWS CDK CLI** >= 2.100.0
- **AWS CLI** >= 2.0
- **Python** >= 3.9
- **Git**

### AWS Requirements
- AWS Account with appropriate permissions
- AWS CLI configured with credentials
- Access to the following AWS services:
  - AWS Lambda
  - Amazon Simple Storage Service (Amazon S3)
  - Amazon ElastiCache
  - Amazon API Gateway
  - AWS Identity and Access Management (IAM)
  - Amazon Virtual Private Cloud (Amazon VPC)
  - Amazon Bedrock

### Permissions Required
Your AWS user/role needs the following permissions:
- `AWSLambdaFullAccess`
- `AmazonS3FullAccess`
- `AmazonElastiCacheFullAccess`
- `AmazonAPIGatewayAdministrator`
- `IAMFullAccess`
- `AmazonVPCFullAccess`

## Quick Start Deployment

### 1. Clone and Setup

```bash
git clone <repository-url>
cd takc-project
```

### 2. Configure AWS Credentials

```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, and region
```

### 3. Install CDK CLI

```bash
npm install -g aws-cdk
```

### 4. Deploy Infrastructure

```bash
# Make deployment script executable
chmod +x scripts/deploy.sh

# Run deployment
./scripts/deploy.sh
```

The deployment script will:
- Check prerequisites
- Install Python dependencies
- Bootstrap CDK environment
- Deploy infrastructure with CDK
- Run basic tests

### 4. Verify Deployment

After deployment, you'll see output similar to:

```
🎉 TAKC deployment completed successfully!

Outputs:
  S3 Bucket: takc-processed-data-a1b2c3d4
  Redis Endpoint: takc-cache-a1b2c3d4.abc123.cache.amazonaws.com
  API Gateway URL: https://xyz123.execute-api.us-east-1.amazonaws.com/dev/query
```

## Manual Deployment Steps

If you prefer manual deployment or need to customize the process:

### 1. Install Dependencies

```bash
# Install CDK CLI
npm install -g aws-cdk

# Install Python dependencies
cd cdk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure CDK Context (Optional)

```bash
# Copy example configuration
cp cdk.context.json.example cdk.context.json

# Edit with your preferences
nano cdk.context.json
```

### 3. Deploy with CDK

```bash
# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy stack
cdk deploy
```

### 4. Configure Environment Variables

Update your shell profile with the CDK outputs:

```bash
export TAKC_S3_BUCKET=$(aws cloudformation describe-stacks --stack-name TakcStack --query 'Stacks[0].Outputs[?OutputKey==`DataBucketName`].OutputValue' --output text)
export TAKC_REDIS_ENDPOINT=$(aws cloudformation describe-stacks --stack-name TakcStack --query 'Stacks[0].Outputs[?OutputKey==`CacheEndpoint`].OutputValue' --output text)
export TAKC_API_URL=$(aws cloudformation describe-stacks --stack-name TakcStack --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' --output text)
```

## Configuration Options

### CDK Context Variables

You can customize the deployment by editing `cdk.context.json`:

```json
{
  "environment": "dev",
  "bedrock_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
  "cache_node_type": "cache.t4g.small"
}
```

### Environment-Specific Configurations

#### Development
```bash
# Edit cdk.context.json
{
  "environment": "dev"
}
cdk deploy
```
- Uses smaller instance sizes
- ElastiCache Serverless
- Basic monitoring

#### Production
```bash
# Edit cdk.context.json
{
  "environment": "prod"
}
cdk deploy
```
- Enhanced monitoring
- Backup configurations
- Production-grade settings

## Post-Deployment Setup

### 1. Upload Sample Data

```bash
# Create a sample document
echo "Sample financial report content..." > sample-data.txt

# Upload to S3
aws s3 cp sample-data.txt s3://$TAKC_S3_BUCKET/raw-data/
```

### 2. Process Data

```bash
python src/data_processor.py \
  --source "s3://$TAKC_S3_BUCKET/raw-data/sample-data.txt" \
  --task-type "financial-analysis"
```

### 3. Create Compressed Caches

```bash
python src/compression_service.py \
  --task-type "financial-analysis" \
  --context-file sample-data.txt \
  --compression-rates medium high
```

### 4. Test Queries

```bash
python src/query_processor.py \
  --query "What are the key financial highlights?" \
  --task-type "financial-analysis"
```

## Testing the Deployment

### Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-mock

# Run tests
pytest tests/
```

### Integration Tests

```bash
# Test API endpoints
curl -X POST $TAKC_API_URL \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Test query",
    "task_type": "financial-analysis"
  }'
```

### Load Testing

```bash
# Install load testing tool
pip install locust

# Run load tests
locust -f tests/load_test.py --host=$TAKC_API_URL
```

## Monitoring and Maintenance

### CloudWatch Dashboards

The deployment creates CloudWatch dashboards for monitoring:
- Lambda function metrics
- API Gateway performance
- ElastiCache statistics
- S3 usage

### Log Analysis

```bash
# View Lambda logs
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/takc"

# Tail logs in real-time
aws logs tail /aws/lambda/takc-query-processor --follow
```

### Performance Tuning

#### Lambda Optimization
```bash
# Update Lambda memory
aws lambda update-function-configuration \
  --function-name takc-query-processor \
  --memory-size 1024
```

#### Cache Optimization
```bash
# Scale ElastiCache
aws elasticache modify-replication-group \
  --replication-group-id takc-cache \
  --node-type cache.t3.medium
```

## Troubleshooting

### Common Issues

#### 1. Lambda Timeout Errors
```bash
# Increase timeout
aws lambda update-function-configuration \
  --function-name takc-data-processor \
  --timeout 900
```

#### 2. S3 Permission Errors
```bash
# Check bucket policy
aws s3api get-bucket-policy --bucket $TAKC_S3_BUCKET
```

#### 3. VPC Connectivity Issues
```bash
# Check security groups
aws ec2 describe-security-groups --group-names takc-lambda-*
```

### Debug Mode

Enable debug logging:

```bash
export TAKC_DEBUG=true
python src/query_processor.py --query "test" --task-type "debug"
```

### Health Checks

```bash
# Check system health
curl $TAKC_API_URL/../health

# Check specific components
aws lambda invoke \
  --function-name takc-query-processor \
  --payload '{"test": true}' \
  response.json
```

## Scaling Considerations

### Horizontal Scaling

#### Lambda Concurrency
```bash
# Set reserved concurrency
aws lambda put-reserved-concurrency \
  --function-name takc-query-processor \
  --reserved-concurrent-executions 100
```

#### ElastiCache Clustering
```bash
# Add cache nodes
aws elasticache increase-replica-count \
  --replication-group-id takc-cache \
  --new-replica-count 2
```

### Vertical Scaling

#### Memory Optimization
- Monitor Lambda memory usage
- Adjust based on workload patterns
- Use CloudWatch metrics for decisions

#### Storage Optimization
- Implement S3 lifecycle policies
- Use appropriate storage classes
- Monitor cache hit rates

## Security Hardening

### Network Security
```bash
# Update security groups for minimal access
aws ec2 authorize-security-group-ingress \
  --group-id sg-12345678 \
  --protocol tcp \
  --port 6379 \
  --source-group sg-87654321
```

### Encryption
- Enable S3 bucket encryption
- Use ElastiCache encryption in transit
- Implement API Gateway authentication

### Access Control
```bash
# Create least-privilege IAM policies
aws iam create-policy \
  --policy-name TAKCMinimalAccess \
  --policy-document file://minimal-policy.json
```

## Backup and Recovery

### Automated Backups
```bash
# Enable S3 versioning
aws s3api put-bucket-versioning \
  --bucket $TAKC_S3_BUCKET \
  --versioning-configuration Status=Enabled
```

### Disaster Recovery
- Multi-region deployment options
- Cross-region replication
- Automated failover procedures

## Cost Optimization

### Resource Right-Sizing
- Monitor Lambda execution duration
- Optimize memory allocation
- Use appropriate cache instance types

### Cost Monitoring
```bash
# Set up billing alerts
aws budgets create-budget \
  --account-id 123456789012 \
  --budget file://budget.json
```

## Cleanup

To remove all resources:

```bash
# Using the destroy script (recommended)
./scripts/destroy.sh

# Or manually
cd cdk
cdk destroy
```

This will remove all AWS resources created by the deployment.

## Support and Troubleshooting

For issues and support:
1. Check the troubleshooting section above
2. Review CloudWatch logs
3. Consult the API reference documentation
4. Check AWS service health dashboards
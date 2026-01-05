# S3 Event Automation Testing Guide

This guide provides step-by-step instructions for testing the S3 event-driven automation pipeline.

## Prerequisites

Before testing, ensure you have:
- AWS CLI configured with appropriate credentials
- AWS CDK CLI installed (version >= 2.100.0)
- Node.js installed (for CDK)
- Python 3.9+ installed
- Docker installed (for CDK Lambda bundling)
- Access to Amazon Bedrock (Claude 3 Haiku model approved)

## Step 1: Deploy Infrastructure

> **Note**: CDK automatically bundles Lambda functions during deployment using Docker. No manual packaging required.

```bash
# Navigate to CDK directory
cd cdk

# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap

# Review the deployment plan
cdk diff

# Deploy the infrastructure
cdk deploy
```

**Note the outputs** after deployment:
- `s3_bucket_name`: Your S3 bucket name
- `lambda_function_names`: Names of deployed Lambda functions
- `api_gateway_url`: API endpoint for queries

## Step 3: Verify Lambda Functions

```bash
# List Lambda functions
aws lambda list-functions --query 'Functions[?contains(FunctionName, `takc`)].FunctionName'

# Expected output:
# [
#     "takc-data-processor-{suffix}",
#     "takc-compression-processor-{suffix}",
#     "takc-query-processor-{suffix}"
# ]
```

## Step 4: Test the S3 Event Pipeline

### 4.1 Upload Test File

```bash
# Get your S3 bucket name from CDK output
BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name TakcStack --query 'Stacks[0].Outputs[?OutputKey==`DataBucketName`].OutputValue' --output text)

# Upload a test file to trigger the pipeline
aws s3 cp tests/sample-financial-data.txt \
  s3://${BUCKET_NAME}/raw-data/financial/sample.txt
```

### 4.2 Monitor Data Processor Lambda

```bash
# Watch the data processor logs in real-time
aws logs tail /aws/lambda/takc-data-processor-{suffix} --follow

# Expected log entries:
# - "Processing chunk X/Y"
# - "Stored chunks to S3"
# - "Triggered compression for financial"
```

### 4.3 Monitor Compression Lambda

```bash
# Watch the compression processor logs in real-time
aws logs tail /aws/lambda/takc-compression-processor-{suffix} --follow

# Expected log entries:
# - "Starting compression for task_type: financial"
# - "Creating ultra compression cache..."
# - "Creating high compression cache..."
# - "Creating medium compression cache..."
# - "Creating light compression cache..."
# - "Compression complete for financial"
```

### 4.4 Verify Processed Chunks

```bash
# Check that chunks were created
aws s3 ls s3://${BUCKET_NAME}/financial/

# Expected output:
# chunk_0000.txt
# chunk_0001.txt
# chunk_0002.txt
# ...
```

### 4.5 Verify Compressed Caches

```bash
# Check that compressed caches were created
aws s3 ls s3://${BUCKET_NAME}/cache/v2/financial/ --recursive

# Expected output:
# cache/v2/financial/ultra/cache.json
# cache/v2/financial/high/cache.json
# cache/v2/financial/medium/cache.json
# cache/v2/financial/light/cache.json
```

## Step 5: Test Query Processing

### 5.1 Query with Compressed Context

```bash
# Get API Gateway URL
API_URL=$(aws cloudformation describe-stacks --stack-name TakcStack --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' --output text)

# Send a test query
curl -X POST ${API_URL} \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "financial",
    "query": "What are the key financial metrics?",
    "compression_rate": "medium"
  }'
```

### 5.2 Monitor Query Processor

```bash
# Watch query processor logs
aws logs tail /aws/lambda/takc-query-processor-{suffix} --follow

# Expected log entries:
# - "Retrieved cache for financial:medium"
# - "Invoking Bedrock for inference"
# - "Query processed successfully"
```

## Step 6: Test Different Task Types

### 6.1 Upload Medical Data

```bash
# Create a test medical file
echo "Patient records and medical history data..." > /tmp/medical-test.txt

# Upload to trigger pipeline
aws s3 cp /tmp/medical-test.txt \
  s3://${BUCKET_NAME}/raw-data/medical/records.txt
```

### 6.2 Upload Legal Data

```bash
# Create a test legal file
echo "Legal documents and contract information..." > /tmp/legal-test.txt

# Upload to trigger pipeline
aws s3 cp /tmp/legal-test.txt \
  s3://${BUCKET_NAME}/raw-data/legal/contracts.txt
```

### 6.3 Verify Multiple Task Types

```bash
# List all compressed caches
aws s3 ls s3://${BUCKET_NAME}/cache/v2/ --recursive

# Expected output:
# cache/v2/financial/ultra/cache.json
# cache/v2/financial/high/cache.json
# cache/v2/financial/medium/cache.json
# cache/v2/financial/light/cache.json
# cache/v2/medical/ultra/cache.json
# cache/v2/medical/high/cache.json
# ...
# cache/v2/legal/ultra/cache.json
# cache/v2/legal/high/cache.json
# ...
```

## Step 7: Verify ElastiCache Storage

```bash
# Get Redis endpoint
REDIS_ENDPOINT=$(aws cloudformation describe-stacks --stack-name TakcStack --query 'Stacks[0].Outputs[?OutputKey==`RedisEndpoint`].OutputValue' --output text)

# Connect to Redis (requires redis-cli and VPC access)
redis-cli -h ${REDIS_ENDPOINT} --tls

# Check cache keys
KEYS takc:*

# Expected output:
# takc:financial:ultra:data
# takc:financial:ultra:metadata
# takc:financial:high:data
# takc:financial:high:metadata
# ...
```

## Step 8: Performance Testing

### 8.1 Test Compression Ratios

```bash
# Check compression metrics in CloudWatch
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=takc-compression-processor-{suffix} \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum
```

### 8.2 Test Query Latency

```bash
# Measure query response time
time curl -X POST ${API_URL} \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "financial",
    "query": "Summarize the financial data",
    "compression_rate": "ultra"
  }'
```

## Troubleshooting

### Lambda Function Not Triggered

```bash
# Check S3 event notification configuration
aws s3api get-bucket-notification-configuration \
  --bucket ${BUCKET_NAME}

# Verify Lambda permissions
aws lambda get-policy \
  --function-name takc-data-processor-{suffix}
```

### Compression Fails

```bash
# Check Bedrock model access
aws bedrock list-foundation-models \
  --query 'modelSummaries[?contains(modelId, `claude-3-haiku`)].modelId'

# Check Lambda execution role permissions
aws iam get-role-policy \
  --role-name takc-lambda-role-{suffix} \
  --policy-name takc-lambda-policy-{suffix}
```

### Cache Not Found

```bash
# Verify ElastiCache cluster status
aws elasticache describe-replication-groups \
  --replication-group-id takc-cache-{suffix}

# Check Lambda VPC configuration
aws lambda get-function-configuration \
  --function-name takc-compression-processor-{suffix} \
  --query 'VpcConfig'
```

## Cleanup

To remove all resources after testing:

```bash
# Run the destroy script
./scripts/destroy.sh

# Or manually with CDK
cd cdk
cdk destroy
```

## Expected Results

After successful testing, you should see:

1. ✅ S3 upload automatically triggers data processing
2. ✅ Data processor creates chunks and invokes compression
3. ✅ Compression service creates 4 compression rates
4. ✅ Caches stored in both ElastiCache and S3
5. ✅ Query API successfully retrieves and uses compressed context
6. ✅ All operations logged to CloudWatch

## Performance Benchmarks

Expected performance metrics:

- **Data Processing**: 1-5 seconds for typical files
- **Compression (per rate)**: 10-30 seconds depending on content size
- **Total Pipeline**: 1-2 minutes for complete multi-rate compression
- **Query Latency**: 500ms-2s with cached compression
- **Cost Reduction**: 8-64× reduction in Bedrock token costs

## Next Steps

After successful testing:

1. Review CloudWatch logs for any warnings or errors
2. Adjust Lambda memory/timeout settings if needed
3. Configure CloudWatch alarms for production monitoring
4. Set up S3 lifecycle policies for old chunks
5. Configure ElastiCache backup and retention policies

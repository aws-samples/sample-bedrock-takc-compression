# TAKC CDK Infrastructure

Python CDK implementation of the Task-Aware Knowledge Compression (TAKC) infrastructure on AWS.

## Overview

This CDK app provides a Python-based infrastructure-as-code solution with:
- Native Python integration with your application code
- Type safety and IDE autocomplete
- Clean, programmatic resource management
- Automatic Lambda function bundling (no manual packaging needed)
- Simplified deployment workflow
- Uses default VPC for faster deployment

## Infrastructure Components

- **Amazon Bedrock** - LLM-powered compression
- **AWS Lambda** - 3 functions (data processor, compression processor, query processor)
- **ElastiCache Serverless** - Redis-compatible cache with auto-scaling
- **Amazon S3** - Data storage with versioning and KMS encryption
- **AWS KMS** - Customer Managed Key for S3 encryption with automatic rotation
- **AWS WAF** - Web Application Firewall protecting API Gateway
- **Amazon API Gateway** - REST API for queries (no authentication - add Cognito/Lambda Authorizer for production)
- **Default VPC** - Uses your AWS account's default VPC for simplified deployment
- **CloudWatch** - Monitoring and alarms

> **Security Note**: This reference implementation does not include:
> - API authentication (add Amazon Cognito, Lambda Authorizers, or API Keys for production)
> - Amazon Bedrock Guardrails (add for content filtering, PII redaction, and safety controls)

### Why ElastiCache Serverless?

**Perfect for demos and production:**
- Provisions in ~2-3 minutes (vs 10-15 min for provisioned clusters)
- Serverless, auto-scaling (no instance management)
- Pay only for what you use (ECPU-based pricing)
- Redis-compatible (works with existing Redis clients)
- Multi-AZ by default
- Automatic scaling from 0 to configured max

> **Note**: This codebase demonstrates Task-Aware Knowledge Compression using Redis as the key-value store. For production, you can adjust the cache limits in `takc_stack.py` or switch to other solutions like ElastiCache provisioned clusters, MemoryDB for Valkey, or self-managed Redis/Valkey based on your requirements.

## Prerequisites

```bash
# Install AWS CDK CLI
npm install -g aws-cdk

# Install Docker (required for Lambda bundling)
# macOS: Install Docker Desktop
# Linux: Install Docker Engine
# Windows: Install Docker Desktop

# Install Python dependencies
pip install -r requirements.txt

# Configure AWS credentials
aws configure
```

## Quick Start

### 1. Install Prerequisites

```bash
# Install AWS CDK CLI
npm install -g aws-cdk

# Install Python dependencies
cd cdk
pip install -r requirements.txt
```

### 2. Deploy Infrastructure

```bash
# Bootstrap CDK (first time only, per account/region)
cdk bootstrap

# Preview changes (optional)
cdk diff

# Deploy (CDK automatically packages Lambda functions)
cdk deploy
```

> **Note**: CDK automatically bundles Lambda functions during deployment. No manual packaging required.

## Configuration

Configuration is managed through `cdk.json` context values. You can override them:

### Via cdk.json (recommended)

Edit the `context` section in `cdk.json`:

```json
{
  "context": {
    "aws_region": "us-east-1",
    "environment": "dev",
    "project_name": "TAKC",
    "bedrock_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
    "lambda_timeout_data_processor": 5,
    "lambda_timeout_query_processor": 60,
    "lambda_memory_data_processor": 512,
    "lambda_memory_query_processor": 256,
    "redis_node_type": "cache.t3.micro",
    "enable_monitoring": true
  }
}
```

### Via Command Line

```bash
cdk deploy \
  -c environment=prod \
  -c bedrock_model_id=anthropic.claude-3-sonnet-20240229-v1:0 \
  -c redis_node_type=cache.t3.small
```

### Via Environment Variables

```bash
export CDK_DEFAULT_ACCOUNT=123456789012
export CDK_DEFAULT_REGION=us-west-2
cdk deploy
```

## Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `aws_region` | AWS region | `us-east-1` |
| `environment` | Environment (dev/staging/prod) | `dev` |
| `project_name` | Project name for tagging | `TAKC` |
| `bedrock_model_id` | Bedrock model for compression | `anthropic.claude-3-haiku-20240307-v1:0` |
| `lambda_timeout_data_processor` | Data processor timeout (minutes) | `5` |
| `lambda_timeout_query_processor` | Query processor timeout (seconds) | `60` |
| `lambda_memory_data_processor` | Data processor memory (MB) | `512` |
| `lambda_memory_query_processor` | Query processor memory (MB) | `256` |
| `enable_monitoring` | Enable CloudWatch alarms | `true` |

### ElastiCache Serverless Configuration

ElastiCache Serverless is configured with default limits in `takc_stack.py`:
- **Max Data Storage**: 5 GB (adjust in code for production)
- **Max ECPU/second**: 5000 (adjust based on workload)

To modify limits, edit the `cache_usage_limits` in `takc_stack.py`.

## Bedrock Model Options

| Model ID | Use Case | Cost |
|----------|----------|------|
| `anthropic.claude-3-haiku-20240307-v1:0` | Development, cost-effective | Low |
| `anthropic.claude-3-sonnet-20240229-v1:0` | Production, balanced | Medium |
| `anthropic.claude-3-opus-20240229-v1:0` | High quality requirements | High |

## Alternative Cache Options

While ElastiCache Serverless is the default, you can modify `takc_stack.py` to use:

1. **ElastiCache Provisioned Clusters** - Fixed capacity, predictable pricing
   - Better for steady, high-throughput workloads
   - Requires instance type selection (cache.t3.micro, cache.r7g.large, etc.)

2. **Amazon MemoryDB for Valkey** - Redis-compatible with durability
   - Multi-AZ durability with transaction logs
   - Microsecond read latency
   - Best for applications requiring data persistence

3. **Self-managed Redis/Valkey** - Full control
   - Deploy on EC2, ECS, or EKS
   - More operational overhead
   - Maximum flexibility

All options are Redis-compatible and work with the existing Lambda code.

## Lambda Bundling

CDK automatically bundles Lambda functions using Docker during deployment. The bundling process:

1. Uses the official Python 3.9 Docker image
2. Installs dependencies from `requirements.txt`
3. Copies necessary Python files
4. Creates deployment packages automatically

**No manual packaging required!** Just run `cdk deploy`.

## Useful CDK Commands

```bash
# List all stacks
cdk list

# Show differences from deployed stack
cdk diff

# Deploy with approval prompts
cdk deploy --require-approval never

# View synthesized CloudFormation template
cdk synth

# Destroy all resources
cdk destroy

# Watch mode (auto-deploy on changes)
cdk watch
```

## Outputs

After deployment, CDK outputs:

- `ApiEndpoint` - API Gateway URL for queries
- `DataBucketName` - S3 bucket name (encrypted with KMS)
- `RedisEndpoint` - ElastiCache Serverless Redis endpoint
- `DataProcessorFunction` - Data processor Lambda name
- `CompressionProcessorFunction` - Compression Lambda name
- `QueryProcessorFunction` - Query Lambda name
- `WebACLArn` - AWS WAF Web ACL ARN protecting the API
- `KmsKeyId` - KMS Key ID for S3 bucket encryption

Access outputs:
```bash
cdk deploy --outputs-file outputs.json
cat outputs.json
```

## Testing the Deployment

```bash
# Get API endpoint
API_URL=$(aws cloudformation describe-stacks \
  --stack-name TakcStack \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
  --output text)

# Test query endpoint
curl -X POST "${API_URL}query" \
  -H "Content-Type: application/json" \
  -d '{"query": "test query", "context": "test context"}'

# Upload test file to trigger processing
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name TakcStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DataBucketName`].OutputValue' \
  --output text)

echo "Test data" > test.txt
aws s3 cp test.txt "s3://${BUCKET}/raw-data/test.txt"
```

## Troubleshooting

### Bootstrap Required

```
Error: This stack uses assets, so the toolkit stack must be deployed
Solution: Run 'cdk bootstrap' once per account/region
```

### Docker Not Running

```
Error: Cannot connect to Docker daemon
Solution: Start Docker Desktop or Docker Engine
```

### Check Logs

```bash
# View Lambda logs
aws logs tail /aws/lambda/takc-data-processor-XXXXX --follow

# View all log groups
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/takc
```

## File Structure

```
cdk/
├── app.py                 # CDK app entry point
├── takc_stack.py         # Main stack definition
├── requirements.txt      # Python dependencies
├── cdk.json             # CDK configuration
└── README.md            # This file
```

## Cleanup

```bash
# Destroy all resources
cdk destroy

# Confirm deletion
# Type 'y' when prompted
```

## Best Practices

1. **Version Control** - Commit `cdk.json` but not `cdk.context.json`
2. **Environments** - Use separate AWS accounts for dev/staging/prod
3. **CI/CD** - Integrate `cdk deploy` into your pipeline
4. **Testing** - Use `cdk diff` before deploying
5. **Monitoring** - Enable CloudWatch alarms in production
6. **Docker** - Ensure Docker is running before deployment

## Support

For issues:
1. Check CloudWatch logs for Lambda functions
2. Review CDK synthesis output: `cdk synth`
3. Validate CloudFormation template
4. Check AWS service quotas
5. Ensure Docker is running
6. Review main project documentation

## Additional Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [CDK Python Reference](https://docs.aws.amazon.com/cdk/api/v2/python/)
- [CDK Examples](https://github.com/aws-samples/aws-cdk-examples)

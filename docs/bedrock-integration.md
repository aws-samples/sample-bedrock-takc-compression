# Amazon Bedrock Integration for TAKC

## Overview

This document describes how Amazon Bedrock is integrated into the Task-Aware Knowledge Compression (TAKC) reference implementation to provide foundation model-based compression capabilities.

Amazon Bedrock is a fully managed service that provides access to foundation models from leading AI companies through a single API.

## Why Amazon Bedrock

### Service Benefits

1. **Managed Service**: Amazon Bedrock reduces infrastructure management overhead with no endpoints to maintain
2. **Pay-per-Token Pricing**: Usage-based pricing model for variable workloads
3. **Multiple Model Access**: Provides access to Claude 3, Llama 2, and Titan model families through a unified API
4. **Managed Scaling**: Automatic scaling based on demand
5. **Security Features**: Includes security and monitoring capabilities

### Implementation Approach

The Amazon Bedrock integration includes:
- **Task-aware prompting** with optional few-shot examples
- **Iterative compression** processing chunks sequentially  
- **Multi-rate compression** at 8×, 16×, 32×, and 64× target ratios
- **Context compression** for efficient knowledge representation

## Customer Responsibilities

When using this Amazon Bedrock integration, customers are responsible for:
- Requesting and managing Amazon Bedrock model access permissions
- Configuring appropriate security controls and access policies
- Monitoring token usage and associated costs
- Implementing data governance and privacy controls
- Conducting regular security assessments

## Available Models

| Model | Model ID | Strengths | Cost | Use Case |
|-------|----------|-----------|------|----------|
| Claude 3 Haiku | `anthropic.claude-3-haiku-20240307-v1:0` | Fast, cost-effective | Low | General compression |
| Claude 3 Sonnet | `anthropic.claude-3-sonnet-20240229-v1:0` | Balanced performance | Medium | Complex reasoning |
| Claude 3 Opus | `anthropic.claude-3-opus-20240229-v1:0` | Highest quality | High | Critical applications |
| Titan Text | `amazon.titan-text-express-v1` | AWS native | Low | Basic compression |

## Implementation Details

### Compression Process

1. **Task Definition**: Create task-specific prompts with optional few-shot examples
2. **Context Chunking**: Split large documents into manageable chunks with overlap
3. **Iterative Compression**: Process chunks sequentially using Bedrock models
4. **Multi-Rate Generation**: Create compressions at different ratios
5. **Cache Storage**: Store compressed representations in Redis and S3

### Prompt Engineering

The system uses carefully crafted prompts optimized for each model:

```python
def create_compression_prompt(task_description, few_shot_examples=None):
    prompt = f"""You are performing task-aware knowledge compression. Your goal is to compress the given context while preserving all information relevant to the specified task.

TASK: {task_description}

{few_shot_examples if few_shot_examples else ""}

COMPRESSION INSTRUCTIONS:
1. Focus on key facts and relationships relevant to the task
2. Preserve important numerical data and metrics
3. Maintain critical entities and their attributes
4. Keep causal relationships and dependencies
5. Remove redundant or irrelevant information
6. Use concise language while maintaining accuracy

CONTEXT TO COMPRESS:
"""
    return prompt
```

### Performance Characteristics

Compression performance varies based on content type, model selection, and task complexity:

| Compression Rate | Target Ratio | Typical Use Case |
|------------------|--------------|------------------|
| Light (8×)       | 8:1          | High accuracy requirements |
| Medium (16×)     | 16:1         | Balanced compression and quality |
| High (32×)       | 32:1         | General purpose compression |
| Ultra (64×)      | 64:1         | Maximum compression for simple queries |

Actual compression ratios and latency will vary based on your specific content and configuration.

## Usage Examples

### Basic Compression

```python
from bedrock_compression_service import BedrockCompressionService, CompressionConfig

service = BedrockCompressionService()

config = CompressionConfig(
    compression_rate="medium",
    task_description="Answer questions about financial performance",
    model_id="anthropic.claude-3-haiku-20240307-v1:0"
)

result = service.compress_context(context, config)
print(f"Compressed {result['original_tokens']} → {result['compressed_tokens']} tokens")
```

### Multi-Rate Compression

```python
cache_keys = service.create_multi_rate_cache(
    task_type="financial-analysis",
    context=document_text,
    task_description="Answer questions about financial performance and metrics"
)
```

### Model Testing

```python
# Test available models
for name, model_id in service.list_available_models().items():
    if service.test_model_access(model_id):
        print(f"✅ {name} is available")
```

## Cost Analysis

### Bedrock Pricing (as of 2024)

| Model | Input Tokens | Output Tokens | Example Cost (1M tokens) |
|-------|--------------|---------------|---------------------------|
| Claude 3 Haiku | $0.25/1M | $1.25/1M | ~$0.50 |
| Claude 3 Sonnet | $3.00/1M | $15.00/1M | ~$6.00 |
| Titan Text | $0.50/1M | $0.65/1M | ~$0.58 |

### Cost Model

Amazon Bedrock uses a pay-per-token pricing model:
- No base infrastructure costs
- Charges based on input and output tokens processed
- No charges when not in use

Refer to AWS Bedrock pricing documentation for current rates and to evaluate cost-effectiveness for your specific workload.

## Deployment Guide

### Prerequisites

1. **AWS Account** with Bedrock access
2. **Model Access**: Request access to desired models in Bedrock console
3. **AWS CLI**: Configured with appropriate permissions
4. **AWS CDK**: For infrastructure deployment

### Step-by-Step Deployment

1. **Deploy Infrastructure**:
   ```bash
   cd cdk
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cdk bootstrap
   cdk deploy
   ```

2. **Test Integration**:
   ```bash
   python examples/bedrock_compression_example.py
   ```

3. **Run Tests**:
   ```bash
   python tests/test_bedrock_compression.py --all
   ```

### Configuration

#### Environment Variables

- `BEDROCK_MODEL_ID`: Default model to use (configured in CDK)
- `AWS_REGION`: AWS region for Bedrock (defaults to us-east-1)
- `S3_BUCKET`: S3 bucket for cache storage
- `REDIS_ENDPOINT`: Redis endpoint for fast cache retrieval

#### Model Selection

Choose models based on your requirements:

```python
# Cost-optimized
config.model_id = "anthropic.claude-3-haiku-20240307-v1:0"

# Balanced performance
config.model_id = "anthropic.claude-3-sonnet-20240229-v1:0"

# Maximum quality
config.model_id = "anthropic.claude-3-opus-20240229-v1:0"
```

## Monitoring and Observability

### CloudWatch Metrics

Bedrock automatically provides:
- **Invocation Count**: Number of model calls
- **Invocation Latency**: Response times
- **Invocation Errors**: Failed requests
- **Token Usage**: Input/output token consumption

### Custom Metrics

The TAKC service tracks:
- **Compression Ratios**: Actual vs. target compression achieved
- **Cache Hit Rates**: Frequency of cache usage vs. new compressions
- **Model Performance**: Success rates by model type
- **Cost Tracking**: Token usage and estimated costs

### Alerting

Consider setting up CloudWatch alarms for:
- **Error Rate**: Monitor Bedrock invocation failures
- **Latency**: Track response times
- **Costs**: Monitor token usage and spending
- **Throttling**: Detect rate limit issues

## Security Considerations

### Data Protection

1. **Encryption**: All data encrypted in transit to Bedrock
2. **VPC Isolation**: Lambda functions in private subnets
3. **IAM Policies**: Least privilege access to Bedrock models
4. **Audit Logging**: All API calls logged to CloudTrail

### Model Security

1. **Access Control**: Restrict model access to authorized services
2. **Data Residency**: Configure data residency based on region selection
3. **Data Usage**: Review AWS Bedrock data usage policies
4. **Compliance**: Review AWS compliance certifications for your requirements

### Best Practices

1. **Prompt Injection Protection**: Validate and sanitize inputs
2. **Rate Limiting**: Implement application-level rate limits
3. **Cost Controls**: Set up billing alerts and limits
4. **Model Rotation**: Use multiple models for redundancy

## Troubleshooting

### Common Issues

1. **Model Access Denied**:
   ```
   Error: ValidationException - Model access not granted
   Solution: Request model access in Bedrock console
   ```

2. **Rate Limiting**:
   ```
   Error: ThrottlingException - Rate exceeded
   Solution: Implement exponential backoff and retry logic
   ```

3. **High Latency**:
   ```
   Issue: Slow compression responses
   Solution: Use Claude 3 Haiku for faster responses
   ```

4. **Poor Compression Quality**:
   ```
   Issue: Compressed text loses important information
   Solution: Improve task description and few-shot examples
   ```

### Debugging Tools

1. **Model Testing**: Use `test_model_access()` to verify connectivity
2. **Compression Testing**: Test with known content to validate quality
3. **CloudWatch Logs**: Review Lambda and Bedrock logs for errors
4. **Cost Monitoring**: Track token usage to identify inefficiencies

## Performance Optimization

### Compression Quality

1. **Task Description**: Be specific about the information to preserve
2. **Few-Shot Examples**: Provide examples when beneficial
3. **Model Selection**: Choose models based on your quality requirements
4. **Chunk Size**: Optimize chunk size based on content type

### Cost Optimization

1. **Model Selection**: Choose models based on cost and performance needs
2. **Caching**: Implement caching to reduce repeated compressions
3. **Batch Processing**: Process multiple documents efficiently
4. **Compression Rate**: Select compression rates based on requirements

### Latency Optimization

1. **Parallel Processing**: Process multiple chunks concurrently where possible
2. **Model Selection**: Consider model latency characteristics
3. **Chunk Optimization**: Balance chunk size and processing time
4. **Caching Strategy**: Implement appropriate caching

## Potential Enhancements

This reference implementation can be extended with:

1. **Streaming Processing**: For large documents
2. **Adaptive Model Selection**: Dynamic model selection based on requirements
3. **Custom Optimization**: Domain-specific tuning
4. **Additional Modalities**: Support for different content types

These enhancements are not included in the current implementation.

## Summary

This reference implementation uses Amazon Bedrock to demonstrate Task-Aware Knowledge Compression:

- **Managed Service**: Reduces infrastructure management overhead
- **Pay-per-Token**: Usage-based pricing model
- **Multiple Models**: Access to various foundation models
- **Security**: Built-in security and monitoring features

### Implementation Considerations

1. **Permissions**: Ensure appropriate Bedrock permissions are configured
2. **Prompt Engineering**: Optimize compression prompts for your use case
3. **Cost Monitoring**: Implement cost tracking and alerts
4. **Quality Validation**: Test compression quality with your specific content

### Getting Started

1. Deploy the infrastructure using CDK
2. Test with your specific content
3. Adjust configuration based on your requirements

**Note**: Ensure you have appropriate Amazon Bedrock permissions configured in your AWS account.

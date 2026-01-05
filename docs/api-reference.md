# TAKC API Reference

## Overview

The TAKC system provides REST APIs for data processing, compression, and querying. All APIs are accessible through Amazon API Gateway with proper authentication and are designed to integrate with AWS security features.

## Base URL

```
https://{api-id}.execute-api.{region}.amazonaws.com/{stage}
```

## Authentication

All API requests require AWS Identity and Access Management (IAM) authentication or API keys configured in Amazon API Gateway. This ensures secure access to the compression and query services.

## AWS Service Integration

The APIs integrate with the following AWS services:
- **Amazon Bedrock**: For foundation model-based compression
- **Amazon S3**: For data storage and retrieval
- **Amazon ElastiCache**: For caching compressed representations
- **AWS Lambda**: For serverless compute execution

## Customer Responsibilities

When using these APIs, customers are responsible for:
- Configuring appropriate IAM policies and access controls
- Managing API keys and authentication tokens securely
- Monitoring API usage and associated costs
- Implementing rate limiting and throttling as needed

## Endpoints

### 1. Query Processing

#### POST /query

Process a query using compressed knowledge representations.

**Request Body:**
```json
{
  "query": "What are the key financial trends in Q4?",
  "task_type": "financial-analysis",
  "compression_rate": "medium",
  "options": {
    "max_tokens": 1000,
    "temperature": 0.1
  }
}
```

**Parameters:**
- `query` (string, required): The question or query to process
- `task_type` (string, required): Type of task for context selection
- `compression_rate` (string, optional): Specific rate to use ("ultra", "high", "medium", "light")
- `options` (object, optional): Additional processing options

**Response:**
```json
{
  "query": "What are the key financial trends in Q4?",
  "response": "Based on the compressed financial data, Q4 shows...",
  "compression_rate_used": "medium",
  "task_type": "financial-analysis",
  "cache_info": {
    "compression_rate": "medium",
    "original_tokens": 50000,
    "compressed_tokens": 3125
  },
  "metadata": {
    "processing_time_ms": 245,
    "cache_hit": true,
    "model_used": "claude-3-sonnet"
  }
}
```

**Status Codes:**
- `200`: Success
- `400`: Bad request (invalid parameters)
- `404`: No compressed cache found for task type
- `500`: Internal server error

#### POST /query/batch

Process multiple queries efficiently.

**Request Body:**
```json
{
  "queries": [
    "What are the revenue trends?",
    "How did expenses change?",
    "What are the profit margins?"
  ],
  "task_type": "financial-analysis",
  "compression_rate": "high"
}
```

**Response:**
```json
{
  "results": [
    {
      "query": "What are the revenue trends?",
      "response": "Revenue increased by 15%...",
      "compression_rate_used": "high"
    },
    // ... more results
  ],
  "summary": {
    "total_queries": 3,
    "successful": 3,
    "failed": 0,
    "total_processing_time_ms": 680
  }
}
```

### 2. Data Processing

#### POST /process

Process and prepare data for compression.

**Request Body:**
```json
{
  "source_type": "s3",
  "source_location": "s3://my-bucket/financial-reports/",
  "task_type": "financial-analysis",
  "config": {
    "chunk_size": 256,
    "overlap": 50,
    "preprocessing_steps": ["clean_whitespace", "remove_special_chars"]
  }
}
```

**Parameters:**
- `source_type` (string, required): Type of data source ("s3", "kinesis")
- `source_location` (string, required): Location of source data
- `task_type` (string, required): Task type for processing
- `config` (object, optional): Processing configuration

**Response:**
```json
{
  "status": "success",
  "job_id": "proc-12345",
  "chunks_location": "s3://takc-processed-data/financial-analysis/",
  "chunk_count": 245,
  "task_type": "financial-analysis",
  "processing_time_ms": 15000
}
```

### 3. Compression Management

#### POST /compress

Create compressed representations for a task.

**Request Body:**
```json
{
  "task_type": "financial-analysis",
  "context_location": "s3://takc-processed-data/financial-analysis/",
  "compression_rates": ["ultra", "high", "medium", "light"],
  "task_description": "Analyze financial performance and trends"
}
```

**Response:**
```json
{
  "status": "success",
  "job_id": "comp-67890",
  "cache_keys": {
    "ultra": "financial-analysis:ultra",
    "high": "financial-analysis:high",
    "medium": "financial-analysis:medium",
    "light": "financial-analysis:light"
  },
  "compression_stats": {
    "ultra": {
      "original_tokens": 50000,
      "compressed_tokens": 781,
      "compression_ratio": 64
    }
    // ... more stats
  }
}
```

#### GET /compress/status/{job_id}

Check compression job status.

**Response:**
```json
{
  "job_id": "comp-67890",
  "status": "completed",
  "progress": 100,
  "started_at": "2025-01-16T10:00:00Z",
  "completed_at": "2025-01-16T10:05:30Z",
  "results": {
    "cache_keys_created": 4,
    "total_compression_time_ms": 330000
  }
}
```

### 4. Cache Management

#### GET /cache/{task_type}

List available caches for a task type.

**Response:**
```json
{
  "task_type": "financial-analysis",
  "available_rates": ["ultra", "high", "medium", "light"],
  "cache_info": {
    "ultra": {
      "created_at": "2025-01-16T10:05:30Z",
      "size_bytes": 1024000,
      "hit_count": 150,
      "last_accessed": "2025-01-16T14:30:00Z"
    }
    // ... more cache info
  }
}
```

#### DELETE /cache/{task_type}/{compression_rate}

Delete a specific compressed cache.

**Response:**
```json
{
  "status": "success",
  "message": "Cache deleted successfully",
  "cache_key": "financial-analysis:medium"
}
```

### 5. System Information

#### GET /health

System health check.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-16T15:00:00Z",
  "services": {
    "api_gateway": "healthy",
    "lambda_functions": "healthy",
    "elasticache": "healthy",
    "s3": "healthy"
  },
  "version": "1.0.0"
}
```

#### GET /metrics

System performance metrics.

**Response:**
```json
{
  "query_metrics": {
    "total_queries_24h": 1250,
    "avg_response_time_ms": 180,
    "cache_hit_rate": 0.85
  },
  "compression_metrics": {
    "total_compressions": 15,
    "avg_compression_time_ms": 45000,
    "storage_saved_gb": 12.5
  },
  "system_metrics": {
    "lambda_invocations": 2500,
    "s3_requests": 800,
    "cache_operations": 1500
  }
}
```

## Error Responses

All error responses follow this format:

```json
{
  "error": {
    "code": "INVALID_TASK_TYPE",
    "message": "Task type 'invalid-task' is not supported",
    "details": {
      "supported_task_types": ["financial-analysis", "legal-research", "technical-docs"]
    }
  },
  "request_id": "req-12345",
  "timestamp": "2025-01-16T15:00:00Z"
}
```

### Common Error Codes

- `INVALID_TASK_TYPE`: Unsupported task type
- `CACHE_NOT_FOUND`: No compressed cache available
- `COMPRESSION_FAILED`: Compression process failed
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `AUTHENTICATION_FAILED`: Invalid credentials
- `INTERNAL_ERROR`: System error

## Rate Limits

- **Query API**: 100 requests per minute per API key
- **Processing API**: 10 requests per minute per API key
- **Compression API**: 5 requests per minute per API key

## SDK Examples

### Python SDK

```python
import boto3
import json

class TAKCClient:
    def __init__(self, api_url, region='us-east-1'):
        self.api_url = api_url
        self.session = boto3.Session()
    
    def query(self, query, task_type, compression_rate=None):
        payload = {
            'query': query,
            'task_type': task_type
        }
        if compression_rate:
            payload['compression_rate'] = compression_rate
        
        # Implementation would use requests with AWS auth
        return self._make_request('POST', '/query', payload)
    
    def process_data(self, source_location, task_type, source_type='s3'):
        payload = {
            'source_type': source_type,
            'source_location': source_location,
            'task_type': task_type
        }
        return self._make_request('POST', '/process', payload)

# Usage
client = TAKCClient('https://api-id.execute-api.us-east-1.amazonaws.com/dev')
result = client.query("What are the key trends?", "financial-analysis")
```

### JavaScript SDK

```javascript
class TAKCClient {
    constructor(apiUrl, credentials) {
        this.apiUrl = apiUrl;
        this.credentials = credentials;
    }
    
    async query(query, taskType, compressionRate = null) {
        const payload = {
            query: query,
            task_type: taskType
        };
        
        if (compressionRate) {
            payload.compression_rate = compressionRate;
        }
        
        return await this.makeRequest('POST', '/query', payload);
    }
    
    async processData(sourceLocation, taskType, sourceType = 's3') {
        const payload = {
            source_type: sourceType,
            source_location: sourceLocation,
            task_type: taskType
        };
        
        return await this.makeRequest('POST', '/process', payload);
    }
}

// Usage
const client = new TAKCClient('https://api-id.execute-api.us-east-1.amazonaws.com/dev', credentials);
const result = await client.query("What are the key trends?", "financial-analysis");
```
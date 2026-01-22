#!/usr/bin/env python3
"""
Enhanced Query Client for TAKC System
Handles query processing with dynamic compression rate selection.
"""

import json
import boto3
import os
import re
from typing import Dict, Any, Optional
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

# Initialize Powertools
logger = Logger(service="query-processor")
tracer = Tracer(service="query-processor")
metrics = Metrics(namespace="TAKC", service="query-processor")


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext):
    """AWS Lambda handler for API Gateway integration"""
    try:
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        query = body.get('query')
        task_type = body.get('task_type')
        compression_rate = body.get('compression_rate')
        
        logger.info("Processing query request", extra={
            "task_type": task_type,
            "compression_rate": compression_rate,
            "query_length": len(query) if query else 0
        })
        
        if not query or not task_type:
            logger.warning("Missing required parameters")
            metrics.add_metric(name="ValidationErrors", unit=MetricUnit.Count, value=1)
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required parameters: query and task_type'
                })
            }
        
        # Process query
        result = process_query(query, task_type, compression_rate)
        
        # Add success metrics
        metrics.add_metric(name="SuccessfulQueries", unit=MetricUnit.Count, value=1)
        metrics.add_dimension(name="TaskType", value=task_type)
        metrics.add_dimension(name="CompressionRate", value=result.get('compression_rate_used', 'unknown'))
        
        logger.info("Query processed successfully", extra={
            "task_type": task_type,
            "compression_rate_used": result.get('compression_rate_used')
        })
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.exception("Error processing request", extra={"error": str(e)})
        metrics.add_metric(name="ProcessingErrors", unit=MetricUnit.Count, value=1)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }


@tracer.capture_method
def process_query(query: str, task_type: str, compression_rate: Optional[str] = None) -> Dict[str, Any]:
    """Process a query using TAKC with optimal compression rate"""
    
    # Determine compression rate if not specified
    if not compression_rate:
        query_complexity = _analyze_query_complexity(query)
        compression_rate = _select_compression_rate(query_complexity)
        logger.info("Auto-selected compression rate", extra={
            "query_complexity": query_complexity,
            "compression_rate": compression_rate
        })
    
    # Retrieve compressed cache
    compressed_cache = _retrieve_compressed_cache(task_type, compression_rate)
    
    if not compressed_cache:
        logger.warning("Cache not found", extra={
            "task_type": task_type,
            "compression_rate": compression_rate
        })
        metrics.add_metric(name="CacheMisses", unit=MetricUnit.Count, value=1)
        return {
            'query': query,
            'response': f"No compressed cache found for task_type: {task_type}, rate: {compression_rate}. Please run compression service first.",
            'compression_rate_used': compression_rate,
            'task_type': task_type,
            'error': 'cache_not_found'
        }
    
    metrics.add_metric(name="CacheHits", unit=MetricUnit.Count, value=1)
    
    # Process query with compressed context
    response = _generate_response(query, compressed_cache, compression_rate, task_type)
    
    return {
        'query': query,
        'response': response,
        'compression_rate_used': compression_rate,
        'task_type': task_type,
        'cache_info': compressed_cache.get('metadata', {})
    }


def _analyze_query_complexity(query: str) -> str:
    """Analyze query complexity"""
    query_lower = query.lower()
    
    # Simple heuristics for query complexity
    if any(word in query_lower for word in ['analyze', 'compare', 'evaluate', 'assess']):
        return 'high'
    elif any(word in query_lower for word in ['explain', 'describe', 'summarize']):
        return 'medium'
    else:
        return 'low'


def _recommend_compression_rate(task_type: str, data_size: int, query_complexity: str) -> str:
    """Recommend compression rate based on task and query"""
    if query_complexity == 'high':
        return 'light'
    elif query_complexity == 'medium':
        return 'medium'
    else:
        return 'high'


@tracer.capture_method
def _retrieve_compressed_cache(task_type: str, compression_rate: str) -> Optional[Dict[str, Any]]:
    """Retrieve compressed cache from Redis or S3"""
    try:
        # Try Redis first
        redis_endpoint = os.environ.get('REDIS_ENDPOINT')
        redis_port = int(os.environ.get('REDIS_PORT', 6379))
        
        if redis_endpoint:
            try:
                import redis
                r = redis.Redis(host=redis_endpoint, port=redis_port, decode_responses=True, socket_connect_timeout=2)
                cache_key = f"takc:{task_type}:{compression_rate}"
                cached_data = r.get(cache_key)
                
                if cached_data:
                    logger.info("Cache retrieved from Redis", extra={"cache_key": cache_key})
                    metrics.add_metric(name="RedisHits", unit=MetricUnit.Count, value=1)
                    return json.loads(cached_data)
            except Exception as e:
                logger.warning("Redis connection failed, falling back to S3", extra={"error": str(e)})
                metrics.add_metric(name="RedisMisses", unit=MetricUnit.Count, value=1)
        
        # Fallback to S3
        s3_client = boto3.client('s3')
        bucket = os.environ.get('S3_BUCKET')
        key = f"cache/v2/{task_type}/{compression_rate}/cache.json"
        
        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            logger.info("Cache retrieved from S3", extra={"bucket": bucket, "key": key})
            metrics.add_metric(name="S3Hits", unit=MetricUnit.Count, value=1)
            return json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            logger.error("S3 retrieval failed", extra={"error": str(e), "bucket": bucket, "key": key})
            metrics.add_metric(name="S3Misses", unit=MetricUnit.Count, value=1)
            return None
            
    except Exception as e:
        logger.exception("Cache retrieval error", extra={"error": str(e)})
        return None


def _analyze_query_complexity(query: str) -> str:
    """Analyze query complexity to determine appropriate compression rate"""
    query_lower = query.lower()
    
    # Simple queries - can use ultra compression
    simple_keywords = ['what', 'when', 'who', 'total', 'sum', 'revenue', 'profit']
    if any(keyword in query_lower for keyword in simple_keywords) and len(query.split()) < 10:
        return 'simple'
    
    # Complex queries - need lighter compression
    complex_keywords = ['analyze', 'compare', 'explain', 'why', 'how', 'relationship', 'trend']
    if any(keyword in query_lower for keyword in complex_keywords):
        return 'complex'
    
    return 'moderate'


def _select_compression_rate(complexity: str) -> str:
    """Select compression rate based on query complexity"""
    rate_map = {
        'simple': 'ultra',
        'moderate': 'high',
        'complex': 'medium'
    }
    return rate_map.get(complexity, 'high')


def _retrieve_compressed_cache(task_type: str, compression_rate: str) -> Optional[Dict[str, Any]]:
    """Retrieve compressed cache from S3"""
    try:
        s3_client = boto3.client('s3')
        bucket_name = os.environ.get('S3_BUCKET', 'takc-processed-data')
        key = f"cache/v2/{task_type}/{compression_rate}/cache.json"
        
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        cache_data = json.loads(response['Body'].read().decode('utf-8'))
        return cache_data
    except Exception as e:
        print(f"Error retrieving cache: {e}")
        return None


def _generate_response(query: str, compressed_cache: Dict[str, Any], 
                     compression_rate: str, task_type: str) -> str:
    """Generate response using Bedrock with compressed context"""
    
    # Get compressed context
    compressed_context = compressed_cache.get('compressed_kv', '')
    if not compressed_context:
        compressed_context = compressed_cache.get('compressed_context', '')
    
    # Construct prompt for Bedrock
    prompt = f"""You are an AI assistant with access to compressed knowledge about {task_type}.

Compressed Knowledge:
{compressed_context}

User Query: {query}

Instructions:
1. Answer the query using ONLY the information from the compressed knowledge above
2. Be concise and specific
3. If the information is not in the compressed knowledge, say "I don't have that information in the provided context"
4. Do not make up information

Answer:"""
    
    try:
        # Call Bedrock for inference
        bedrock_runtime = boto3.client('bedrock-runtime')
        model_id = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')
        
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'messages': [{
                    'role': 'user',
                    'content': prompt
                }],
                'max_tokens': 500,
                'temperature': 0.7
            })
        )
        
        result = json.loads(response['body'].read())
        answer = result['content'][0]['text']
        
        logger.info("Bedrock response generated", extra={
            "query": query,
            "compression_rate": compression_rate,
            "model_id": model_id
        })
        
        return answer
        
    except Exception as e:
        logger.error("Bedrock invocation failed", extra={"error": str(e)})
        # Fallback to simple context return
        return f"[Using {compression_rate} compression] Based on the compressed knowledge: {compressed_context[:300]}..."


if __name__ == '__main__':
    # Test locally
    test_event = {
        'body': json.dumps({
            'query': 'What was the total revenue?',
            'task_type': 'financial-analysis'
        })
    }
    print(json.dumps(lambda_handler(test_event, None), indent=2))
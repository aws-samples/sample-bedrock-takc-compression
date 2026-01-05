#!/usr/bin/env python3
"""
Amazon Bedrock-based Task-Aware Knowledge Compression Service
Implements KV cache compression using Amazon Bedrock foundation models as described in the whitepaper.

This service uses Amazon Bedrock to provide managed access to foundation models from leading AI companies
for task-aware knowledge compression. Amazon Bedrock is designed to help customers build and scale 
generative AI applications with security and privacy features.

Customer Responsibilities:
- Configure Amazon Bedrock model access permissions
- Implement appropriate access controls and user permissions
- Monitor token usage and costs
- Conduct regular security assessments
"""

import json
import boto3
import os
import time
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

# Initialize Powertools
logger = Logger(service="bedrock-compression")
tracer = Tracer(service="bedrock-compression")
metrics = Metrics(namespace="TAKC", service="bedrock-compression")


@dataclass
class CompressionConfig:
    compression_rate: str = "medium"  # ultra, high, medium, light
    task_description: str = ""
    few_shot_examples: Optional[str] = None
    max_tokens: int = 4096
    chunk_size: int = 512
    overlap_size: int = 64
    model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"


class BedrockCompressionService:
    """
    Compression service that uses Amazon Bedrock foundation models for 
    task-aware KV cache compression as described in the TAKC whitepaper.
    
    Amazon Bedrock provides managed access to foundation models from leading AI companies,
    designed to help customers build and scale generative AI applications with security
    and privacy features.
    
    Customer Responsibilities:
    - Ensure appropriate Amazon Bedrock model access permissions
    - Configure compression parameters for specific use cases
    - Monitor token usage and costs
    - Implement appropriate security controls
    """
    
    def __init__(self):
        self.compression_ratios = {
            "ultra": 64,    # 64× compression - reduces context by ~98.4%
            "high": 32,     # 32× compression - reduces context by ~96.9%
            "medium": 16,   # 16× compression - reduces context by ~93.8%
            "light": 8      # 8× compression - reduces context by ~87.5%
        }
        
        # Available Amazon Bedrock models
        self.available_models = {
            "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
            "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
            "claude-3-opus": "anthropic.claude-3-opus-20240229-v1:0",
            "llama2-13b": "meta.llama2-13b-chat-v1",
            "llama2-70b": "meta.llama2-70b-chat-v1",
            "titan-text": "amazon.titan-text-express-v1"
        }
        
        # Initialize AWS service clients
        self.bedrock_runtime = boto3.client('bedrock-runtime')  # Amazon Bedrock Runtime client
        self.s3_client = boto3.client('s3')  # Amazon S3 client
        self.redis_client = None  # Amazon ElastiCache Redis client (initialized if available)
        
        # Get environment variables for AWS service configuration
        self.s3_bucket = os.environ.get('S3_BUCKET', 'takc-processed-data-b39b0734')
        self.redis_endpoint = os.environ.get('REDIS_ENDPOINT', '')
        self.default_model = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')
        
        # Try to initialize Amazon ElastiCache Redis client if endpoint is available
        if self.redis_endpoint:
            try:
                import redis
                self.redis_client = redis.Redis(
                    host=self.redis_endpoint,
                    port=6379,
                    ssl=True,
                    decode_responses=True
                )
                logger.info("Redis client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis client: {e}")
    
    def _create_task_prompt(self, task_description: str, few_shot_examples: Optional[str] = None) -> str:
        """Create the task-aware prompt for compression"""
        prompt = f"""You are performing task-aware knowledge compression. Your goal is to compress the given context while preserving all information relevant to the specified task.

TASK: {task_description}

"""
        
        if few_shot_examples:
            prompt += f"""EXAMPLES:
{few_shot_examples}

"""
        
        prompt += """COMPRESSION INSTRUCTIONS:
1. Focus on key facts and relationships relevant to the task
2. Preserve important numerical data and metrics
3. Maintain critical entities and their attributes
4. Keep causal relationships and dependencies
5. Remove redundant or irrelevant information
6. Use concise language while maintaining accuracy

CONTEXT TO COMPRESS:
"""
        
        return prompt
    
    def _chunk_context(self, context: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
        """Split context into overlapping chunks for processing"""
        words = context.split()
        chunks = []
        
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk = ' '.join(words[start:end])
            chunks.append(chunk)
            
            if end >= len(words):
                break
                
            start = end - overlap
        
        logger.info(f"Split context into {len(chunks)} chunks")
        return chunks
    
    @tracer.capture_method
    def _invoke_bedrock_compression(self, prompt: str, context_chunk: str, 
                                  compression_ratio: int, model_id: str) -> str:
        """
        Invoke Amazon Bedrock model for KV cache compression with retry logic.
        
        Implements exponential backoff for handling rate limiting and transient errors
        when calling Amazon Bedrock APIs.
        """
        # Calculate target length based on compression ratio
        input_tokens = len(context_chunk.split())
        target_tokens = max(10, input_tokens // compression_ratio)
        
        # Prepare the full prompt
        full_prompt = f"""{prompt}
{context_chunk}

Please compress the above context to approximately {target_tokens} tokens while preserving all task-relevant information:"""
        
        # Retry configuration for handling rate limiting
        max_retries = 3
        base_delay = 1.0  # Base delay in seconds
        
        for attempt in range(max_retries + 1):
            try:
                # Prepare request based on Amazon Bedrock model type
                if "anthropic.claude" in model_id:
                    # Claude models via Amazon Bedrock
                    body = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": min(target_tokens + 100, 4096),
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "messages": [
                            {
                                "role": "user",
                                "content": full_prompt
                            }
                        ]
                    }
                elif "meta.llama" in model_id:
                    # Llama models via Amazon Bedrock
                    body = {
                        "prompt": full_prompt,
                        "max_gen_len": min(target_tokens + 100, 2048),
                        "temperature": 0.1,
                        "top_p": 0.9
                    }
                elif "amazon.titan" in model_id:
                    # Titan models
                    body = {
                        "inputText": full_prompt,
                        "textGenerationConfig": {
                            "maxTokenCount": min(target_tokens + 100, 4096),
                            "temperature": 0.1,
                            "topP": 0.9,
                            "stopSequences": []
                        }
                    }
                else:
                    raise ValueError(f"Unsupported model: {model_id}")
                
                # Invoke Amazon Bedrock Runtime API for model inference
                response = self.bedrock_runtime.invoke_model(
                    modelId=model_id,
                    contentType='application/json',
                    accept='application/json',
                    body=json.dumps(body)
                )
                
                # Parse response based on model type
                response_body = json.loads(response['body'].read())
                
                if "anthropic.claude" in model_id:
                    compressed_text = response_body['content'][0]['text'].strip()
                elif "meta.llama" in model_id:
                    compressed_text = response_body['generation'].strip()
                elif "amazon.titan" in model_id:
                    compressed_text = response_body['results'][0]['outputText'].strip()
                else:
                    compressed_text = str(response_body).strip()
                
                logger.debug(f"Compressed {input_tokens} tokens to {len(compressed_text.split())} tokens")
                return compressed_text
                
            except Exception as e:
                # Check if this is a rate limiting error
                error_message = str(e).lower()
                is_rate_limit = any(term in error_message for term in [
                    'throttling', 'rate limit', 'too many requests', 'quota exceeded'
                ])
                
                if is_rate_limit and attempt < max_retries:
                    # Exponential backoff for rate limiting
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Rate limiting detected, retrying in {delay} seconds (attempt {attempt + 1}/{max_retries + 1})")
                    time.sleep(delay)
                    continue
                else:
                    # Final attempt failed or non-rate-limit error
                    logger.error(f"Amazon Bedrock invocation failed after {attempt + 1} attempts: {e}")
                    return self._fallback_compression(context_chunk, compression_ratio)
    
    def _fallback_compression(self, context: str, compression_ratio: int) -> str:
        """Fallback compression method when Bedrock is not available"""
        logger.warning("Using fallback compression method")
        sentences = context.split('. ')
        target_sentences = max(1, len(sentences) // compression_ratio)
        
        # Simple scoring based on sentence length and position
        scored_sentences = []
        for i, sentence in enumerate(sentences):
            # Position score (beginning and end are important)
            pos_score = 1.0
            if i < len(sentences) * 0.3:
                pos_score = 1.5
            elif i > len(sentences) * 0.7:
                pos_score = 1.2
            
            # Length score (prefer medium-length sentences)
            length_score = min(2.0, len(sentence.split()) / 10)
            
            total_score = pos_score * length_score
            scored_sentences.append((sentence, total_score))
        
        # Sort by score and take top sentences
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        top_sentences = [s[0] for s in scored_sentences[:target_sentences]]
        
        # Restore original order
        result = []
        for sentence in sentences:
            if sentence in top_sentences:
                result.append(sentence)
        
        return '. '.join(result)
    
    @tracer.capture_method
    def _iterative_compression(self, chunks: List[str], task_prompt: str, 
                             compression_ratio: int, model_id: str) -> str:
        """Perform iterative compression as described in the whitepaper"""
        compressed_cache = ""
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            
            # Combine previous compressed cache with current chunk
            if compressed_cache:
                combined_context = f"{compressed_cache}\n\n{chunk}"
            else:
                combined_context = chunk
            
            # Compress the combined context with retry logic for rate limiting
            compressed_result = self._invoke_bedrock_compression(
                task_prompt, combined_context, compression_ratio, model_id
            )
            
            # Update the compressed cache
            compressed_cache = compressed_result
        
        return compressed_cache
    
    @tracer.capture_method
    def compress_context(self, context: str, config: CompressionConfig) -> Dict[str, Any]:
        """
        Perform task-aware KV cache compression using Amazon Bedrock foundation models.
        
        This method uses Amazon Bedrock to intelligently reduce context size while
        preserving task-relevant information. Amazon Bedrock provides managed access
        to foundation models from leading AI companies.
        
        Customer Responsibilities:
        - Ensure appropriate Amazon Bedrock model access permissions
        - Configure compression parameters for specific use cases
        - Monitor token usage and costs
        - Validate compression results for accuracy
        
        Args:
            context: Text content to compress
            config: Compression configuration including task description and rate
            
        Returns:
            Dict containing compressed content and metadata including:
            - compressed_kv: The compressed text content
            - compression_ratio: Actual compression ratio achieved
            - original_tokens: Number of tokens in original context
            - compressed_tokens: Number of tokens in compressed result
            
        Raises:
            ClientError: When Amazon Bedrock API calls fail
            ValueError: When compression parameters are invalid
        """
        compression_ratio = self.compression_ratios[config.compression_rate]
        
        # Create task-aware prompt
        task_prompt = self._create_task_prompt(
            config.task_description, 
            config.few_shot_examples
        )
        
        # Split context into chunks
        chunks = self._chunk_context(
            context, 
            config.chunk_size, 
            config.overlap_size
        )
        
        logger.info(f"Compressing {len(chunks)} chunks at {compression_ratio}× ratio using {config.model_id}")
        
        # Perform iterative compression
        compressed_kv = self._iterative_compression(chunks, task_prompt, compression_ratio, config.model_id)
        
        # Calculate compression statistics
        original_tokens = len(context.split())
        compressed_tokens = len(compressed_kv.split())
        actual_ratio = original_tokens / max(1, compressed_tokens)
        
        return {
            'compressed_kv': compressed_kv,
            'compression_rate': config.compression_rate,
            'original_tokens': original_tokens,
            'compressed_tokens': compressed_tokens,
            'compression_ratio': actual_ratio,
            'target_ratio': compression_ratio,
            'chunks_processed': len(chunks),
            'task_description': config.task_description,
            'model_used': config.model_id
        }
    
    @tracer.capture_method
    def create_multi_rate_cache(self, task_type: str, context: str, 
                               task_description: str = None,
                               few_shot_examples: str = None,
                               model_id: str = None) -> Dict[str, str]:
        """Create compressed caches at all compression rates"""
        if not task_description:
            task_description = f"Answer questions and perform analysis related to {task_type}"
        
        if not model_id:
            model_id = self.default_model
        
        cache_keys = {}
        compression_results = {}
        
        for rate in ["ultra", "high", "medium", "light"]:
            logger.info(f"Creating {rate} compression cache...")
            
            config = CompressionConfig(
                compression_rate=rate,
                task_description=task_description,
                few_shot_examples=few_shot_examples,
                chunk_size=512 if rate in ["ultra", "high"] else 1024,
                overlap_size=64 if rate in ["ultra", "high"] else 128,
                model_id=model_id
            )
            
            compressed_data = self.compress_context(context, config)
            cache_key = self.store_compressed_cache(task_type, rate, compressed_data)
            
            cache_keys[rate] = cache_key
            compression_results[rate] = {
                'ratio': compressed_data['compression_ratio'],
                'tokens': compressed_data['compressed_tokens']
            }
        
        # Print summary
        logger.info("Compression Summary:")
        for rate, result in compression_results.items():
            logger.info(f"  {rate:6}: {result['ratio']:.1f}× compression, {result['tokens']} tokens")
        
        return cache_keys
    
    @tracer.capture_method
    def store_compressed_cache(self, task_type: str, compression_rate: str, 
                             compressed_data: Dict[str, Any]) -> str:
        """Store compressed cache with enhanced metadata"""
        cache_key = f"takc:{task_type}:{compression_rate}"
        
        # Enhanced metadata
        metadata = {
            'compression_rate': compression_rate,
            'original_tokens': compressed_data['original_tokens'],
            'compressed_tokens': compressed_data['compressed_tokens'],
            'compression_ratio': compressed_data['compression_ratio'],
            'target_ratio': compressed_data['target_ratio'],
            'task_type': task_type,
            'task_description': compressed_data['task_description'],
            'chunks_processed': compressed_data['chunks_processed'],
            'model_used': compressed_data['model_used'],
            'timestamp': int(time.time()),
            'service': 'bedrock',
            'version': '2.0'
        }
        
        # Store in Redis if available
        if self.redis_client:
            try:
                self.redis_client.setex(
                    f"{cache_key}:metadata", 
                    86400,  # 24 hour expiry
                    json.dumps(metadata)
                )
                self.redis_client.setex(
                    f"{cache_key}:data", 
                    86400,  # 24 hour expiry
                    compressed_data['compressed_kv']
                )
                logger.info(f"Stored cache in Redis: {cache_key}")
            except Exception as e:
                logger.error(f"Failed to store in Redis: {e}")
        
        # Store in S3 as backup
        try:
            cache_data = {
                'compressed_kv': compressed_data['compressed_kv'],
                'metadata': metadata
            }
            
            s3_key = f"cache/v2/{task_type}/{compression_rate}/cache.json"
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(cache_data, indent=2).encode('utf-8'),
                ContentType='application/json'
            )
            logger.info(f"Stored cache in S3: s3://{self.s3_bucket}/{s3_key}")
        except Exception as e:
            logger.error(f"Failed to store in S3: {e}")
        
        return cache_key
    
    @tracer.capture_method
    def retrieve_compressed_cache(self, task_type: str, compression_rate: str) -> Optional[Dict[str, Any]]:
        """Retrieve compressed cache with fallback logic"""
        cache_key = f"takc:{task_type}:{compression_rate}"
        
        # Try Amazon ElastiCache Redis first for fast retrieval
        if self.redis_client:
            try:
                metadata = self.redis_client.get(f"{cache_key}:metadata")
                data = self.redis_client.get(f"{cache_key}:data")
                
                if metadata and data:
                    return {
                        'compressed_kv': data,
                        'metadata': json.loads(metadata)
                    }
            except Exception as e:
                logger.error(f"Redis retrieval failed: {e}")
        
        # Try Amazon S3 v2 format for persistent storage
        try:
            s3_key = f"cache/v2/{task_type}/{compression_rate}/cache.json"
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=s3_key
            )
            return json.loads(response['Body'].read().decode('utf-8'))
        except:
            pass
        
        # Try Amazon S3 v1 format (backward compatibility)
        try:
            s3_key = f"cache/{task_type}/{compression_rate}/cache.json"
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=s3_key
            )
            return json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            logger.error(f"Cache not found: {e}")
            return None
    
    def list_available_models(self) -> Dict[str, str]:
        """List available Bedrock models"""
        return self.available_models
    
    def test_model_access(self, model_id: str = None) -> bool:
        """Test if we can access a specific Bedrock model"""
        if not model_id:
            model_id = self.default_model
        
        try:
            test_prompt = "Hello, this is a test. Please respond with 'Test successful'."
            
            if "anthropic.claude" in model_id:
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": test_prompt}]
                }
            elif "meta.llama" in model_id:
                body = {
                    "prompt": test_prompt,
                    "max_gen_len": 10,
                    "temperature": 0.1
                }
            elif "amazon.titan" in model_id:
                body = {
                    "inputText": test_prompt,
                    "textGenerationConfig": {"maxTokenCount": 10}
                }
            else:
                return False
            
            response = self.bedrock_runtime.invoke_model(
                modelId=model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps(body)
            )
            
            logger.info(f"Successfully tested model: {model_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to test model {model_id}: {e}")
            return False


def lambda_handler(event, context):
    """AWS Lambda handler for S3-triggered compression"""
    try:
        # Extract parameters from event (sent by data_processor Lambda)
        task_type = event.get('task_type')
        chunks_location = event.get('chunks_location')
        chunk_count = event.get('chunk_count')
        
        if not task_type or not chunks_location:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameters'})
            }
        
        logger.info(f"Starting compression for task_type: {task_type}")
        
        # Read all chunks from S3
        service = BedrockCompressionService()
        bucket, key_prefix = chunks_location[5:].split('/', 1)
        
        # Combine all chunks into single context
        chunks = []
        for i in range(chunk_count):
            chunk_key = f"{key_prefix}/chunk_{i:04d}.txt"
            response = service.s3_client.get_object(Bucket=bucket, Key=chunk_key)
            chunks.append(response['Body'].read().decode('utf-8'))
        
        context = '\n\n'.join(chunks)
        
        # Create multi-rate compressed caches
        task_description = f"Answer questions and perform analysis related to {task_type}"
        cache_keys = service.create_multi_rate_cache(
            task_type=task_type,
            context=context,
            task_description=task_description
        )
        
        logger.info(f"Compression complete for {task_type}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'success',
                'task_type': task_type,
                'cache_keys': cache_keys
            })
        }
        
    except Exception as e:
        logger.error(f"Compression failed: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Bedrock-powered TAKC compression')
    parser.add_argument('--task-type', help='Task type for compression')
    parser.add_argument('--context-file', help='File containing context to compress')
    parser.add_argument('--task-description', help='Detailed task description')
    parser.add_argument('--few-shot-examples', help='Few-shot examples for the task')
    parser.add_argument('--model-id', help='Bedrock model ID to use')
    parser.add_argument('--compression-rates', nargs='+', 
                       choices=['ultra', 'high', 'medium', 'light'],
                       default=['medium'], help='Compression rates to generate')
    parser.add_argument('--test-models', action='store_true', help='Test available models')
    
    args = parser.parse_args()
    
    service = BedrockCompressionService()
    
    if args.test_models:
        print("Testing available Bedrock models:")
        for name, model_id in service.list_available_models().items():
            success = service.test_model_access(model_id)
            status = "✅" if success else "❌"
            print(f"  {status} {name}: {model_id}")
        return
    
    # Require task-type and context-file for compression operations
    if not args.task_type or not args.context_file:
        parser.error("--task-type and --context-file are required for compression operations")
    
    # Read context from file
    with open(args.context_file, 'r') as f:
        context = f.read()
    
    if len(args.compression_rates) == 1:
        # Single rate compression
        config = CompressionConfig(
            compression_rate=args.compression_rates[0],
            task_description=args.task_description or f"Process queries related to {args.task_type}",
            few_shot_examples=args.few_shot_examples,
            model_id=args.model_id or service.default_model
        )
        
        result = service.compress_context(context, config)
        cache_key = service.store_compressed_cache(args.task_type, args.compression_rates[0], result)
        print(f"Created cache: {cache_key}")
        print(f"Compression: {result['compression_ratio']:.1f}× ({result['original_tokens']} → {result['compressed_tokens']} tokens)")
    else:
        # Multi-rate compression
        cache_keys = service.create_multi_rate_cache(
            task_type=args.task_type,
            context=context,
            task_description=args.task_description,
            few_shot_examples=args.few_shot_examples,
            model_id=args.model_id
        )
        
        print("Created compressed caches:")
        for rate, key in cache_keys.items():
            print(f"  {rate}: {key}")


if __name__ == '__main__':
    main()

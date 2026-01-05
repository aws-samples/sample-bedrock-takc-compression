#!/usr/bin/env python3
"""
Task-Aware Knowledge Compression Service
Handles compression of knowledge at multiple rates for efficient reasoning.
"""

import json
import boto3
import os
import hashlib
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

# Initialize Powertools
logger = Logger(service="compression-service")
tracer = Tracer(service="compression-service")
metrics = Metrics(namespace="TAKC", service="compression-service")


@dataclass
class CompressionConfig:
    compression_rate: str = "medium"  # ultra, high, medium, light
    task_description: str = ""
    few_shot_examples: Optional[str] = None
    max_tokens: int = 4096


class CompressionService:
    def __init__(self):
        self.compression_ratios = {
            "ultra": 0.015625,  # 64× compression
            "high": 0.03125,    # 32× compression
            "medium": 0.0625,   # 16× compression
            "light": 0.125      # 8× compression
        }
        
        # Initialize AWS clients
        self.s3_client = boto3.client('s3')
        self.redis_client = None
        
        # Get environment variables
        self.s3_bucket = os.environ.get('S3_BUCKET', 'takc-processed-data-b39b0734')
        self.redis_endpoint = os.environ.get('REDIS_ENDPOINT', '')
        
        # Try to initialize Redis client if endpoint is available
        if self.redis_endpoint:
            try:
                import redis
                self.redis_client = redis.Redis(
                    host=self.redis_endpoint,
                    port=6379,
                    ssl=True,
                    decode_responses=True
                )
            except Exception as e:
                print(f"Failed to initialize Redis client: {e}")
    
    def recommend_compression_rate(self, task_type: str, data_size: int, 
                                 query_complexity: str) -> str:
        """Recommend optimal compression rate based on task characteristics"""
        if query_complexity == "simple" and data_size < 50000:
            return "ultra"  # 64× compression
        elif query_complexity == "moderate" or (query_complexity == "simple" and data_size >= 50000):
            return "high"   # 32× compression
        elif query_complexity == "complex" and data_size < 100000:
            return "medium" # 16× compression
        else:
            return "light"  # 8× compression
    
    def analyze_query_complexity(self, query: str) -> str:
        """Analyze query to determine its complexity level"""
        complexity_indicators = ["compare", "synthesize", "across", "relationship", "between"]
        
        if any(indicator in query.lower() for indicator in complexity_indicators):
            return "complex"
        elif len(query.split()) > 15:
            return "moderate"
        else:
            return "simple"
    
    def _extract_key_sentences(self, text: str, ratio: float) -> str:
        """Extract key sentences based on importance scoring"""
        # Split text into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Calculate number of sentences to keep
        num_to_keep = max(1, int(len(sentences) * ratio))
        
        # Score sentences based on simple heuristics
        scored_sentences = []
        for i, sentence in enumerate(sentences):
            # Score based on position (beginning and end sentences are important)
            position_score = 1.0
            if i < len(sentences) * 0.2:  # First 20%
                position_score = 1.5
            elif i > len(sentences) * 0.8:  # Last 20%
                position_score = 1.2
                
            # Score based on presence of key terms
            key_terms = ["revenue", "profit", "sales", "growth", "increase", "decrease", 
                        "million", "billion", "percent", "market", "customer", "product"]
            term_score = sum(1 for term in key_terms if term.lower() in sentence.lower()) * 0.5
            
            # Score based on sentence length (prefer medium length sentences)
            words = sentence.split()
            length = len(words)
            length_score = 1.0
            if 5 <= length <= 25:
                length_score = 1.2
            elif length > 40:
                length_score = 0.7
                
            # Calculate final score
            final_score = position_score + term_score + length_score
            scored_sentences.append((sentence, final_score))
        
        # Sort sentences by score and keep top ones
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        top_sentences = [s[0] for s in scored_sentences[:num_to_keep]]
        
        # Restore original order
        ordered_top_sentences = [s for s in sentences if s in top_sentences]
        
        return ' '.join(ordered_top_sentences)
    
    def _task_aware_filtering(self, text: str, task_description: str, ratio: float) -> str:
        """Filter content based on task relevance"""
        # Extract key terms from task description
        task_terms = set(task_description.lower().split())
        
        # Split text into paragraphs
        paragraphs = text.split('\n\n')
        
        # Score paragraphs based on relevance to task
        scored_paragraphs = []
        for para in paragraphs:
            if not para.strip():
                continue
                
            # Count task-related terms
            para_terms = set(para.lower().split())
            term_overlap = len(task_terms.intersection(para_terms))
            
            # Calculate relevance score
            relevance_score = term_overlap / max(1, len(task_terms)) * 10
            
            # Add paragraph length factor (prefer medium-length paragraphs)
            length = len(para.split())
            length_factor = 1.0
            if length < 10:
                length_factor = 0.7
            elif length > 100:
                length_factor = 0.8
                
            final_score = relevance_score * length_factor
            scored_paragraphs.append((para, final_score))
        
        # Sort by relevance score and keep top paragraphs
        scored_paragraphs.sort(key=lambda x: x[1], reverse=True)
        num_to_keep = max(1, int(len(paragraphs) * ratio))
        compressed_text = '\n\n'.join(p[0] for p in scored_paragraphs[:num_to_keep])
        
        return compressed_text
    
    @tracer.capture_method
    def compress_context(self, context: str, config: CompressionConfig) -> Dict[str, Any]:
        """Perform task-aware compression of the context"""
        ratio = self.compression_ratios[config.compression_rate]
        
        # Apply task-aware filtering
        filtered_text = self._task_aware_filtering(context, config.task_description, ratio * 2)
        
        # Apply sentence extraction on the filtered text
        compressed_text = self._extract_key_sentences(filtered_text, ratio * 2)
        
        # Calculate compression statistics
        original_tokens = len(context.split())
        compressed_tokens = len(compressed_text.split())
        
        return {
            'compressed_kv': compressed_text,
            'compression_rate': config.compression_rate,
            'original_tokens': original_tokens,
            'compressed_tokens': compressed_tokens,
            'compression_ratio': original_tokens / max(1, compressed_tokens)
        }
    
    def _get_cache_key(self, task_type: str, compression_rate: str) -> str:
        """Generate a consistent cache key"""
        return f"takc:{task_type}:{compression_rate}"
    
    @tracer.capture_method
    def store_compressed_cache(self, task_type: str, compression_rate: str, 
                             compressed_data: Dict[str, Any]) -> str:
        """Store compressed cache in Redis/S3"""
        cache_key = self._get_cache_key(task_type, compression_rate)
        
        # Store metadata
        metadata = {
            'compression_rate': compression_rate,
            'original_tokens': compressed_data['original_tokens'],
            'compressed_tokens': compressed_data['compressed_tokens'],
            'compression_ratio': compressed_data['compression_ratio'],
            'task_type': task_type,
            'timestamp': str(boto3.client('sts').get_caller_identity().get('Account'))
        }
        
        # Try to store in Redis if available
        if self.redis_client:
            try:
                self.redis_client.set(f"{cache_key}:metadata", json.dumps(metadata))
                self.redis_client.set(f"{cache_key}:data", compressed_data['compressed_kv'])
                print(f"Stored cache in Redis with key: {cache_key}")
            except Exception as e:
                print(f"Failed to store in Redis: {e}")
        
        # Always store in S3 as backup
        try:
            cache_data = {
                'compressed_kv': compressed_data['compressed_kv'],
                'metadata': metadata
            }
            
            s3_key = f"cache/{task_type}/{compression_rate}/cache.json"
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(cache_data).encode('utf-8')
            )
            print(f"Stored cache in S3: s3://{self.s3_bucket}/{s3_key}")
        except Exception as e:
            print(f"Failed to store in S3: {e}")
        
        return cache_key
    
    @tracer.capture_method
    def retrieve_compressed_cache(self, task_type: str, compression_rate: str) -> Optional[Dict[str, Any]]:
        """Retrieve compressed cache from storage"""
        cache_key = self._get_cache_key(task_type, compression_rate)
        
        # Try to get from Redis first if available
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
                print(f"Failed to retrieve from Redis: {e}")
        
        # Fall back to S3
        try:
            s3_key = f"cache/{task_type}/{compression_rate}/cache.json"
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key=s3_key
            )
            
            cache_data = json.loads(response['Body'].read().decode('utf-8'))
            return cache_data
        except Exception as e:
            print(f"Failed to retrieve from S3: {e}")
            
            # If no cache exists, try to create one from available data
            try:
                # Look for raw data in S3
                data_key = f"{task_type}/test-data.txt"
                response = self.s3_client.get_object(
                    Bucket=self.s3_bucket,
                    Key=data_key
                )
                
                context = response['Body'].read().decode('utf-8')
                config = CompressionConfig(
                    compression_rate=compression_rate,
                    task_description=f"Process queries related to {task_type}"
                )
                
                compressed_data = self.compress_context(context, config)
                self.store_compressed_cache(task_type, compression_rate, compressed_data)
                
                return {
                    'compressed_kv': compressed_data['compressed_kv'],
                    'metadata': {
                        'compression_rate': compression_rate,
                        'original_tokens': compressed_data['original_tokens'],
                        'compressed_tokens': compressed_data['compressed_tokens'],
                        'task_type': task_type,
                        'auto_generated': True
                    }
                }
            except Exception as auto_e:
                print(f"Failed to auto-generate cache: {auto_e}")
                return None
    
    def create_compressed_cache(self, task_type: str, context: str, 
                              compression_rates: List[str] = None) -> Dict[str, str]:
        """Create compressed caches at multiple rates"""
        if compression_rates is None:
            compression_rates = ["ultra", "high", "medium", "light"]
        
        cache_keys = {}
        
        for rate in compression_rates:
            config = CompressionConfig(
                compression_rate=rate,
                task_description=f"Process queries related to {task_type}"
            )
            
            compressed_data = self.compress_context(context, config)
            cache_key = self.store_compressed_cache(task_type, rate, compressed_data)
            cache_keys[rate] = cache_key
        
        return cache_keys


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Compress knowledge for TAKC')
    parser.add_argument('--task-type', required=True, help='Task type for compression')
    parser.add_argument('--context-file', required=True, help='File containing context to compress')
    parser.add_argument('--compression-rates', nargs='+', 
                       choices=['ultra', 'high', 'medium', 'light'],
                       default=['medium'], help='Compression rates to generate')
    
    args = parser.parse_args()
    
    # Read context from file
    with open(args.context_file, 'r') as f:
        context = f.read()
    
    service = CompressionService()
    cache_keys = service.create_compressed_cache(
        task_type=args.task_type,
        context=context,
        compression_rates=args.compression_rates
    )
    
    print("Created compressed caches:")
    for rate, key in cache_keys.items():
        print(f"  {rate}: {key}")


if __name__ == '__main__':
    main()
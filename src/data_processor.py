#!/usr/bin/env python3
"""
Data Processing Pipeline for TAKC
Handles data ingestion from various sources and prepares it for compression.
"""

import json
import boto3
import argparse
import os
from typing import Dict, List, Any
from dataclasses import dataclass
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

# Initialize Powertools
logger = Logger(service="data-processor")
tracer = Tracer(service="data-processor")
metrics = Metrics(namespace="TAKC", service="data-processor")


@dataclass
class ProcessingConfig:
    chunk_size: int = 256
    overlap: int = 50
    preprocessing_steps: List[str] = None


class DataProcessor:
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.kinesis_client = boto3.client('kinesis')
        self.lambda_client = boto3.client('lambda')
    
    @tracer.capture_method
    def read_from_s3(self, bucket: str, key: str) -> str:
        """Read data from S3 bucket"""
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read().decode('utf-8')
        except Exception as e:
            raise Exception(f"Failed to read from S3: {e}")
    
    def read_from_kinesis(self, stream_name: str, shard_id: str = None) -> List[str]:
        """Read data from Kinesis stream"""
        try:
            if shard_id:
                response = self.kinesis_client.get_shard_iterator(
                    StreamName=stream_name,
                    ShardId=shard_id,
                    ShardIteratorType='LATEST'
                )
                shard_iterator = response['ShardIterator']
                
                records_response = self.kinesis_client.get_records(
                    ShardIterator=shard_iterator
                )
                return [record['Data'].decode('utf-8') for record in records_response['Records']]
            else:
                # Get all shards
                stream_desc = self.kinesis_client.describe_stream(StreamName=stream_name)
                shards = stream_desc['StreamDescription']['Shards']
                all_records = []
                
                for shard in shards:
                    records = self.read_from_kinesis(stream_name, shard['ShardId'])
                    all_records.extend(records)
                
                return all_records
        except Exception as e:
            raise Exception(f"Failed to read from Kinesis: {e}")
    
    def preprocess_data(self, data: str, config: ProcessingConfig) -> str:
        """Apply preprocessing steps to raw data"""
        processed = data
        
        if config.preprocessing_steps:
            for step in config.preprocessing_steps:
                if step == 'clean_whitespace':
                    processed = ' '.join(processed.split())
                elif step == 'remove_special_chars':
                    processed = ''.join(c for c in processed if c.isalnum() or c.isspace())
                elif step == 'lowercase':
                    processed = processed.lower()
        
        return processed
    
    def chunk_data(self, data: str, chunk_size: int, overlap: int = 0) -> List[str]:
        """Split data into overlapping chunks"""
        words = data.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk = ' '.join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        
        return chunks
    
    @tracer.capture_method
    def store_chunks(self, chunks: List[str], output_location: str) -> None:
        """Store processed chunks to S3"""
        if output_location.startswith('s3://'):
            bucket, key_prefix = output_location[5:].split('/', 1)
            
            for i, chunk in enumerate(chunks):
                key = f"{key_prefix}/chunk_{i:04d}.txt"
                self.s3_client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=chunk.encode('utf-8')
                )
    
    @tracer.capture_method
    def process_data(self, source_type: str, source_location: str, 
                    task_type: str, config: ProcessingConfig = None) -> Dict[str, Any]:
        """Main processing function"""
        if config is None:
            config = ProcessingConfig()
        
        # Read data based on source type
        if source_type == 's3':
            bucket, key = source_location[5:].split('/', 1)
            data = self.read_from_s3(bucket, key)
        elif source_type == 'kinesis':
            data = '\n'.join(self.read_from_kinesis(source_location))
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
        
        # Process and chunk data
        processed_data = self.preprocess_data(data, config)
        chunks = self.chunk_data(processed_data, config.chunk_size, config.overlap)
        
        # Store processed chunks - use environment variable for bucket name
        bucket_name = os.environ.get('S3_BUCKET', 'takc-processed-data')
        output_location = f"s3://{bucket_name}/{task_type}/"
        self.store_chunks(chunks, output_location)
        
        return {
            'status': 'success',
            'chunks_location': output_location,
            'chunk_count': len(chunks),
            'task_type': task_type
        }


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext):
    """AWS Lambda handler for S3-triggered data processing"""
    try:
        # Handle S3 event notification
        if 'Records' in event:
            for record in event['Records']:
                # Extract S3 bucket and key from event
                bucket = record['s3']['bucket']['name']
                key = record['s3']['object']['key']
                
                logger.info("Processing S3 event", extra={
                    "bucket": bucket,
                    "key": key
                })
                
                # Process the uploaded file
                source_location = f"s3://{bucket}/{key}"
                
                # Extract task_type from S3 key path (e.g., raw-data/financial/file.txt)
                task_type = key.split('/')[1] if '/' in key else 'default'
                
                # Create processing config
                config = ProcessingConfig(
                    chunk_size=256,
                    overlap=50,
                    preprocessing_steps=['clean_whitespace']
                )
                
                processor = DataProcessor()
                result = processor.process_data('s3', source_location, task_type, config)
                
                logger.info("Data processing completed", extra={
                    "task_type": task_type,
                    "chunk_count": result['chunk_count']
                })
                metrics.add_metric(name="ChunksCreated", unit=MetricUnit.Count, value=result['chunk_count'])
                metrics.add_dimension(name="TaskType", value=task_type)
                
                # Invoke compression Lambda after successful processing
                lambda_client = boto3.client('lambda')
                compression_payload = {
                    'task_type': task_type,
                    'chunks_location': result['chunks_location'],
                    'chunk_count': result['chunk_count']
                }
                
                lambda_client.invoke(
                    FunctionName=os.environ.get('COMPRESSION_LAMBDA_NAME'),
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps(compression_payload)
                )
                
                logger.info("Triggered compression Lambda", extra={"task_type": task_type})
                metrics.add_metric(name="CompressionTriggered", unit=MetricUnit.Count, value=1)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'success'})
        }
        
    except Exception as e:
        print(f"Processing failed: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def main():
    parser = argparse.ArgumentParser(description='Process data for TAKC compression')
    parser.add_argument('--source', required=True, help='Data source location')
    parser.add_argument('--source-type', default='s3', choices=['s3', 'kinesis'], 
                       help='Type of data source')
    parser.add_argument('--task-type', required=True, help='Task type for compression')
    parser.add_argument('--chunk-size', type=int, default=256, help='Chunk size for processing')
    
    args = parser.parse_args()
    
    processor = DataProcessor()
    config = ProcessingConfig(chunk_size=args.chunk_size)
    
    result = processor.process_data(
        source_type=args.source_type,
        source_location=args.source,
        task_type=args.task_type,
        config=config
    )
    
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
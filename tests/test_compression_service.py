#!/usr/bin/env python3
"""
Unit tests for the compression service
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from compression_service import CompressionService, CompressionConfig


class TestCompressionService(unittest.TestCase):
    """Test cases for CompressionService"""

    def setUp(self):
        """Set up test fixtures"""
        self.service = CompressionService()
        self.test_context = """
        Financial Performance Report Q4 2024

        Executive Summary:
        Our company achieved record-breaking financial performance in Q4 2024, with total revenue 
        reaching $125 million, representing a 23% increase compared to Q4 2023. Net profit margins 
        improved to 18.5%, up from 15.2% in the previous year.

        Revenue Analysis:
        - Product Sales: $85 million (68% of total revenue)
        - Service Revenue: $25 million (20% of total revenue)
        - Licensing: $15 million (12% of total revenue)
        """

    def test_analyze_query_complexity(self):
        """Test query complexity analysis"""
        # Test simple query
        self.assertEqual(
            self.service.analyze_query_complexity("What was the revenue?"),
            "simple"
        )
        
        # Test moderate query
        self.assertEqual(
            self.service.analyze_query_complexity("Can you provide a detailed breakdown of the financial performance for the last quarter?"),
            "moderate"
        )
        
        # Test complex query
        self.assertEqual(
            self.service.analyze_query_complexity("Compare the relationship between revenue growth and market expansion across different regions"),
            "complex"
        )

    def test_recommend_compression_rate(self):
        """Test compression rate recommendation"""
        # Test ultra compression
        self.assertEqual(
            self.service.recommend_compression_rate("financial", 10000, "simple"),
            "ultra"
        )
        
        # Test high compression
        self.assertEqual(
            self.service.recommend_compression_rate("financial", 60000, "simple"),
            "high"
        )
        
        # Test medium compression
        self.assertEqual(
            self.service.recommend_compression_rate("financial", 50000, "complex"),
            "medium"
        )
        
        # Test light compression
        self.assertEqual(
            self.service.recommend_compression_rate("financial", 150000, "complex"),
            "light"
        )

    def test_compress_context(self):
        """Test context compression"""
        config = CompressionConfig(
            compression_rate="medium",
            task_description="Analyze financial performance"
        )
        
        result = self.service.compress_context(self.test_context, config)
        
        # Check that result contains expected keys
        self.assertIn('compressed_kv', result)
        self.assertIn('compression_rate', result)
        self.assertIn('original_tokens', result)
        self.assertIn('compressed_tokens', result)
        
        # Check compression rate
        self.assertEqual(result['compression_rate'], "medium")
        
        # Check that compression actually happened
        self.assertLess(result['compressed_tokens'], result['original_tokens'])

    @patch('boto3.client')
    def test_store_compressed_cache(self, mock_boto3_client):
        """Test storing compressed cache"""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        
        compressed_data = {
            'compressed_kv': 'Test compressed data',
            'compression_rate': 'medium',
            'original_tokens': 100,
            'compressed_tokens': 20,
            'compression_ratio': 5.0
        }
        
        cache_key = self.service.store_compressed_cache(
            task_type="financial",
            compression_rate="medium",
            compressed_data=compressed_data
        )
        
        # Check that cache key is correct format
        self.assertEqual(cache_key, "takc:financial:medium")
        
        # Check that S3 put_object was called
        mock_s3.put_object.assert_called_once()


if __name__ == '__main__':
    unittest.main()
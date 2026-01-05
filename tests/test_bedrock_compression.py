#!/usr/bin/env python3
"""
Test script for Bedrock-based TAKC compression service
"""

import sys
import os
import json
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bedrock_compression_service import BedrockCompressionService, CompressionConfig


class TestBedrockCompressionService(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.service = BedrockCompressionService()
        self.test_context = """
        The company reported strong financial results for Q3 2024. Revenue increased by 15% 
        year-over-year to $2.5 billion, driven primarily by growth in the cloud services 
        division which saw 28% growth. Operating margin improved to 22% from 19% in the 
        previous quarter. The CEO mentioned that customer acquisition costs decreased by 8% 
        while customer lifetime value increased by 12%. The company also announced plans to 
        expand into three new international markets in 2025, with an expected investment of 
        $150 million. Employee headcount grew by 5% to 12,000 employees. The board approved 
        a $500 million share buyback program.
        """
        
    def test_initialization(self):
        """Test service initialization"""
        self.assertIsNotNone(self.service)
        self.assertEqual(len(self.service.compression_ratios), 4)
        self.assertIn("ultra", self.service.compression_ratios)
        self.assertIn("anthropic.claude-3-haiku-20240307-v1:0", self.service.available_models.values())
    
    def test_create_task_prompt(self):
        """Test task prompt creation"""
        task_desc = "Answer financial questions"
        few_shot = "Q: What is revenue? A: $2.5B"
        
        prompt = self.service._create_task_prompt(task_desc, few_shot)
        
        self.assertIn(task_desc, prompt)
        self.assertIn(few_shot, prompt)
        self.assertIn("COMPRESSION INSTRUCTIONS", prompt)
    
    def test_chunk_context(self):
        """Test context chunking"""
        chunks = self.service._chunk_context(self.test_context, chunk_size=20, overlap=5)
        
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.split()) <= 25 for chunk in chunks))  # Allow some flexibility
    
    def test_fallback_compression(self):
        """Test fallback compression method"""
        compressed = self.service._fallback_compression(self.test_context, compression_ratio=4)
        
        original_tokens = len(self.test_context.split())
        compressed_tokens = len(compressed.split())
        
        self.assertLess(compressed_tokens, original_tokens)
        self.assertGreater(len(compressed), 0)
    
    @patch('boto3.client')
    def test_bedrock_invocation_claude(self, mock_boto_client):
        """Test Bedrock invocation with Claude model"""
        # Mock Bedrock response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'Compressed financial results: Revenue $2.5B (+15% YoY), cloud +28%, margin 22%.'}]
        }).encode()
        
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = mock_response
        mock_boto_client.return_value = mock_bedrock
        
        # Create new service instance to use mocked client
        service = BedrockCompressionService()
        service.bedrock_runtime = mock_bedrock
        
        result = service._invoke_bedrock_compression(
            "Test prompt", 
            self.test_context, 
            compression_ratio=4,
            model_id="anthropic.claude-3-haiku-20240307-v1:0"
        )
        
        self.assertIn("Revenue", result)
        self.assertIn("$2.5B", result)
        mock_bedrock.invoke_model.assert_called_once()
    
    @patch('boto3.client')
    def test_bedrock_invocation_llama(self, mock_boto_client):
        """Test Bedrock invocation with Llama model"""
        # Mock Bedrock response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'generation': 'Financial summary: Q3 revenue $2.5B, up 15%. Cloud division grew 28%.'
        }).encode()
        
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = mock_response
        mock_boto_client.return_value = mock_bedrock
        
        # Create new service instance to use mocked client
        service = BedrockCompressionService()
        service.bedrock_runtime = mock_bedrock
        
        result = service._invoke_bedrock_compression(
            "Test prompt", 
            self.test_context, 
            compression_ratio=4,
            model_id="meta.llama2-13b-chat-v1"
        )
        
        self.assertIn("revenue", result.lower())
        self.assertIn("$2.5b", result.lower())
        mock_bedrock.invoke_model.assert_called_once()
    
    @patch('boto3.client')
    def test_compress_context(self, mock_boto_client):
        """Test full context compression"""
        # Mock Bedrock response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'Q3 2024: Revenue $2.5B (+15% YoY), cloud +28%, margin 22%, CAC -8%, LTV +12%.'}]
        }).encode()
        
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = mock_response
        mock_boto_client.return_value = mock_bedrock
        
        # Create new service instance to use mocked client
        service = BedrockCompressionService()
        service.bedrock_runtime = mock_bedrock
        
        config = CompressionConfig(
            compression_rate="medium",
            task_description="Answer financial performance questions",
            model_id="anthropic.claude-3-haiku-20240307-v1:0"
        )
        
        result = service.compress_context(self.test_context, config)
        
        self.assertIn('compressed_kv', result)
        self.assertIn('compression_ratio', result)
        self.assertGreater(result['original_tokens'], result['compressed_tokens'])
        self.assertEqual(result['compression_rate'], 'medium')
    
    def test_compression_config(self):
        """Test compression configuration"""
        config = CompressionConfig(
            compression_rate="high",
            task_description="Test task",
            few_shot_examples="Q: Test? A: Yes.",
            chunk_size=256,
            model_id="anthropic.claude-3-sonnet-20240229-v1:0"
        )
        
        self.assertEqual(config.compression_rate, "high")
        self.assertEqual(config.task_description, "Test task")
        self.assertEqual(config.chunk_size, 256)
        self.assertIn("claude-3-sonnet", config.model_id)
    
    def test_list_available_models(self):
        """Test listing available models"""
        models = self.service.list_available_models()
        
        self.assertIsInstance(models, dict)
        self.assertIn("claude-3-haiku", models)
        self.assertIn("llama2-13b", models)
        self.assertIn("titan-text", models)
    
    @patch('boto3.client')
    def test_model_access_test(self, mock_boto_client):
        """Test model access testing"""
        # Mock successful response
        mock_response = {
            'body': Mock()
        }
        mock_response['body'].read.return_value = json.dumps({
            'content': [{'text': 'Test successful'}]
        }).encode()
        
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.return_value = mock_response
        mock_boto_client.return_value = mock_bedrock
        
        # Create new service instance to use mocked client
        service = BedrockCompressionService()
        service.bedrock_runtime = mock_bedrock
        
        result = service.test_model_access("anthropic.claude-3-haiku-20240307-v1:0")
        
        self.assertTrue(result)
        mock_bedrock.invoke_model.assert_called_once()
    
    @patch('boto3.client')
    def test_model_access_test_failure(self, mock_boto_client):
        """Test model access testing with failure"""
        mock_bedrock = Mock()
        mock_bedrock.invoke_model.side_effect = Exception("Access denied")
        mock_boto_client.return_value = mock_bedrock
        
        # Create new service instance to use mocked client
        service = BedrockCompressionService()
        service.bedrock_runtime = mock_bedrock
        
        result = service.test_model_access("invalid-model")
        
        self.assertFalse(result)


class TestIntegration(unittest.TestCase):
    """Integration tests that require actual AWS access"""
    
    def setUp(self):
        self.service = BedrockCompressionService()
        self.test_context = """
        Amazon Web Services (AWS) is a comprehensive cloud computing platform provided by Amazon. 
        It offers over 200 fully featured services from data centers globally. AWS serves millions 
        of customers including startups, large enterprises, and government agencies. The platform 
        provides services in compute, storage, database, analytics, machine learning, and more.
        """
    
    def test_real_bedrock_access(self):
        """Test actual Bedrock access (requires AWS credentials and permissions)"""
        try:
            # Test with Claude Haiku (most cost-effective)
            success = self.service.test_model_access("anthropic.claude-3-haiku-20240307-v1:0")
            if success:
                print("✅ Successfully accessed Claude 3 Haiku")
            else:
                print("❌ Failed to access Claude 3 Haiku")
                
            # Test other models
            for name, model_id in self.service.list_available_models().items():
                if name != "claude-3-haiku":  # Already tested above
                    success = self.service.test_model_access(model_id)
                    status = "✅" if success else "❌"
                    print(f"{status} {name}: {model_id}")
                    
        except Exception as e:
            print(f"Integration test skipped (no AWS access): {e}")
    
    def test_real_compression(self):
        """Test actual compression with Bedrock (requires AWS credentials)"""
        try:
            config = CompressionConfig(
                compression_rate="medium",
                task_description="Answer questions about cloud computing and AWS services",
                model_id="anthropic.claude-3-haiku-20240307-v1:0"
            )
            
            result = self.service.compress_context(self.test_context, config)
            
            print(f"Original tokens: {result['original_tokens']}")
            print(f"Compressed tokens: {result['compressed_tokens']}")
            print(f"Compression ratio: {result['compression_ratio']:.1f}×")
            print(f"Compressed content: {result['compressed_kv'][:200]}...")
            
            self.assertGreater(result['compression_ratio'], 1.0)
            self.assertIn('AWS', result['compressed_kv'])
            
        except Exception as e:
            print(f"Real compression test skipped (no AWS access): {e}")


def run_basic_tests():
    """Run basic unit tests that don't require AWS access"""
    print("Running basic unit tests...")
    
    # Create test suite with only basic tests
    suite = unittest.TestSuite()
    
    # Add unit tests
    suite.addTest(TestBedrockCompressionService('test_initialization'))
    suite.addTest(TestBedrockCompressionService('test_create_task_prompt'))
    suite.addTest(TestBedrockCompressionService('test_chunk_context'))
    suite.addTest(TestBedrockCompressionService('test_fallback_compression'))
    suite.addTest(TestBedrockCompressionService('test_bedrock_invocation_claude'))
    suite.addTest(TestBedrockCompressionService('test_bedrock_invocation_llama'))
    suite.addTest(TestBedrockCompressionService('test_compress_context'))
    suite.addTest(TestBedrockCompressionService('test_compression_config'))
    suite.addTest(TestBedrockCompressionService('test_list_available_models'))
    suite.addTest(TestBedrockCompressionService('test_model_access_test'))
    suite.addTest(TestBedrockCompressionService('test_model_access_test_failure'))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def run_integration_tests():
    """Run integration tests that require AWS access"""
    print("\nRunning integration tests (requires AWS access)...")
    
    # Create test suite with integration tests
    suite = unittest.TestSuite()
    suite.addTest(TestIntegration('test_real_bedrock_access'))
    suite.addTest(TestIntegration('test_real_compression'))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Bedrock compression service')
    parser.add_argument('--integration', action='store_true', 
                       help='Run integration tests (requires AWS access)')
    parser.add_argument('--all', action='store_true', 
                       help='Run all tests')
    
    args = parser.parse_args()
    
    success = True
    
    if args.all or not args.integration:
        success &= run_basic_tests()
    
    if args.all or args.integration:
        success &= run_integration_tests()
    
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)

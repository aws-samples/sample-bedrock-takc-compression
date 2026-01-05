#!/usr/bin/env python3
"""
Example of using the Bedrock-powered TAKC compression service
"""

import os
import sys
import json

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from bedrock_compression_service import BedrockCompressionService, CompressionConfig


def main():
    print("🚀 Bedrock TAKC Compression Example")
    print("=" * 50)
    
    # Initialize the service
    service = BedrockCompressionService()
    
    # Test model access first
    print("\n📋 Testing Bedrock model access...")
    available_models = []
    for name, model_id in service.list_available_models().items():
        if service.test_model_access(model_id):
            available_models.append((name, model_id))
            print(f"✅ {name}: {model_id}")
        else:
            print(f"❌ {name}: {model_id} (not accessible)")
    
    if not available_models:
        print("\n❌ No Bedrock models are accessible. Please check:")
        print("  1. AWS credentials are configured")
        print("  2. Bedrock service is available in your region")
        print("  3. You have requested access to Bedrock models")
        return
    
    # Use the first available model
    selected_model = available_models[0]
    print(f"\n🎯 Using model: {selected_model[0]} ({selected_model[1]})")
    
    # Example context - financial data
    context = '''
    The company reported strong financial results for Q3 2024. Revenue increased by 15% 
    year-over-year to $2.5 billion, driven primarily by growth in the cloud services 
    division which saw 28% growth. Operating margin improved to 22% from 19% in the 
    previous quarter. The CEO mentioned that customer acquisition costs decreased by 8% 
    while customer lifetime value increased by 12%. The company also announced plans to 
    expand into three new international markets in 2025, with an expected investment of 
    $150 million. Employee headcount grew by 5% to 12,000 employees. The board approved 
    a $500 million share buyback program. The company's cash position remains strong at 
    $3.2 billion. Research and development spending increased by 18% to support new 
    product initiatives. The customer satisfaction score improved to 4.7 out of 5.0.
    '''
    
    print(f"\n📄 Original context ({len(context.split())} tokens):")
    print(context.strip())
    
    # Test different compression rates
    compression_rates = ["light", "medium", "high", "ultra"]
    
    print(f"\n🔄 Testing compression at different rates...")
    print("-" * 80)
    
    results = {}
    
    for rate in compression_rates:
        print(f"\n🔧 Testing {rate} compression...")
        
        # Create compression configuration
        config = CompressionConfig(
            compression_rate=rate,
            task_description="Answer questions about financial performance and business metrics",
            few_shot_examples='''
Q: What was the revenue growth?
A: Revenue grew 15% year-over-year to $2.5 billion.

Q: How did the cloud division perform?
A: Cloud services division grew 28%.

Q: What was the operating margin?
A: Operating margin improved to 22% from 19%.
            '''.strip(),
            model_id=selected_model[1]
        )
        
        try:
            # Perform compression
            result = service.compress_context(context, config)
            results[rate] = result
            
            print(f"  📊 Compression: {result['compression_ratio']:.1f}× "
                  f"({result['original_tokens']} → {result['compressed_tokens']} tokens)")
            print(f"  📝 Compressed content:")
            print(f"     {result['compressed_kv']}")
            
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            continue
    
    # Summary table
    if results:
        print(f"\n📈 Compression Summary:")
        print("-" * 80)
        print(f"{'Rate':<8} {'Ratio':<8} {'Tokens':<8} {'Efficiency':<12}")
        print("-" * 80)
        
        for rate in compression_rates:
            if rate in results:
                result = results[rate]
                efficiency = f"{(1 - result['compressed_tokens']/result['original_tokens'])*100:.1f}%"
                print(f"{rate:<8} {result['compression_ratio']:<8.1f} "
                      f"{result['compressed_tokens']:<8} {efficiency:<12}")
    
    # Test cache storage and retrieval
    print(f"\n💾 Testing cache storage...")
    
    if "medium" in results:
        try:
            # Store cache
            cache_key = service.store_compressed_cache(
                "financial-analysis", 
                "medium", 
                results["medium"]
            )
            print(f"  ✅ Stored cache: {cache_key}")
            
            # Retrieve cache
            retrieved = service.retrieve_compressed_cache("financial-analysis", "medium")
            if retrieved:
                print(f"  ✅ Retrieved cache successfully")
                print(f"     Metadata: {json.dumps(retrieved['metadata'], indent=2)}")
            else:
                print(f"  ❌ Failed to retrieve cache")
                
        except Exception as e:
            print(f"  ❌ Cache operation failed: {e}")
    
    # Test multi-rate cache creation
    print(f"\n🎯 Testing multi-rate cache creation...")
    
    try:
        cache_keys = service.create_multi_rate_cache(
            task_type="financial-analysis",
            context=context,
            task_description="Answer questions about financial performance and business metrics",
            model_id=selected_model[1]
        )
        
        print(f"  ✅ Created multi-rate caches:")
        for rate, key in cache_keys.items():
            print(f"     {rate}: {key}")
            
    except Exception as e:
        print(f"  ❌ Multi-rate cache creation failed: {e}")
    
    print(f"\n🎉 Example completed successfully!")
    print(f"\n💡 Next steps:")
    print(f"  1. Try different models by modifying the model_id parameter")
    print(f"  2. Experiment with different task descriptions and few-shot examples")
    print(f"  3. Test with your own domain-specific content")
    print(f"  4. Integrate with your application using the compression service")


def test_specific_model():
    """Test a specific model interactively"""
    service = BedrockCompressionService()
    
    print("Available models:")
    models = service.list_available_models()
    for i, (name, model_id) in enumerate(models.items(), 1):
        print(f"  {i}. {name}: {model_id}")
    
    try:
        choice = int(input("\nSelect a model (1-{}): ".format(len(models))))
        selected = list(models.items())[choice - 1]
        
        print(f"\nTesting {selected[0]}...")
        if service.test_model_access(selected[1]):
            print("✅ Model is accessible!")
            
            # Quick compression test
            test_text = "This is a test of the compression system. It should work well."
            config = CompressionConfig(
                compression_rate="medium",
                task_description="Test compression",
                model_id=selected[1]
            )
            
            result = service.compress_context(test_text, config)
            print(f"Test compression: {result['compression_ratio']:.1f}×")
            print(f"Result: {result['compressed_kv']}")
            
        else:
            print("❌ Model is not accessible")
            
    except (ValueError, IndexError):
        print("Invalid selection")
    except KeyboardInterrupt:
        print("\nCancelled")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Bedrock compression example')
    parser.add_argument('--test-model', action='store_true', 
                       help='Interactively test a specific model')
    
    args = parser.parse_args()
    
    if args.test_model:
        test_specific_model()
    else:
        main()

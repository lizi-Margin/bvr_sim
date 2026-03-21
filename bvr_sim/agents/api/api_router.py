from api.api import *

def get_api_class(model_name):
    # a router to get correct API client class
    if model_name == 'deepseek-v3.1-250821':
        return OpenAI_API

    if 'qwen' in model_name:
        API_CLASS = WWXQ_API
    elif 'doubao' in model_name:
        API_CLASS = Volcano_API
    elif 'kimi' in model_name:
        API_CLASS = Volcano_API
    elif 'deepseek' in model_name:
        API_CLASS = Volcano_API
    elif 'gpt' in model_name:
        API_CLASS = OpenAI_API
    elif 'gemini' in model_name:
        API_CLASS = OpenAI_API
    else:
        ## WWXQ by default
        API_CLASS = WWXQ_API

    return API_CLASS


def unit_test():
    """Test different API models"""

    test_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in Chinese and tell me 1+1=?"}
    ]

    # Test configs: (model_name, description)
    test_configs = [
        ('doubao-seed-1-6-250615', 'Doubao Seed 1.6'),
        ('doubao-seed-1-6-flash-250828', 'Doubao Flash'),
        ('kimi-k2-250905', 'Kimi K2'),
        ('deepseek-v3-1-250821', 'DeepSeek V3'),
        ('qwen3-8b', 'Qwen 3 8B'),
        # ('gpt-4o-mini', 'GPT-4o Mini'),
    ]

    print("=" * 60)
    print("API Unit Tests")
    print("=" * 60)

    for model_name, description in test_configs:
        print(f"\n[Testing] {description} ({model_name})")
        print("-" * 60)

        try:
            # Get API class and initialize
            api_class = get_api_class(model_name)
            api = api_class(model=model_name)

            print(f"API Class: {api_class.__name__}")
            print(f"API Key Set: {'Yes' if api.api_key else 'No'}")

            # Call API
            response = api(
                input_messages=test_messages,
                temperature=0.7,
                max_tokens=100
            )

            print(f"✓ SUCCESS")
            print(f"Response: {response[:200]}..." if len(response) > 200 else f"Response: {response}")

        except Exception as e:
            error_str = str(e)
            print(f"✗ FAILED")
            print(f"Error Type: {type(e).__name__}")

            # Parse specific error messages
            if 'ModelNotOpen' in error_str:
                print("Reason: Model not activated in account")
            elif '404' in error_str:
                print("Reason: Model not found or not accessible")
            elif '401' in error_str or 'Unauthorized' in error_str:
                print("Reason: Invalid or missing API key")
            elif 'api_key' in error_str.lower():
                print("Reason: API key not configured")
            else:
                print(f"Reason: {error_str[:200]}")

    print("\n" + "=" * 60)
    print("Test Summary Complete")
    print("=" * 60)


if __name__ == '__main__':
    unit_test()
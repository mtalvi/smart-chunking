# LLM API Configuration

The smart-chunking system uses OpenAI-compatible APIs for LLM-powered solution generation. This provides flexibility to use various LLM providers including OpenAI, Azure OpenAI, local models, or other compatible services.

## Environment Variables

Configure the following environment variables to enable LLM integration:

### Required Variables

- **API_KEY**: Your LLM provider API key
  - OpenAI: Get from [OpenAI API Keys](https://platform.openai.com/api-keys) (Format: `sk-...`)
  - Azure OpenAI: Get from Azure portal
  - Local/Custom: Provider-specific format
  - **This is required for LLM functionality to work**

### Optional Variables

- **ENDPOINT_URL**: LLM API endpoint URL
  - Default: `https://api.openai.com/v1` (OpenAI)
  - Azure OpenAI: `https://your-resource.openai.azure.com/`
  - Local models: `http://localhost:8000/v1` (e.g., vLLM, LocalAI)
  - Other providers: Provider-specific endpoint

- **MODEL_NAME**: Model to use for solution generation
  - Default: `gpt-3.5-turbo`
  - OpenAI: `gpt-3.5-turbo`, `gpt-4`, `gpt-4-turbo-preview`, etc.
  - Azure OpenAI: Your deployed model name
  - Local models: Model identifier from your deployment
  - Choose based on your needs, budget, and availability

## Setup Instructions

### 1. Set Environment Variables

**Option A: Export in shell**
```bash
export API_KEY="your-api-key-here"
export MODEL_NAME="gpt-3.5-turbo"
export ENDPOINT_URL="https://api.openai.com/v1"
```

**Option B: Create .env file**
```bash
# Create .env file in project root
cat > .env << 'EOF'
API_KEY=your-api-key-here
MODEL_NAME=gpt-3.5-turbo
ENDPOINT_URL=https://api.openai.com/v1
EOF
```

**Option C: Docker/Container deployment**
```yaml
# In docker-compose.yml or Kubernetes deployment
environment:
  - API_KEY=your-api-key-here
  - MODEL_NAME=gpt-3.5-turbo
  - ENDPOINT_URL=https://api.openai.com/v1
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Test Configuration

```python
from src.solutions.llm_generator import LLMSolutionGenerator

# Test the configuration
generator = LLMSolutionGenerator()
print(f"LLM Available: {generator.is_available}")
print(f"Model: {generator.model_name}")
print(f"Endpoint: {generator.endpoint_url}")
```

## Provider-Specific Examples

### OpenAI
```bash
API_KEY=sk-your-openai-key-here
MODEL_NAME=gpt-3.5-turbo
ENDPOINT_URL=https://api.openai.com/v1
```

### Azure OpenAI
```bash
API_KEY=your-azure-openai-key
MODEL_NAME=your-deployment-name
ENDPOINT_URL=https://your-resource.openai.azure.com/
```

### Local vLLM/LocalAI
```bash
API_KEY=dummy-key-or-actual-key
MODEL_NAME=mistral-7b-instruct-v0.1
ENDPOINT_URL=http://localhost:8000/v1
```

### Ollama (with OpenAI-compatible server)
```bash
API_KEY=ollama
MODEL_NAME=llama2:7b
ENDPOINT_URL=http://localhost:11434/v1
```

## Model Recommendations

### For Development/Testing
- **OpenAI gpt-3.5-turbo**: Fast, cost-effective, good quality (~$0.002 per 1K tokens)
- **Local 7B models**: Free, privacy-focused, moderate quality
- **Ollama models**: Easy setup, good for experimentation

### For Production
- **OpenAI gpt-4**: Higher quality solutions, better reasoning (~$0.03 per 1K tokens)
- **Azure OpenAI**: Enterprise features, compliance, dedicated capacity
- **Local 13B+ models**: Privacy, control, predictable costs

### For High-Volume Production
- **OpenAI gpt-3.5-turbo**: Balance of cost and quality
- **Local model clusters**: Scalable, cost-effective for high volume
- Consider rate limiting and caching strategies

## Fallback Behavior

The system gracefully handles missing or invalid LLM configuration:

1. **No API_KEY**: LLM solutions disabled, pattern-only mode
2. **Invalid API_KEY**: Falls back to built-in solution templates  
3. **API errors**: Provides generic troubleshooting steps
4. **Rate limits**: Returns cached or template solutions
5. **Network issues**: Timeout fallback to pattern-based solutions

## Security Best Practices

1. **Never commit API keys** to version control
2. **Use environment variables** or secure secret management
3. **Rotate API keys** regularly (when supported by provider)
4. **Monitor usage** and set appropriate limits
5. **Use least-privilege** API keys when available
6. **Secure local deployments** with proper authentication

## Troubleshooting

### Common Issues

**"LLM not available - using pattern-only mode"**
- Check API_KEY is set and valid
- Verify network connectivity to the endpoint
- Check model name is supported by your provider
- Ensure endpoint URL is correct and accessible

**"API error: 401 Unauthorized"**
- Invalid or missing API key
- API key may be revoked or expired
- Wrong authentication format for your provider

**"API error: 429 Rate Limited"**
- Rate limit exceeded
- Upgrade API plan or implement backoff
- Consider using a different model or provider

**"API error: timeout"**
- Network issues or high load
- Increase timeout or implement retry logic
- Consider using a local model for reliability

### Debug Commands

```bash
# Check environment variables
echo $API_KEY | head -c 20
echo $MODEL_NAME
echo $ENDPOINT_URL

# Test API connectivity (OpenAI-compatible)
curl -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     "$ENDPOINT_URL/models"

# Test with a simple completion
curl -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"'$MODEL_NAME'","messages":[{"role":"user","content":"Hello"}],"max_tokens":5}' \
     "$ENDPOINT_URL/chat/completions"
```

## Migration Guide

### From Ollama to OpenAI-compatible API

The migration is transparent for existing code:

- **No code changes** required in detection or analysis logic
- **Same solution format** returned by the LLM generator
- **Improved reliability** with managed API services
- **Better scaling** options for production workloads

### From OpenAI to Other Providers

Simply update the environment variables:

1. Change `ENDPOINT_URL` to your new provider
2. Update `API_KEY` with the new provider's key
3. Set `MODEL_NAME` to an available model
4. Test the configuration

Existing error patterns and solution templates remain unchanged. 
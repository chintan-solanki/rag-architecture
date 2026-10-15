# Configuring LLM providers

The API and ingestion services configure their LLM independently in
`api/config/config.yml` and `ingestion/config/config.yml`. Each `llm` section
uses the same fields:

```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
```

Supported providers and their default credential environment variables are:

| Provider | LlamaIndex adapter | Default environment variable |
| --- | --- | --- |
| `openai` | `llama-index-llms-openai` | `OPENAI_API_KEY` |
| `gemini` | `llama-index-llms-google-genai` | `GOOGLE_API_KEY` |
| `anthropic` | `llama-index-llms-anthropic` | `ANTHROPIC_API_KEY` |

Set `provider`, `model`, and `api_key_env` in both service configs to choose a
provider and model. Set the named environment variable in the runtime
environment (for Docker Compose, in the project `.env` file or shell); do not
put the credential value in YAML. Both services receive the supported
provider credential variables through Compose.

For example, to use Gemini, set `provider: gemini`, choose a supported Gemini
model, and set `api_key_env: GOOGLE_API_KEY` in both LLM config sections. The
same approach applies to Anthropic with `ANTHROPIC_API_KEY`. Runtime startup
reports an explicit error if the selected credential is missing or a provider
adapter is unavailable.

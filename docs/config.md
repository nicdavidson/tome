# Documentation for LLM Backend Expansion to Include xAI

This documentation covers the recent changes to the application's configuration, which expand the supported LLM (Large Language Model) backends to include xAI (Grok). This update enhances flexibility, allowing users to choose from multiple backends based on their needs, with a focus on cost-efficiency and auto-detection.

## What This Does and Why It Matters

This change updates the `LLM_BACKEND` configuration in `config.py` to support "xai" as an additional option alongside "anthropic" (for Anthropic's Claude models) and "ollama" (for local inference with Ollama). The system now auto-detects the backend based on the presence of API keys in the environment variables, prioritizing "anthropic" if its key is set, then "xai", and defaulting to "ollama".

Why it matters:
- **Increased Options**: Users can now integrate xAI's Grok models, which are designed for efficiency and may reduce costs compared to other providers.
- **Auto-Detection**: This simplifies setup by automatically selecting the backend without manual configuration, reducing errors and improving user experience.
- **Seamless Integration**: New variables (`XAI_API_KEY` and `XAI_MODEL`) enable easy configuration for xAI, ensuring the application can switch backends without major code changes.
- **Broader Use Cases**: This supports diverse environments, such as cloud-based AI services (Anthropic/xAI) or local setups (Ollama), making the application more versatile for developers and organizations.

## How to Use It

To use the updated LLM backend configuration, you'll primarily work with environment variables in a `.env` file (e.g., based on the provided `.env.example`). The system auto-detects the backend, but you can override it explicitly.

### Steps to Set Up xAI as the Backend

1. **Create or Update Your `.env` File**:
   - Copy the provided `.env.example` to `.env` in your project root.
   - Set the required variables for xAI.

2. **Example Configuration**:
   Here's an example of a `.env` file configured for xAI:

   ```
   # LLM Backend — auto-detects based on which key is set
   # Options: "anthropic", "xai", "ollama"
   TOME_LLM_BACKEND=xai  # Optional override; if omitted, it auto-detects based on keys

   # xAI (Grok) Configuration
   XAI_API_KEY=xai-your_api_key_here  # Required for xAI; obtain from xAI dashboard
   XAI_MODEL=grok-3-mini-fast  # Default model; can be changed for other xAI models
   ```

   - If you don't specify `TOME_LLM_BACKEND`, the system checks for `ANTHROPIC_API_KEY` first, then `XAI_API_KEY`, and defaults to "ollama".
   - Restart your application after updating the `.env` file to apply changes.

3. **Code Example in Your Application**:
   Once configured, you can use the LLM backend in your code as before. For instance, in `engine.py`, the `llm_generate` function now supports xAI:

   ```python
   import config as Config

   async def main():
       # Example: Generate text using the configured LLM
       prompt = "Explain the theory of relativity in simple terms."
       response = await Config.llm_generate(prompt)  # This will use xAI if configured
       print(response)
   ```

   - The `llm_generate` function in `engine.py` automatically routes to the correct backend based on `Config.LLM_BACKEND`.
   - In `app.py`, the health check now includes xAI status:

     ```python
     async def health():
         if Config.LLM_BACKEND == "xai":
             llm_status = "configured" if Config.XAI_API_KEY else "missing_key"
             model = Config.XAI_MODEL
         # ... other backends ...
     ```

     This allows you to verify the backend configuration via an API endpoint.

## Parameters and Options

The following configuration options have been updated or added in `config.py`. These are accessed via environment variables and have default values for ease of use.

| Variable              | Description                          | Default Value                  | Notes |
|-----------------------|--------------------------------------|--------------------------------|-------|
| **TOME_LLM_BACKEND** | Specifies the LLM backend to use.   | Auto-detected: "anthropic" if `ANTHROPIC_API_KEY` is set, otherwise "xai" if `XAI_API_KEY` is set, otherwise "ollama". | Options: "anthropic", "xai", "ollama". Set explicitly to override auto-detection. |
| **XAI_API_KEY**      | API key for xAI (Grok) services.    | Empty string ("")              | Required for xAI backend; obtain from the xAI platform. If not set, xAI won't be selected via auto-detection. |
| **XAI_MODEL**        | The default model to use with xAI.  | "grok-3-mini-fast"             | Specifies the xAI model for inference. Change this to other available xAI models as needed. |

These variables are loaded in `config.py` using `os.getenv`, ensuring they are environment-safe and easy to manage.

## Common Patterns and Gotchas

- **Auto-Detection Order**: The backend is detected in this priority: Anthropic > xAI > Ollama. If multiple keys are set, Anthropic takes precedence. Always check your `.env` file to avoid unexpected behavior.
  
- **Overriding Defaults**: While defaults exist (e.g., `XAI_MODEL`), explicitly set them in `.env` for production to ensure consistency across environments.

- **Error Handling**: If an API key is missing for the selected backend (e.g., `XAI_API_KEY` for "xai"), the application may fail gracefully (e.g., in health checks) or raise errors during runtime. Monitor logs for messages like "missing_key".

- **Security Best Practices**: Treat API keys as sensitive; use environment variables or secure vaults instead of hardcoding. Never commit actual keys to version control—use the `.env.example` as a template.

- **Testing Patterns**: After changing backends, test with a simple prompt (e.g., via `llm_generate`) to verify integration. For xAI, ensure your API key has the necessary permissions for the selected model.

- **Gotchas**:
  - xAI requires an internet connection, unlike Ollama which can run locally.
  - If switching backends frequently, restart the application to reload configurations.
  - Rate limits: xAI and Anthropic have API usage limits; handle retries or fallbacks in your code if needed.

This update makes the application more robust and adaptable—refer to the code diffs in the change log for more details. If you encounter issues, check the environment variables and application logs first.
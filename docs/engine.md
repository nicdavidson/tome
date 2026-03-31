# Documentation for New xAI Backend Integration in engine.py

## Overview
This documentation covers a recent code change that introduces support for the xAI Grok API as a new backend for large language model (LLM) generation in the application. Specifically, a new function `_xai_generate` has been added to `engine.py`. This enhancement allows users to leverage xAI's models for more cost-efficient and flexible LLM operations, expanding beyond existing backends like Anthropic and Ollama.

### What This Does and Why It Matters
- **What it does**: The `_xai_generate` function is a new asynchronous function that interfaces with the xAI Grok API to generate responses based on a given prompt. It integrates into the existing `llm_generate` function, which acts as a dispatcher for different LLM backends. When the application is configured to use the "xai" backend, `llm_generate` will call `_xai_generate` to handle the API request.
- **Why it matters**: xAI's models, such as Grok-3, offer a cost-effective alternative for AI-driven tasks like text generation. This addition increases the application's flexibility, allowing developers to switch backends based on performance, cost, or availability. It also demonstrates how the system can be extended for custom LLM integrations, promoting modularity and ease of maintenance.

## How It Fits into the Existing Code
The `_xai_generate` function is called from `llm_generate`, which is the central entry point for LLM generation. Here's a simplified overview:
- `llm_generate` checks the configured backend (via `Config.LLM_BACKEND`) and routes the request accordingly.
- If `Config.LLM_BACKEND` is set to "xai", it invokes `_xai_generate(prompt, json_mode)`.
- This design allows seamless switching between backends without altering high-level code, as long as the environment is properly configured.

Configuration for the xAI backend is handled in `config.py`, which auto-detects the backend based on environment variables (e.g., `XAI_API_KEY`). Updates in `app.py` ensure that the health check reflects the xAI status.

## Parameters and Options
The `_xai_generate` function has the following parameters:
- **prompt (str)**: The input text or query to send to the xAI Grok API. This is the main content that the model will process to generate a response.
- **json_mode (bool, optional)**: Defaults to `False`. If set to `True`, the function requests the API to format the response as structured JSON, which is useful for applications needing parseable output.

To use the xAI backend, you must set the following environment variables in your `.env` file (as shown in the updated `.env.example`):
- **XAI_API_KEY**: Your xAI API key (e.g., `XAI_API_KEY=xai-your_key_here`). This is required for authentication.
- **TOME_XAI_MODEL**: The specific xAI model to use (e.g., `TOME_XAI_MODEL=grok-3-mini-fast`). This defaults to "grok-3-mini-fast" if not specified.

The backend is auto-detected in `config.py`, so setting `XAI_API_KEY` will prioritize "xai" over other options like "anthropic" or "ollama".

## How to Use It
To integrate and use the xAI backend, follow these steps:

1. **Set up your environment**:
   Add the necessary variables to your `.env` file:
   ```
   TOME_LLM_BACKEND=xai  # Explicitly set if needed, but auto-detection will use this if XAI_API_KEY is present
   XAI_API_KEY=your_xai_api_key_here
   TOME_XAI_MODEL=grok-3-mini-fast  # Optional, but recommended for specificity
   ```

2. **Call the LLM generation function**:
   In your code, use `llm_generate` as you normally would. The system will automatically route to `_xai_generate` if configured.

   **Example**:
   ```python
   import asyncio
   from engine import llm_generate

   async def main():
       prompt = "Explain the theory of relativity in simple terms."
       json_mode = True  # Request JSON-formatted response
       
       try:
           response = await llm_generate(prompt, json_mode)
           print(response)  # Output: A JSON string or plain text based on the model
       except Exception as e:
           print(f"Error: {e}")

   if __name__ == "__main__":
       asyncio.run(main())
   ```

   In this example:
   - If `TOME_LLM_BACKEND` is "xai", `_xai_generate` will handle the request.
   - The response will be a string from the xAI API, potentially in JSON format if `json_mode` is True.

3. **Integrating Custom LLM Backends**:
   For developers looking to add their own backends:
   - Add a new condition in `llm_generate` similar to the existing ones (e.g., `if Config.LLM_BACKEND == "custom": return await _custom_generate(...)`).
   - Create a new function like `_xai_generate` in `engine.py`.
   - Update `config.py` to include any new environment variables and auto-detection logic.
   - Ensure error handling for API keys and network issues.

## Common Patterns and Gotchas
- **Auto-Detection**: The system prioritizes backends based on the order in `config.py` (e.g., Anthropic first, then xAI, then Ollama). If multiple keys are set, xAI will only be used if explicitly set or if Anthropic's key is absent.
- **Error Handling**: Always wrap calls to `llm_generate` in try-except blocks, as API failures (e.g., invalid keys or rate limits) can raise exceptions. For xAI specifically, ensure your API key is valid and not expired.
- **Performance Considerations**: xAI models may have different response times and token limits compared to Anthropic or Ollama. Test with your prompts to avoid truncation or incomplete responses.
- **JSON Mode**: If using `json_mode=True`, parse the response with a JSON library (e.g., `json.loads(response)`) to handle it properly, as the output might not always be perfectly formatted.
- **Security**: Never hardcode API keys in your code. Always use environment variables or secure vaults.
- **Testing**: Before deploying, verify the backend in a health check or debug mode, as shown in the updated `app.py`. If `XAI_API_KEY` is missing, the system will fall back to other backends or report an error.

This integration enhances the application's versatility for LLM tasks—refer to the code changes in `engine.py`, `config.py`, and `.env.example` for full details. If you're extending this for other backends, follow the modular pattern to keep the codebase maintainable.
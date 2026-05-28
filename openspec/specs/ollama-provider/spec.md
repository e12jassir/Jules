# Ollama Provider Specification

## Purpose

Define the canonical provider contract and the local Ollama HTTP integration used by Jules for identity, offline fallback, streaming, and embeddings.

## Requirements

### Requirement: Provider Protocol Contract

The system MUST expose a `Provider` protocol for Jules providers and a canonical provider error hierarchy.

- `name: str`
- `async def ask(self, prompt: str, context: SessionContext, model: str) -> str`
- `async def stream(self, prompt: str, context: SessionContext, model: str) -> AsyncIterator[str]`
- `async def embed(self, text: str) -> list[float]`
- `async def health_check(self) -> bool`
- `async def close(self) -> None`

The system MUST expose these exceptions:
- `ProviderError`
- `ProviderUnavailableError`
- `ProviderTimeoutError`

#### Scenario: Import provider contract
- **Given** Module 3 provider code is imported
- **When** a caller imports `Provider` and the provider exceptions from `jules.providers.base`
- **Then** the contract MUST be usable without importing provider-specific transport code
- **And** timeout and availability failures MUST be representable distinctly from generic provider errors.

### Requirement: Non-Blocking Ollama Ask

The system MUST implement an asynchronous `OllamaProvider.ask()` that calls the local Ollama generate API without blocking the terminal event loop.

#### Scenario: Generate a non-streaming response
- **Given** a reachable Ollama daemon and a valid local model name
- **When** `OllamaProvider.ask(prompt, context, model)` is called
- **Then** the provider MUST send `POST /api/generate` with `{"model": model, "prompt": prompt, "stream": false}`
- **And** it MUST return the `response` string from the JSON payload
- **And** it MUST raise `ProviderTimeoutError` on request timeout
- **And** it MUST raise `ProviderUnavailableError` when the Ollama daemon cannot be reached.

### Requirement: Streaming Token Delivery

The system MUST implement `OllamaProvider.stream()` as an async iterator over Ollama streaming responses.

#### Scenario: Yield streamed text chunks
- **Given** a reachable Ollama daemon and a valid local model name
- **When** `OllamaProvider.stream(prompt, context, model)` is iterated
- **Then** the provider MUST send `POST /api/generate` with `stream: true`
- **And** it MUST yield non-empty `response` chunks as they arrive
- **And** it MUST stop when Ollama sends `done: true`
- **And** malformed JSON or explicit Ollama error payloads MUST raise `ProviderError`.

### Requirement: Embedding Generation

The system MUST implement `OllamaProvider.embed()` against the current Ollama embeddings API.

#### Scenario: Generate an embedding vector
- **Given** a reachable Ollama daemon and an embedding-capable local model
- **When** `OllamaProvider.embed(text)` is called
- **Then** the provider MUST send `POST /api/embed` with `{"model": embedding_model, "input": text}`
- **And** it MUST read the first vector from the returned `embeddings` array
- **And** it MUST return a `list[float]`
- **And** missing or malformed vectors MUST raise `ProviderError`.

### Requirement: Lightweight Health Check

The system MUST implement `OllamaProvider.health_check()` as a low-cost readiness probe.

#### Scenario: Check local Ollama availability
- **Given** the provider is configured with a local Ollama base URL
- **When** `health_check()` is executed
- **Then** the provider MUST probe `GET /api/tags`
- **And** it MUST return `True` only when a successful HTTP response is received
- **And** timeout, transport, or invalid-response failures MUST return `False` instead of raising.

### Requirement: Session Reuse and Cleanup

The system MUST reuse an internal `aiohttp.ClientSession` across provider calls and close it explicitly when the provider is no longer needed.

#### Scenario: Reuse and close HTTP session
- **Given** the same `OllamaProvider` instance handles multiple requests
- **When** `ask()`, `stream()`, `embed()`, or `health_check()` are invoked sequentially
- **Then** the provider MUST reuse a persistent `aiohttp.ClientSession`
- **And** `close()` MUST close that session cleanly
- **And** later requests MAY recreate a fresh session if the previous one was closed.

### Requirement: Module 3 Verification Baseline

The system MUST maintain integration coverage for the local Ollama provider behavior.

#### Scenario: Run Module 3 verification
- **Given** the project virtualenv is active and Ollama is available on `localhost:11434`
- **When** `./.venv/bin/python -m pytest tests/integration/test_provider_coherence.py` runs
- **Then** the suite MUST verify `health_check`, `ask`, `stream`, `embed`, and timeout handling
- **And** model selection MUST be discovered dynamically from `/api/tags` when available
- **And** the suite MUST skip cleanly when no local Ollama daemon is running.
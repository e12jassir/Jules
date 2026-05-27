from __future__ import annotations

import asyncio
import json
import socket
import aiohttp

import pytest

from jules.memory.models import SessionContext
from jules.providers.base import ProviderTimeoutError
from jules.providers.ollama import OllamaProvider


OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434


def _ollama_port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((OLLAMA_HOST, OLLAMA_PORT)) == 0


def _require_ollama() -> None:
    if not _ollama_port_open():
        pytest.skip("Ollama integration tests require localhost:11434")


def _require_model() -> str:
    _require_ollama()

    async def fetch_tags():
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", timeout=5) as response:
                return await response.json()

    payload = asyncio.run(fetch_tags())
    
    models = []
    for model in payload.get("models", []):
        name = model.get("name")
        if isinstance(name, str):
            models.append(name)
            
    for name in models:
        if name.startswith("llama3.2:1b"):
            return name
            
    if models:
        return models[0]

    pytest.skip("Ollama integration tests require at least one local model")


def _context() -> SessionContext:
    return SessionContext(
        project="jules",
        directory="/home/e12jassir/proyects/Jules",
        active_files=["jules/providers/ollama.py"],
        inferred_intent="testing",
        time_of_day="afternoon",
    )


def test_ollama_health_check_returns_true_when_service_is_running() -> None:
    _require_ollama()

    provider = OllamaProvider(timeout_seconds=5.0)

    async def run_check():
        try:
            return await provider.health_check()
        finally:
            await provider.close()

    assert asyncio.run(run_check()) is True


def test_ollama_ask_returns_a_coherent_response() -> None:
    model = _require_model()

    provider = OllamaProvider(timeout_seconds=30.0)
    
    async def run_ask():
        try:
            return await provider.ask(
                "Reply with exactly one word: Jules",
                _context(),
                model,
            )
        finally:
            await provider.close()

    response = asyncio.run(run_ask())

    assert isinstance(response, str)
    assert response.strip()
    assert len(response.strip()) <= 100


def test_ollama_timeout_raises_provider_timeout_error() -> None:
    model = _require_model()

    provider = OllamaProvider(timeout_seconds=0.001)

    async def run_timeout():
        try:
            await provider.ask(
                "Explain terminal latency in one short paragraph.",
                _context(),
                model,
            )
        finally:
            await provider.close()

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(run_timeout())


def test_ollama_stream_yields_chunks() -> None:
    model = _require_model()

    provider = OllamaProvider(timeout_seconds=30.0)

    async def run_stream():
        try:
            chunks = []
            async for chunk in provider.stream(
                "Reply with exactly one word: Jules",
                _context(),
                model,
            ):
                chunks.append(chunk)
            return chunks
        finally:
            await provider.close()

    chunks = asyncio.run(run_stream())

    assert len(chunks) > 0
    full_text = "".join(chunks)
    assert full_text.strip()
    assert len(full_text.strip()) <= 100


def test_ollama_embed_returns_vector() -> None:
    model = _require_model()

    provider = OllamaProvider(timeout_seconds=30.0, default_model=model)

    async def run_embed():
        try:
            return await provider.embed("Jules")
        finally:
            await provider.close()

    vector = asyncio.run(run_embed())

    assert isinstance(vector, list)
    assert len(vector) > 0
    assert all(isinstance(v, float) for v in vector)

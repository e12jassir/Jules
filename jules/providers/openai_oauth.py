"""Native OpenAI provider backed by Jules OAuth tokens."""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any, AsyncIterator

from jules.auth import get_valid_token
from jules.memory.models import SessionContext
from jules.providers.base import ContentEvent, ProviderError, ProviderUnavailableError

_OPENAI_CODEX_BASE_URL = "https://chatgpt.com/backend-api"


def _extract_chatgpt_account_id(token: str) -> str:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Token OAuth de OpenAI no tiene el formato JWT esperado.")
        payload_b64 = parts[1]
        missing_padding = len(payload_b64) % 4
        if missing_padding:
            payload_b64 += "=" * (4 - missing_padding)
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        payload = json.loads(payload_bytes.decode("utf-8"))
        claim = payload.get("https://api.openai.com/auth", {})
        account_id = claim.get("chatgpt_account_id")
        if not account_id:
            raise ValueError("No se encontró 'chatgpt_account_id' en los claims del token.")
        return str(account_id)
    except Exception as exc:
        raise ValueError(f"Error al decodificar el token JWT de OpenAI: {exc}") from exc


class OpenAIOAuthProvider:
    name = "openai_oauth"

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds

    def _system_prompt(self) -> str:
        try:
            from jules.personality.loader import PersonalityLoader
            return PersonalityLoader().load("openai_oauth")
        except Exception:
            return "You are Jules, a helpful AI assistant."

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        del context
        try:
            import httpx  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderUnavailableError("httpx not installed. Run: pip install httpx") from exc

        token = await get_valid_token("openai", auto_login=False)
        try:
            account_id = _extract_chatgpt_account_id(token.access_token)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

        req_id = f"codex_ws_{uuid.uuid4().hex[:8]}"
        ws_url = "wss://chatgpt.com/backend-api/codex/responses"

        payload = {
            "type": "response.create",
            "model": model,
            "stream": True,
            "instructions": self._system_prompt(),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
        }

        try:
            import websockets
            async with websockets.connect(
                ws_url,
                additional_headers=self._headers_ws(token.access_token, account_id, req_id),
                open_timeout=self.timeout_seconds,
            ) as ws:
                await ws.send(json.dumps(payload))
                
                full_response = []
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    event_type = data.get("type")
                    
                    if event_type == "error":
                        error_msg = data.get("error", {}).get("message", "Unknown error")
                        raise ProviderError(f"OpenAI WS Error: {error_msg}")
                    
                    if event_type in ("response.text.delta", "response.output_text.delta"):
                        full_response.append(data.get("delta", ""))
                    
                    if event_type in ("response.done", "response.completed", "response.incomplete"):
                        break
                        
                return "".join(full_response)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OpenAI OAuth request failed: {exc}") from exc

    async def stream(
        self,
        prompt: str,
        context: SessionContext,
        model: str,
    ) -> AsyncIterator[str]:
        del context
        token = await get_valid_token("openai", auto_login=False)
        try:
            account_id = _extract_chatgpt_account_id(token.access_token)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc

        req_id = f"codex_ws_{uuid.uuid4().hex[:8]}"
        ws_url = "wss://chatgpt.com/backend-api/codex/responses"

        payload = {
            "type": "response.create",
            "model": model,
            "stream": True,
            "instructions": self._system_prompt(),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
        }

        try:
            import websockets
            async with websockets.connect(
                ws_url,
                additional_headers=self._headers_ws(token.access_token, account_id, req_id),
                open_timeout=self.timeout_seconds,
            ) as ws:
                await ws.send(json.dumps(payload))
                
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    event_type = data.get("type")
                    
                    if event_type == "error":
                        error_msg = data.get("error", {}).get("message", "Unknown error")
                        yield f"[Error: {error_msg}]"
                        break
                    
                    if event_type in ("response.text.delta", "response.output_text.delta"):
                        yield data.get("delta", "")
                    
                    if event_type in ("response.done", "response.completed", "response.incomplete"):
                        break
        except Exception as exc:
            yield f"\n[Stream Error: {exc}]\n"

    async def embed(self, text: str) -> list[float]:
        del text
        raise NotImplementedError("Use Ollama for embeddings.")

    async def health_check(self) -> bool:
        try:
            token = await get_valid_token("openai", auto_login=False)
            if token is None or token.is_expired():
                return False
            # Validate that the account ID can be extracted
            _extract_chatgpt_account_id(token.access_token)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        pass

    async def list_models(self) -> tuple[str, ...]:
        # El endpoint de models público /v1/models no está disponible con tokens de Codex.
        # Por seguridad y velocidad, retornamos los modelos estáticos soportados oficialmente.
        return (
            "gpt-5.5",
            "gpt-5.5-pro",
            "gpt-5.4",
            "gpt-5.4-pro",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
        )

    @staticmethod
    def _headers_ws(access_token: str, account_id: str, req_id: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": account_id,
            "originator": "pi",
            "User-Agent": "pi (linux 6.5.0; x64)",
            "OpenAI-Beta": "responses_websockets=2026-02-06",
            "session-id": req_id,
            "x-client-request-id": req_id,
        }

    @staticmethod
    async def _iter_sse_events(response: Any) -> AsyncIterator[dict[str, Any]]:
        buffer: list[str] = []
        async for line in response.aiter_lines():
            if not line:
                if buffer:
                    data_lines = [raw[6:] for raw in buffer if raw.startswith("data: ")]
                    buffer.clear()
                    for data in data_lines:
                        if data == "[DONE]":
                            return
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(payload, dict):
                            yield payload
                continue
            buffer.append(line)
        if buffer:
            data_lines = [raw[6:] for raw in buffer if raw.startswith("data: ")]
            for data in data_lines:
                if data == "[DONE]":
                    return
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    yield payload

    @staticmethod
    def _extract_stream_text(
        event: dict[str, Any],
        *,
        allow_completed_text: bool = True,
    ) -> str:
        event_type = event.get("type")
        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            return delta if isinstance(delta, str) else ""
        if event_type == "response.completed" and allow_completed_text:
            response = event.get("response")
            if isinstance(response, dict):
                return OpenAIOAuthProvider._extract_output_text(response)
        if event_type == "error":
            raise ProviderError(str(event.get("message") or event.get("error") or "OpenAI OAuth stream error"))
        return ""

    @staticmethod
    def _extract_output_text(payload: dict[str, Any]) -> str:
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text

        chunks: list[str] = []
        output = payload.get("output")
        if not isinstance(output, list):
            return ""
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"output_text", "text"}:
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
        return "".join(chunks)

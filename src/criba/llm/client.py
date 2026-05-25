import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_TIMEOUT = 60


class OllamaClient:
    
    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        self._host = host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)
        self._model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        self._timeout = timeout or int(os.getenv("OLLAMA_TIMEOUT", str(DEFAULT_TIMEOUT)))
    
    async def analyze(self, prompt: str) -> dict | None:
        url = f"{self._host}/api/chat"
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
            },
        }
        
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                raw_response = data.get("message", {}).get("content", "")
                return json.loads(self._strip_thinking(raw_response))
        except json.JSONDecodeError:
            logger.warning("Ollama returned non-JSON response: %s", raw_response[:200])
            return None
        except httpx.HTTPError:
            logger.exception("Ollama HTTP error")
            return None
    
    @staticmethod
    def _strip_thinking(text: str) -> str:
        return re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.DOTALL).strip()
    
    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self._host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
    
    @property
    def model(self) -> str:
        return self._model

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
        # Precedence: explicit argument, then environment, then criba.yml,
        # then built-in defaults. A missing or broken criba.yml never breaks
        # the client: load_infra_config falls back to safe defaults.
        from criba.config import load_infra_config

        infra = load_infra_config().ollama
        self._host = host or os.getenv("OLLAMA_HOST") or infra.host
        self._model = model or os.getenv("OLLAMA_MODEL") or infra.model
        env_timeout = os.getenv("OLLAMA_TIMEOUT")
        self._timeout = timeout or (int(env_timeout) if env_timeout else infra.timeout)
    
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
        
        raw_response = ""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get("message"), dict):
                    raw_response = data["message"].get("content") or ""
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

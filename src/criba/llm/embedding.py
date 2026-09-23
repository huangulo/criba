import logging
import os

import httpx

logger = logging.getLogger(__name__)


class OllamaEmbeddingClient:

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "nomic-embed-text"
    DEFAULT_TIMEOUT = 30

    def __init__(self, host: str | None = None, model: str | None = None, timeout: int | None = None):
        # host/timeout follow param > env > criba.yml > defaults; the embed
        # model stays independent of the chat model configured in criba.yml.
        from criba.config import load_infra_config

        infra = load_infra_config().ollama
        self._host = host or os.getenv("OLLAMA_HOST") or infra.host
        self._model = model or os.getenv("OLLAMA_EMBED_MODEL") or self.DEFAULT_MODEL
        env_timeout = os.getenv("OLLAMA_TIMEOUT")
        self._timeout = timeout or (int(env_timeout) if env_timeout else infra.timeout)

    async def embed(self, text: str) -> list[float] | None:
        url = f"{self._host}/api/embed"
        payload = {
            "model": self._model,
            "input": text,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) > 0:
                    return embeddings[0]
                return None
        except (httpx.HTTPError, KeyError, IndexError):
            logger.exception("Ollama embedding error")
            return None

    async def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        results = []
        for text in texts:
            vec = await self.embed(text)
            results.append(vec)
        return results

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

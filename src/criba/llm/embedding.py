import logging
import os

import httpx

logger = logging.getLogger(__name__)


class OllamaEmbeddingClient:

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "nomic-embed-text"
    DEFAULT_TIMEOUT = 30

    def __init__(self, host: str | None = None, model: str | None = None, timeout: int | None = None):
        self._host = host or os.getenv("OLLAMA_HOST", self.DEFAULT_HOST)
        self._model = model or os.getenv("OLLAMA_EMBED_MODEL", self.DEFAULT_MODEL)
        self._timeout = timeout or int(os.getenv("OLLAMA_TIMEOUT", str(self.DEFAULT_TIMEOUT)))

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

from __future__ import annotations

import httpx


class OllamaClient:
    """
    Minimal HTTP client for Ollama's local API.

    We keep this small and explicit so behavior is auditable.
    """

    def __init__(self, base_url: str = "http://localhost:11434", timeout_s: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_s

    def embed(self, model: str, text: str) -> list[float]:
        """
        Create an embedding vector for the provided text.

        NOTE: Ollama embeddings endpoint expects {"model": "...", "prompt": "..."}.
        We also surface Ollama's error body if it fails (critical for debugging).
        """
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": model, "prompt": text}

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload)

        if resp.status_code >= 400:
            # Include Ollama's message to make failures actionable
            raise RuntimeError(f"Ollama embeddings failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        emb = data.get("embedding")
        if not isinstance(emb, list) or not emb:
            raise RuntimeError(f"Ollama embeddings returned unexpected payload: {data}")

        return emb

    def chat(self, model: str, messages: list[dict]) -> str:
        """
        Chat with an LLM using Ollama's /api/chat endpoint.
        """
        url = f"{self.base_url}/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload)

        if resp.status_code >= 400:
            raise RuntimeError(f"Ollama chat failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        return data["message"]["content"]

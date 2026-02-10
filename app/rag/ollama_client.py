from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class OllamaClient:
    """
    Minimal HTTP client for Ollama.

    We keep this small and explicit for auditability:
    - no frameworks
    - no hidden retries
    - no streaming (v1)
    """

    def __init__(self, base_url: str = "http://localhost:11434", timeout_s: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def embed(self, model: str, text: str) -> List[float]:
        """
        Create an embedding vector for the provided text using an Ollama embedding model.
        """
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": model, "prompt": text}

        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Ollama returns: {"embedding": [floats], ...}
        return data["embedding"]

    def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        seed: Optional[int] = 1,
    ) -> str:
        """
        Generate a completion from an Ollama model.

        For policy/government use, we default to deterministic-ish settings:
        - temperature=0
        - seed fixed (if the backend supports it)
        """
        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
            },
        }

        # Some runtimes/models honor seed; if ignored, it's harmless.
        if seed is not None:
            payload["options"]["seed"] = seed

        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return (data.get("response") or "").strip()

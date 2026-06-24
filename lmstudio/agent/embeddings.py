"""embeddings.py — LM Studio embedding client for vector memory."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_LM = "http://127.0.0.1:1234"


def _lm_base() -> str:
    return os.environ.get("LMSTUDIO_URL", DEFAULT_LM).rstrip("/")


def resolve_embedding_model(lm_base: str | None = None) -> str:
    """Pick a loaded embedding model, or fall back to first embedding in catalog."""
    lm = (lm_base or _lm_base()).rstrip("/")
    try:
        with urllib.request.urlopen(f"{lm}/api/v1/models", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        loaded = [
            m["key"] for m in data.get("models", [])
            if m.get("type") == "embedding" and m.get("loaded_instances")
        ]
        if loaded:
            return loaded[0]
        for m in data.get("models", []):
            if m.get("type") == "embedding":
                return m["key"]
    except Exception:  # noqa: BLE001
        pass

    with urllib.request.urlopen(f"{lm}/v1/models", timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for item in data.get("data", []):
        mid = item.get("id", "")
        if mid and "embed" in mid.lower():
            return mid
    raise RuntimeError(
        f"No embedding model found at {lm}. Load an embedding model in LM Studio."
    )


def embed_texts(
    texts: list[str],
    *,
    lm_base: str | None = None,
    model: str | None = None,
) -> list[list[float]]:
    """Return embedding vectors for each text via LM Studio OpenAI-compatible API."""
    if not texts:
        return []
    lm = (lm_base or _lm_base()).rstrip("/")
    resolved = model or os.environ.get("EMBEDDING_MODEL") or resolve_embedding_model(lm)
    body: dict[str, Any] = {"model": resolved, "input": texts}
    req = urllib.request.Request(
        f"{lm}/v1/embeddings",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Embedding request failed ({exc.code}): {detail}") from exc

    items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in items]

"""Optional local-LLM narration via Ollama.

Design note worth defending in a viva: no operational decision in this system
is made by an LLM. Prices come from a constrained optimisation, allocations
from CP-SAT, forecasts from XGBoost. The LLM's only job is to turn the
structured decisions the engines already made into readable prose for the
kitchen manager's briefing.

That separation is deliberate. It means the system is fully deterministic,
reproducible and auditable, and it degrades to templated summaries when Ollama
is not installed rather than failing.
"""
from __future__ import annotations

import json

import httpx

from app.config import OLLAMA_MODEL, OLLAMA_URL

_available: bool | None = None


def is_available() -> bool:
    """Probe Ollama once and cache the result."""
    global _available
    if _available is not None:
        return _available
    try:
        r = httpx.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=1.5)
        _available = r.status_code == 200
    except Exception:
        _available = False
    return _available


def narrate(prompt: str, fallback: str) -> dict:
    """Return {'text', 'source'} - LLM prose when available, template otherwise."""
    if not is_available():
        return {"text": fallback, "source": "template"}
    try:
        r = httpx.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.3, "num_predict": 220}},
            timeout=30.0,
        )
        r.raise_for_status()
        return {"text": r.json().get("response", "").strip() or fallback,
                "source": f"ollama:{OLLAMA_MODEL}"}
    except Exception:
        return {"text": fallback, "source": "template-fallback"}


def build_briefing_prompt(summary: dict) -> str:
    return (
        "You are the operations assistant for an institutional cafeteria. "
        "Write a concise 4-sentence morning briefing for the kitchen manager "
        "based strictly on this JSON. Do not invent numbers.\n\n"
        + json.dumps(summary, indent=2, default=str)
    )

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional


def _safe_json_loads(text: str) -> dict[str, Any]:
    """
    Strict parse → extract {...} → repair → parse.
    """
    try:
        return json.loads(text)
    except Exception:
        pass

    # Extract first JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    candidate = m.group(0) if m else text

    # Try strict parse of extracted candidate
    try:
        return json.loads(candidate)
    except Exception:
        pass

    # ✅ Repair malformed JSON (missing commas, trailing commas, etc.)
    try:
        from json_repair import repair_json
        repaired = repair_json(candidate)
        return json.loads(repaired)
    except Exception as e:
        raise ValueError(
            f"Model returned invalid JSON even after repair. "
            f"Repair error: {type(e).__name__}: {e}. "
            f"First 400 chars: {candidate[:400]!r}"
        )


@dataclass
class LLMConfig:
    provider: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 900
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None


class GeminiLLM:
    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        from google import genai
        from google.genai import types

        self._types = types
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate_json(self, system: str, user: str, schema_hint: str = "") -> dict[str, Any]:
        prompt = user if not schema_hint else f"{user}\n\nReturn JSON following this schema:\n{schema_hint}"

        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=[system],
                response_mime_type="application/json",
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )

        txt = resp.text or "{}"
        return _safe_json_loads(txt)


def build_llm(cfg: LLMConfig):
    provider = (cfg.provider or "").lower().strip()

    if provider == "gemini":
        if not cfg.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is missing. Add it to .env")
        return GeminiLLM(
            api_key=cfg.gemini_api_key,
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )

    raise ValueError(f"Unsupported llm provider: {cfg.provider}. Use provider: gemini")

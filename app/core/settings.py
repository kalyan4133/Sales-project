from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic_settings import BaseSettings


def _load_yaml_config() -> dict:
    root = Path(__file__).resolve().parents[2]  # project root
    cfg_path = root / "config.yaml"
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    # LLM
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3-flash-preview"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 900

    # API keys (optional)
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None  # keep optional to avoid crashes

    # Retrieval
    catalog_top_k: int = 5
    history_top_k: int = 5
    tfidf_max_features: int = 20000

    class Config:
        env_file = ".env"
        extra = "ignore"

    def __init__(self, **kwargs):
        cfg = _load_yaml_config()
        llm = (cfg.get("llm") or {})
        retrieval = (cfg.get("retrieval") or {})

        super().__init__(
            llm_provider=llm.get("provider", "gemini"),
            llm_model=llm.get("model", "gemini-3-flash-preview"),
            llm_temperature=llm.get("temperature", 0.2),
            llm_max_tokens=llm.get("max_tokens", 900),
            catalog_top_k=retrieval.get("catalog_top_k", 5),
            history_top_k=retrieval.get("history_top_k", 5),
            tfidf_max_features=retrieval.get("tfidf_max_features", 20000),
            **kwargs,
        )
    
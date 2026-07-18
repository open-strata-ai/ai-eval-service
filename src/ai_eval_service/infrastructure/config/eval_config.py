from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel


class EvalConfig(BaseModel):
    enabled: bool = True
    scorers: dict = {
        "promptfoo": {"enabled": True, "version": "0.90.0"},
        "deepeval": {"enabled": False, "version": "2.0.0"},
        "ragas": {"enabled": False, "version": "0.2.0"},
    }
    execution: dict = {"concurrency": 16, "backend": "threadpool"}
    storage: dict = {
        "postgres": {"dsn_env": "PGDSN"},
        "redis": {"enabled": True},
    }
    integrations: dict = {
        "agentRuntime": "langgraph",
        "llmProvider": ["qwen-cloud", "openai"],
        "vectorStore": "qdrant",
        "tracing": "langfuse",
    }

    @classmethod
    def from_env(cls) -> "EvalConfig":
        pg_dsn = os.environ.get("PGDSN")
        if pg_dsn:
            cfg = cls()
            cfg.storage["postgres"]["dsn_env"] = "PGDSN"
            return cfg
        return cls()

    @classmethod
    def load_eval_config(cls, path: Optional[str] = None) -> "EvalConfig":
        if path and os.path.exists(path):
            try:
                import yaml  # lazy

                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                # The fragment nests everything under an `eval:` key.
                if isinstance(data, dict) and "eval" in data:
                    data = data["eval"]
                return cls(**data)
            except ImportError:
                return cls()
        return cls()


def load_eval_config(path: Optional[str] = None) -> EvalConfig:
    """Module-level helper used by the DI container and config package."""
    return EvalConfig.load_eval_config(path)

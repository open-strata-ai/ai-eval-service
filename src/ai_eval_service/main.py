from __future__ import annotations

import os

from ai_eval_service.interface.rest.app import create_app

# EVAL_MODE env var: "memory" (default, offline) or "production" (Postgres+Redis).
mode = os.environ.get("EVAL_MODE", "memory")
app = create_app(mode=mode)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_eval_service.main:app", host="0.0.0.0", port=8000, reload=False)

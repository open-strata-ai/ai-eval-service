from __future__ import annotations

from ai_eval_service.interface.rest.app import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ai_eval_service.main:app", host="0.0.0.0", port=8000, reload=False)

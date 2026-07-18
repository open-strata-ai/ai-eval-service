from __future__ import annotations

from fastapi import FastAPI

from ai_eval_service.di.container import Container, build_container


def create_app(container: Container | None = None) -> FastAPI:
    """FastAPI app factory. Defaults to an offline ``memory`` container."""
    container = container or build_container(mode="memory")
    app = FastAPI(title="ai-eval-service", version="1.0.0")

    from ai_eval_service.interface.rest.routes import register_routes

    register_routes(app, container)
    app.state.container = container
    return app

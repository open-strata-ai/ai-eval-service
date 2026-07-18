from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai_eval_service.di.container import build_container
from ai_eval_service.interface.rest.app import create_app


@pytest.fixture
def container():
    return build_container(mode="memory")


@pytest.fixture
def client(container):
    return TestClient(create_app(container))

"""Shared test fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from servermanager.config import Settings  # noqa: E402


@pytest.fixture()
def settings() -> Settings:
    return Settings.from_env({})


@pytest.fixture()
def client(settings: Settings):
    from fastapi.testclient import TestClient

    from servermanager.web.app import create_app

    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def token_settings() -> Settings:
    return Settings.from_env({"SM_TOKEN": "test-token-12345"})


@pytest.fixture()
def token_client(token_settings: Settings):
    from fastapi.testclient import TestClient

    from servermanager.web.app import create_app

    with TestClient(create_app(token_settings)) as test_client:
        yield test_client

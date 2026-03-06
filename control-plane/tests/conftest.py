from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.endpoints import campaigns as campaigns_ep
from app.core.config import settings


@pytest.fixture(autouse=True)
def reset_campaign_state() -> Generator[None, None, None]:
    prev = settings.enable_memory_fallback
    settings.enable_memory_fallback = True
    campaigns_ep._CAMPAIGN_STORE.clear()
    campaigns_ep._CAMPAIGN_VERSION_STORE.clear()
    yield
    campaigns_ep._CAMPAIGN_STORE.clear()
    campaigns_ep._CAMPAIGN_VERSION_STORE.clear()
    settings.enable_memory_fallback = prev


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra" / "stub-app"))

from app.api import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    database_url = os.environ["DATABASE_URL"]
    subprocess.run(
        [sys.executable, "-m", "app.migrate"],
        cwd=ROOT / "infra" / "stub-app",
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
    )
    with TestClient(app) as test_client:
        yield test_client


def test_live_works_without_database(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_fails_without_database(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_migrated_database_is_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_catalog_matches_contract(client):
    response = client.get("/api/v1/catalog")
    assert response.status_code == 200
    assert response.json() == {
        "products": [
            {"sku": "KIT-100", "unit_price_cents": 1299},
            {"sku": "PART-200", "unit_price_cents": 599},
            {"sku": "PACK-300", "unit_price_cents": 249},
        ]
    }


def test_metrics_include_request_counter(client):
    client.get("/health/live")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "fulfillops_http_requests_total" in response.text

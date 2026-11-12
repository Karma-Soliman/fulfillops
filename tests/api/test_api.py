def test_health_endpoints(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

def test_health_ready_when_database_unavailable(client, monkeypatch):
    from api import main

    def raise_database_error():
        raise RuntimeError("Database unavailable")

    monkeypatch.setattr(main, "SessionLocal", raise_database_error)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}

def test_catalog(client):
    response = client.get("/api/v1/catalog")

    assert response.status_code == 200
    assert response.json() == {
        "products": [
            {"sku": "KIT-100", "unit_price_cents": 1299},
            {"sku": "PACK-300", "unit_price_cents": 249},
            {"sku": "PART-200", "unit_price_cents": 599},
        ]
    }


def test_inventory(client):
    response = client.get("/api/v1/inventory/KIT-100")

    assert response.status_code == 200
    assert response.json() == {
        "sku": "KIT-100",
        "available": 7,
    }


def test_unknown_inventory_sku(client):
    response = client.get("/api/v1/inventory/UNKNOWN-999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SKU_NOT_FOUND"


def test_create_order(client):
    response = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "test-order-001"},
        json={
            "customer_id": "CUST-042",
            "items": [{"sku": "KIT-100", "quantity": 1}],
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert "order_id" in response.json()

    inventory = client.get("/api/v1/inventory/KIT-100")
    assert inventory.json()["available"] == 6
def test_idempotent_order_replay(client):
    headers = {"Idempotency-Key": "replay-test-001"}
    payload = {
        "customer_id": "CUST-042",
        "items": [{"sku": "KIT-100", "quantity": 1}],
    }

    first = client.post("/api/v1/orders", headers=headers, json=payload)
    second = client.post("/api/v1/orders", headers=headers, json=payload)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["order_id"] == second.json()["order_id"]

    inventory = client.get("/api/v1/inventory/KIT-100")
    assert inventory.json()["available"] == 6


def test_idempotency_conflict(client):
    headers = {"Idempotency-Key": "conflict-test-001"}

    first = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "customer_id": "CUST-042",
            "items": [{"sku": "KIT-100", "quantity": 1}],
        },
    )

    second = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "customer_id": "CUST-042",
            "items": [{"sku": "PART-200", "quantity": 1}],
        },
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_invalid_quantity(client):
    response = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "invalid-quantity-001"},
        json={
            "customer_id": "CUST-042",
            "items": [{"sku": "KIT-100", "quantity": 0}],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_QUANTITY"


def test_invalid_sku(client):
    response = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "invalid-sku-001"},
        json={
            "customer_id": "CUST-042",
            "items": [{"sku": "UNKNOWN-999", "quantity": 1}],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SKU"


def test_insufficient_stock(client):
    response = client.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": "out-of-stock-001"},
        json={
            "customer_id": "CUST-042",
            "items": [{"sku": "KIT-100", "quantity": 8}],
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "OUT_OF_STOCK"

    inventory = client.get("/api/v1/inventory/KIT-100")
    assert inventory.json()["available"] == 7
def test_concurrent_idempotent_requests():
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from api.main import app

    headers = {"Idempotency-Key": "concurrent-test-001"}
    payload = {
        "customer_id": "CUST-042",
        "items": [{"sku": "KIT-100", "quantity": 1}],
    }

    def send_request(_):
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/orders",
                headers=headers,
                json=payload,
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(send_request, range(8)))

    assert all(status == 202 for status, _ in results)

    order_ids = {
        body["order_id"]
        for _, body in results
    }

    assert len(order_ids) == 1

    with TestClient(app) as test_client:
        inventory = test_client.get("/api/v1/inventory/KIT-100")

    assert inventory.json()["available"] == 6
def test_concurrent_orders_do_not_oversell():
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from api.main import app

    payload = {
        "customer_id": "CUST-STRESS",
        "items": [{"sku": "KIT-100", "quantity": 1}],
    }

    def send_request(index):
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/orders",
                headers={"Idempotency-Key": f"stock-race-{index:03d}"},
                json=payload,
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(send_request, range(8)))

    assert statuses.count(202) == 7
    assert statuses.count(409) == 1

    with TestClient(app) as test_client:
        inventory = test_client.get("/api/v1/inventory/KIT-100")

    assert inventory.json()["available"] == 0
def test_prometheus_metrics(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    metrics = response.text

    required_metrics = [
        "fulfillops_orders_created_total",
        "fulfillops_orders_failed_total",
        "fulfillops_worker_retries_total",
        "fulfillops_http_requests_total",
        "fulfillops_http_request_duration_seconds",
    ]

    for metric in required_metrics:
        assert metric in metrics

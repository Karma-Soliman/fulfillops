import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.database import engine
from api.main import app
from api.models import (
    IdempotencyKey,
    Job,
    OrderItem,
    Order,
    Inventory,
    Product,
)


@pytest.fixture(autouse=True)
def reset_test_database():
    database_name = engine.url.database

    if database_name != "fulfillops_test":
        pytest.fail(f"Tests must use fulfillops_test, not {database_name}")

    with engine.begin() as connection:
        connection.execute(delete(IdempotencyKey))
        connection.execute(delete(Job))
        connection.execute(delete(OrderItem))
        connection.execute(delete(Order))
        connection.execute(delete(Inventory))
        connection.execute(delete(Product))

        connection.execute(
            Product.__table__.insert(),
            [
                {"sku": "KIT-100", "unit_price_cents": 1299, "active": True},
                {"sku": "PART-200", "unit_price_cents": 599, "active": True},
                {"sku": "PACK-300", "unit_price_cents": 249, "active": True},
            ],
        )

        connection.execute(
            Inventory.__table__.insert(),
            [
                {"sku": "KIT-100", "quantity_on_hand": 7, "quantity_reserved": 0},
                {"sku": "PART-200", "quantity_on_hand": 12, "quantity_reserved": 0},
                {"sku": "PACK-300", "quantity_on_hand": 5, "quantity_reserved": 0},
            ],
        )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

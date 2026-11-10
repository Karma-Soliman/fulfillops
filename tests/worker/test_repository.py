import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker

from worker.repository import Claim, Repository


@pytest.fixture
def sessions():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for real PostgreSQL tests")
    parsed = make_url(url)
    if (os.getenv("APP_ENV") != "test" or parsed.drivername != "postgresql+psycopg"
        or not (parsed.database or "").startswith("fulfillops_test")):
        pytest.fail("Requires APP_ENV=test and dedicated fulfillops_test* PostgreSQL database")
    engine = create_engine(url)
    schema = "worker_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated_url = parsed.update_query_dict({"options": f"-csearch_path={schema}"})
    isolated = create_engine(isolated_url)
    try:
        # database configuration cannot leak between test cases.
        environment = dict(os.environ, DATABASE_URL=isolated_url.render_as_string(hide_password=False))
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       env=environment, cwd=Path(__file__).resolve().parents[2], check=True)
        models = automap_base()
        models.prepare(autoload_with=isolated)
        factory = sessionmaker(isolated)
        factory.models = models.classes
        yield factory
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def repository(sessions):
    m = sessions.models
    return Repository(sessions, m.jobs, m.orders, m.inventory, m.order_items)


def seed(sessions, quantities=None):
    quantities = quantities or {"KIT-100": 1}
    order_id, job_id = uuid4(), uuid4()
    m = sessions.models
    with sessions.begin() as session:
        total = 0
        for sku, quantity in quantities.items():
            inventory = session.get(m.inventory, sku)
            inventory.quantity_reserved += quantity
            price = session.get(m.products, sku).unit_price_cents
            total += price * quantity
        session.add(m.orders(id=order_id, customer_id="TEST", total_cents=total))
        session.flush()
        for sku, quantity in quantities.items():
            price = session.get(m.products, sku).unit_price_cents
            session.add(m.order_items(id=uuid4(), order_id=order_id, sku=sku,
                                      quantity=quantity, unit_price_cents=price))
        session.add(m.jobs(id=job_id, order_id=order_id))
    return order_id, job_id


def stock(sessions, sku="KIT-100"):
    with sessions() as session:
        row = session.get(sessions.models.inventory, sku)
        return row.quantity_on_hand, row.quantity_reserved


def test_completion_consumes_reservation_exactly_once(sessions):
    order_id, job_id = seed(sessions, {"KIT-100": 2, "PART-200": 1})
    repo = repository(sessions)
    claim = repo.claim("worker-test")
    assert claim is not None
    assert repo.complete(claim)
    assert not repo.complete(claim)
    assert repo.claim("other") is None
    with sessions() as session:
        order = session.get(sessions.models.orders, order_id)
        assert order.status == "completed"
        assert order.total_cents == 3197
        job = session.get(sessions.models.jobs, job_id)
        assert (job.status, job.attempts, job.lease_token) == ("completed", 1, None)
        assert job.locked_by is None and job.lease_expires_at is None
        assert order.updated_at >= order.created_at
    assert stock(sessions) == (5, 0)
    assert stock(sessions, "PART-200") == (11, 0)


def test_wrong_token_cannot_modify_order_or_inventory(sessions):
    order_id, job_id = seed(sessions)
    repo = repository(sessions)
    claim = repo.claim("worker-test")
    assert not repo.complete(Claim(job_id, order_id, uuid4(), claim.worker_id))
    with sessions() as session:
        assert session.get(sessions.models.orders, order_id).status == "processing"
    assert stock(sessions) == (7, 1)
    assert repo.complete(claim)


def test_expired_claim_cannot_complete(sessions):
    order_id, job_id = seed(sessions)
    repo = repository(sessions)
    claim = repo.claim("worker-test")
    with sessions.begin() as session:
        session.execute(text("UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = :id"), {"id": job_id})
    assert not repo.complete(claim)
    with sessions() as session:
        assert session.get(sessions.models.orders, order_id).status == "processing"
    assert stock(sessions) == (7, 1)


def test_inconsistent_reservation_rolls_back_all_completion(sessions):
    order_id, job_id = seed(sessions, {"KIT-100": 1, "PART-200": 1})
    repo = repository(sessions)
    claim = repo.claim("worker-test")
    with sessions.begin() as session:
        session.get(sessions.models.inventory, "PART-200").quantity_reserved = 0
    with pytest.raises(RuntimeError, match="Insufficient inventory reservation"):
        repo.complete(claim)
    assert stock(sessions) == (7, 1)
    assert stock(sessions, "PART-200") == (12, 0)
    with sessions() as session:
        assert session.get(sessions.models.orders, order_id).status == "processing"
        assert session.get(sessions.models.jobs, job_id).status == "processing"

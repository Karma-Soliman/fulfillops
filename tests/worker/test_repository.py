import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from .schema_double import Base, Inventory, Job, Order
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
    schema = "b2_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated_url = parsed.update_query_dict({"options": f"-csearch_path={schema}"})
    isolated = create_engine(isolated_url)
    try:
        # Only this test-owned disposable schema is created.
        Base.metadata.create_all(isolated)
        yield sessionmaker(isolated)
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def seed(sessions):
    order_id, job_id = str(uuid4()), str(uuid4())
    with sessions.begin() as session:
        session.add(Inventory(sku="KIT-100", unit_price_cents=1299, available=6))
        session.add(Order(id=order_id, customer_id="TEST", total_cents=1299))
        session.flush()
        session.add(Job(id=job_id, order_id=order_id))
    return order_id, job_id


def test_complete_persists_once_without_reserving_again(sessions):
    order_id, job_id = seed(sessions)
    repo = Repository(sessions, Job, Order)
    claim = repo.claim("worker-test")
    assert claim is not None
    assert repo.complete(claim)
    assert not repo.complete(claim)
    assert repo.claim("other") is None
    with sessions() as session:
        assert session.get(Order, order_id).status == "completed"
        job = session.get(Job, job_id)
        assert (job.status, job.attempts, job.lease_token) == ("completed", 1, None)
        assert session.get(Inventory, "KIT-100").available == 6


def test_wrong_token_cannot_modify_order(sessions):
    order_id, job_id = seed(sessions)
    repo = Repository(sessions, Job, Order)
    claim = repo.claim("worker-test")
    assert not repo.complete(Claim(job_id, order_id, str(uuid4()), claim.worker_id))
    with sessions() as session:
        assert session.get(Order, order_id).status == "processing"
    assert repo.complete(claim)


def test_expired_claim_cannot_complete(sessions):
    order_id, job_id = seed(sessions)
    repo = Repository(sessions, Job, Order)
    claim = repo.claim("worker-test")
    with sessions.begin() as session:
        session.execute(text("UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = :id"), {"id": job_id})
    assert not repo.complete(claim)
    with sessions() as session:
        assert session.get(Order, order_id).status == "processing"

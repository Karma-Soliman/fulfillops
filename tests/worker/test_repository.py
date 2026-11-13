import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError

from worker.repository import Claim, Repository
from worker.processor import process_claim


@pytest.fixture
def sessions():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for real PostgreSQL tests")
    parsed = make_url(url)
    if (
        os.getenv("APP_ENV") != "test"
        or parsed.drivername != "postgresql+psycopg"
        or not (parsed.database or "").startswith("fulfillops_test")
    ):
        pytest.fail(
            "Requires APP_ENV=test and dedicated fulfillops_test* PostgreSQL database"
        )
    engine = create_engine(url)
    schema = "worker_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated_url = parsed.update_query_dict(
        {
            "options": f"-csearch_path={schema} -cstatement_timeout=5000 -clock_timeout=3000"
        }
    )
    isolated = create_engine(isolated_url)
    try:
        # database configuration cannot leak between test cases.
        environment = dict(
            os.environ, DATABASE_URL=isolated_url.render_as_string(hide_password=False)
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=environment,
            cwd=Path(__file__).resolve().parents[2],
            check=True,
        )
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
            session.add(
                m.order_items(
                    id=uuid4(),
                    order_id=order_id,
                    sku=sku,
                    quantity=quantity,
                    unit_price_cents=price,
                )
            )
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
        session.execute(
            text(
                "UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = :id"
            ),
            {"id": job_id},
        )
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


def race(*operations):
    """Start independent worker calls together; propagate errors to pytest."""
    barrier = Barrier(len(operations))

    def invoke(operation):
        barrier.wait(timeout=5)
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(invoke, operation) for operation in operations]
        return [future.result(timeout=10) for future in futures]


def test_two_workers_claim_one_job_only_once(sessions):
    _, job_id = seed(sessions)
    first, second = repository(sessions), repository(sessions)
    claims = race(lambda: first.claim("worker-one"), lambda: second.claim("worker-two"))
    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].job_id == job_id
    with sessions() as session:
        job = session.get(sessions.models.jobs, job_id)
        assert job.attempts == 1
        assert job.locked_by == winners[0].worker_id
        assert job.lease_token == winners[0].token


def test_locked_job_is_skipped_without_blocking_other_work(sessions):
    _, locked_id = seed(sessions)
    _, eligible_id = seed(sessions)
    Job = sessions.models.jobs
    with sessions.begin() as owner:
        owner.scalar(select(Job).where(Job.id == locked_id).with_for_update())
        # The owner still holds its transaction open on a separate connection.
        with ThreadPoolExecutor(max_workers=1) as pool:
            claim = pool.submit(repository(sessions).claim, "other-worker").result(
                timeout=5
            )
        assert claim.job_id == eligible_id
        assert owner.get(Job, locked_id).attempts == 0


def test_two_workers_complete_different_orders_sharing_stock(sessions):
    first_order, _ = seed(sessions, {"KIT-100": 2, "PART-200": 1})
    second_order, _ = seed(sessions, {"PART-200": 2, "KIT-100": 1})
    first, second = repository(sessions), repository(sessions)
    claims = race(lambda: first.claim("worker-one"), lambda: second.claim("worker-two"))
    assert all(claim is not None for claim in claims)
    assert len({claim.job_id for claim in claims}) == 2
    assert race(
        lambda: first.complete(claims[0]), lambda: second.complete(claims[1])
    ) == [True, True]
    assert stock(sessions) == (4, 0)
    assert stock(sessions, "PART-200") == (9, 0)
    with sessions() as session:
        for order_id in (first_order, second_order):
            assert session.get(sessions.models.orders, order_id).status == "completed"


def test_simultaneous_completion_applies_business_effect_once(sessions):
    order_id, job_id = seed(sessions)
    first, second = repository(sessions), repository(sessions)
    claim = first.claim("worker-one")
    results = race(lambda: first.complete(claim), lambda: second.complete(claim))
    assert sorted(results) == [False, True]
    assert stock(sessions) == (6, 0)
    with sessions() as session:
        assert session.get(sessions.models.jobs, job_id).attempts == 1
        assert session.get(sessions.models.orders, order_id).status == "completed"


def test_replaced_claim_cannot_apply_business_effect(sessions):
    order_id, job_id = seed(sessions)
    first, second = repository(sessions), repository(sessions)
    stale = first.claim("worker-one")
    new_token = uuid4()
    # Simulate an atomic reclaim in the fixture. Automatic expired-job recovery
    # is later work; this test isolates protection against a replaced owner.
    with sessions.begin() as session:
        session.execute(
            text("""
            UPDATE jobs SET attempts = attempts + 1,
                locked_by = 'worker-two', lease_token = :token,
                lease_expires_at = clock_timestamp() + interval '10 seconds'
            WHERE id = :id
        """),
            {"token": new_token, "id": job_id},
        )
    current = Claim(job_id, order_id, new_token, "worker-two")
    assert not first.complete(stale)
    assert stock(sessions) == (7, 1)
    assert second.complete(current)
    assert not first.complete(stale)
    assert stock(sessions) == (6, 0)
    with sessions() as session:
        assert session.get(sessions.models.jobs, job_id).attempts == 2
        assert session.get(sessions.models.orders, order_id).status == "completed"


def expire(sessions, job_id):
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE jobs SET lease_expires_at = now() - interval '1 second' WHERE id = :id"
            ),
            {"id": job_id},
        )


def make_retry_due(sessions, job_id):
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE jobs SET available_at = now() - interval '1 second' WHERE id = :id"
            ),
            {"id": job_id},
        )


def test_expired_job_reclaimed_and_stale_worker_fenced(sessions):
    _, job_id = seed(sessions)
    repo = repository(sessions)
    stale = repo.claim("old")
    expire(sessions, job_id)
    current = repo.claim("new")
    assert current.job_id == stale.job_id and current.token != stale.token
    assert not repo.renew(stale)
    assert not repo.fail(stale)
    assert not repo.complete(stale)
    assert repo.complete(current)
    assert stock(sessions) == (6, 0)


def test_renew_extends_valid_lease_but_cannot_revive_expired_one(sessions):
    _, job_id = seed(sessions)
    repo = repository(sessions)
    claim = repo.claim("owner")
    with sessions() as session:
        before = session.get(sessions.models.jobs, job_id).lease_expires_at
    assert repo.renew(claim)
    with sessions() as session:
        assert session.get(sessions.models.jobs, job_id).lease_expires_at > before
    expire(sessions, job_id)
    assert not repo.renew(claim)


def test_poison_job_has_backoff_and_stops_after_three_attempts(sessions):
    order_id, job_id = seed(sessions)
    repo = repository(sessions)
    for attempt in range(1, 4):
        claim = repo.claim("worker")
        assert claim is not None
        assert repo.fail(claim, "secret must never be stored")
        with sessions() as session:
            job = session.get(sessions.models.jobs, job_id)
            assert job.attempts == attempt
            assert job.last_error == "processing_failed"
            assert job.lease_token is None
            if attempt < 3:
                assert job.status == "queued"
                assert (job.available_at - job.updated_at).total_seconds() == 2 ** (
                    attempt - 1
                )
            else:
                assert job.status == "failed"
                assert session.get(sessions.models.orders, order_id).status == "failed"
        assert repo.claim("too-soon") is None
        if attempt < 3:
            make_retry_due(sessions, job_id)
    assert repo.claim("fourth") is None
    assert stock(sessions) == (7, 1)


def test_retry_can_succeed_without_reserving_again(sessions):
    _, job_id = seed(sessions)
    repo = repository(sessions)
    assert repo.fail(repo.claim("first"))
    make_retry_due(sessions, job_id)
    assert repo.complete(repo.claim("second"))
    assert stock(sessions) == (6, 0)
    with sessions() as session:
        assert session.get(sessions.models.jobs, job_id).attempts == 2


def test_third_crashed_attempt_is_failed_without_fourth_claim(sessions):
    order_id, job_id = seed(sessions)
    repo = repository(sessions)
    for _ in range(3):
        assert repo.claim("crashing-worker") is not None
        expire(sessions, job_id)
    assert repo.claim("recovery-worker") is None
    assert repo.claim("fourth") is None
    with sessions() as session:
        job = session.get(sessions.models.jobs, job_id)
        assert (job.status, job.attempts) == ("failed", 3)
        assert job.last_error == "attempts_exhausted_after_interruption"
        assert job.lease_token is None
        assert session.get(sessions.models.orders, order_id).status == "failed"
    assert stock(sessions) == (7, 1)


def test_only_one_worker_reclaims_expired_job(sessions):
    _, job_id = seed(sessions)
    repository(sessions).claim("old")
    expire(sessions, job_id)
    results = race(
        lambda: repository(sessions).claim("new-one"),
        lambda: repository(sessions).claim("new-two"),
    )
    assert sum(claim is not None for claim in results) == 1
    with sessions() as session:
        assert session.get(sessions.models.jobs, job_id).attempts == 2


def test_killed_process_leaves_durable_recoverable_work(sessions):
    import selectors

    _, job_id = seed(sessions)
    url = sessions.kw["bind"].url.render_as_string(hide_password=False)
    code = """
import os, time
from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import sessionmaker
from worker.repository import Repository
engine = create_engine(os.environ['DATABASE_URL'])
models = automap_base()
models.prepare(autoload_with=engine)
m = models.classes
repo = Repository(sessionmaker(engine), m.jobs, m.orders, m.inventory, m.order_items)
claim = repo.claim('doomed-process')
assert claim is not None
print('CLAIM_COMMITTED', flush=True)
time.sleep(60)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        env=dict(os.environ, DATABASE_URL=url),
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), "Child did not commit its claim"
            assert child.stdout.readline().strip() == "CLAIM_COMMITTED"
        child.kill()
        child.wait(timeout=5)
        with sessions() as session:
            assert session.get(sessions.models.jobs, job_id).status == "processing"
        # Advance lease expiry in fixture SQL rather than slow wall-clock sleeps.
        expire(sessions, job_id)
        repo = repository(sessions)
        recovered = repo.claim("survivor")
        assert recovered.job_id == job_id
        assert repo.complete(recovered)
        assert not repo.complete(recovered)
        assert stock(sessions) == (6, 0)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdout.close()


def test_poison_processing_callback_reaches_durable_failure(sessions):
    order_id, job_id = seed(sessions)
    repo = repository(sessions)

    def poison(_claim):
        raise ValueError("deterministic test failure; never persist raw exception")

    for _ in range(3):
        claim = repo.claim("poison-worker")
        assert claim is not None
        assert process_claim(repo, claim, poison) == "failure_recorded"
        make_retry_due(sessions, job_id)
    assert repo.claim("fourth") is None
    with sessions() as session:
        job = session.get(sessions.models.jobs, job_id)
        assert (job.status, job.attempts, job.last_error) == (
            "failed",
            3,
            "processing_failed",
        )
        assert session.get(sessions.models.orders, order_id).status == "failed"
    assert stock(sessions) == (7, 1)


def test_persisted_lower_attempt_limit_is_respected(sessions):
    order_id, job_id = seed(sessions)
    with sessions.begin() as session:
        session.get(sessions.models.jobs, job_id).max_attempts = 1
    repo = repository(sessions)
    assert repo.fail(repo.claim("single-attempt"))
    assert repo.claim("extra-attempt") is None
    with sessions() as session:
        job = session.get(sessions.models.jobs, job_id)
        assert (job.status, job.attempts) == ("failed", 1)
        assert session.get(sessions.models.orders, order_id).status == "failed"
    assert stock(sessions) == (7, 1)


def test_backoff_is_capped_and_future_job_is_not_claimed(sessions):
    _, job_id = seed(sessions)
    repo = repository(sessions)
    repo.backoff_base, repo.backoff_max = 4, 5
    for expected_delay in (4, 5):
        claim = repo.claim("retry-worker")
        assert repo.fail(claim)
        with sessions() as session:
            job = session.get(sessions.models.jobs, job_id)
            assert (job.available_at - job.updated_at).total_seconds() == expected_delay
        assert repo.claim("early-worker") is None
        make_retry_due(sessions, job_id)


def test_completed_outcome_survives_new_engine_and_worker(sessions):
    order_id, job_id = seed(sessions)
    original = repository(sessions)
    claim = original.claim("before-restart")
    assert original.complete(claim)
    # A fresh engine has no pooled connections or ORM identity state in common.
    engine = create_engine(sessions.kw["bind"].url)
    try:
        models = automap_base()
        models.prepare(autoload_with=engine)
        m = models.classes
        restarted = Repository(
            sessionmaker(engine), m.jobs, m.orders, m.inventory, m.order_items
        )
        assert restarted.claim("after-restart") is None
        assert not restarted.complete(claim)
        with sessionmaker(engine)() as session:
            assert session.get(m.orders, order_id).status == "completed"
            assert session.get(m.jobs, job_id).attempts == 1
            inventory = session.get(m.inventory, "KIT-100")
            assert (inventory.quantity_on_hand, inventory.quantity_reserved) == (6, 0)
    finally:
        engine.dispose()


def test_database_failure_rolls_back_inventory_job_and_order(sessions):
    order_id, job_id = seed(sessions)
    repo = repository(sessions)
    claim = repo.claim("worker")
    with sessions.begin() as session:
        session.execute(
            text("""
            CREATE FUNCTION reject_completion() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.status = 'completed' THEN
                    RAISE EXCEPTION 'test-only completion failure';
                END IF;
                RETURN NEW;
            END $$
        """)
        )
        # Deferred until commit, after the ORM has sent ALL inventory/status writes.
        session.execute(
            text("""
            CREATE CONSTRAINT TRIGGER reject_completion_trigger
            AFTER UPDATE ON orders DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION reject_completion()
        """)
        )
    with pytest.raises(DBAPIError):
        repo.complete(claim)
    with sessions() as session:
        job = session.get(sessions.models.jobs, job_id)
        assert job.status == "processing" and job.lease_token == claim.token
        assert session.get(sessions.models.orders, order_id).status == "processing"
    assert stock(sessions) == (7, 1)


def test_lease_expiring_while_inventory_locked_cannot_complete(sessions):
    from threading import Event
    from sqlalchemy import event

    _, job_id = seed(sessions)
    repo = repository(sessions)
    repo.lease_seconds = 0.25
    claim = repo.claim("short-lease")
    waiting = Event()
    engine = sessions.kw["bind"]

    def observe_inventory_lock(_conn, _cursor, statement, _params, _context, _many):
        if "inventory" in statement.lower() and "FOR UPDATE" in statement:
            waiting.set()

    Inventory = sessions.models.inventory
    with sessions.begin() as blocker:
        blocker.scalar(
            select(Inventory).where(Inventory.sku == "KIT-100").with_for_update()
        )
        event.listen(engine, "before_cursor_execute", observe_inventory_lock)
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(repo.complete, claim)
        try:
            assert waiting.wait(2), "Completion did not reach inventory locking"
            # Real database-clock expiry, not an edited lease, while lock is held.
            blocker.execute(text("SELECT pg_sleep(0.35)"))
        finally:
            event.remove(engine, "before_cursor_execute", observe_inventory_lock)
            # Release the blocking lock before waiting for the worker thread.
            blocker.commit()
            pool.shutdown(wait=True)
    assert future.result(timeout=5) is False
    assert stock(sessions) == (7, 1)
    assert repository(sessions).complete(repository(sessions).claim("recovery"))
    assert stock(sessions) == (6, 0)


def test_worker_entry_point_completes_and_exits_on_sigterm(sessions):
    import json

    order_id, job_id = seed(sessions)
    url = sessions.kw["bind"].url.render_as_string(hide_password=False)
    child = subprocess.Popen(
        [sys.executable, "-m", "worker.main"],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(os.environ, DATABASE_URL=url, WORKER_METRICS_PORT="0"),
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        from time import monotonic

        deadline = monotonic() + 10
        # Inspect the durable state while stdout is reserved for JSON log checks.
        while monotonic() < deadline:
            with sessions() as session:
                if session.get(sessions.models.orders, order_id).status == "completed":
                    break
            import time

            time.sleep(0.02)
        else:
            pytest.fail("Worker did not complete order")
        child.terminate()
        assert child.wait(timeout=5) == 0
        logs = [json.loads(line) for line in child.stdout.read().splitlines()]
        completed = [record for record in logs if record["event"] == "job_completed"]
        assert len(completed) == 1 and completed[0]["job_id"] == str(job_id)
        assert logs[-1]["event"] == "worker_stopped"
        assert all("timestamp" in record and "level" in record for record in logs)
        with sessions() as session:
            assert session.get(sessions.models.orders, order_id).status == "completed"
        assert stock(sessions) == (6, 0)
        assert repository(sessions).claim("restarted-worker") is None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdout.close()


def test_heartbeat_allows_processing_beyond_original_lease(sessions):
    _, job_id = seed(sessions)
    repo = repository(sessions)
    repo.lease_seconds = 0.5
    claim = repo.claim("long-running-worker")
    with sessions() as session:
        original_expiry = session.get(sessions.models.jobs, job_id).lease_expires_at

    def prepare(_claim):
        with sessions() as session:
            session.execute(text("SELECT pg_sleep(0.8)"))
            assert session.scalar(select(text("clock_timestamp()"))) > original_expiry

    assert process_claim(repo, claim, prepare, renew_seconds=0.05) == "job_completed"
    assert stock(sessions) == (6, 0)


def test_metrics_track_committed_retry_and_completion_only(sessions):
    import io
    from worker.telemetry import Telemetry

    _, job_id = seed(sessions)
    telemetry = Telemetry("worker", stream=io.StringIO())
    repo = repository(sessions)
    repo.observer = telemetry.record
    claim = repo.claim("worker")
    assert repo.renew(claim)
    assert repo.fail(claim)
    make_retry_due(sessions, job_id)
    claim = repo.claim("worker")
    assert repo.complete(claim)
    assert not repo.complete(claim)
    assert not repo.fail(claim)
    assert telemetry.registry.get_sample_value("fulfillops_worker_claims_total") == 2
    assert telemetry.registry.get_sample_value("fulfillops_worker_retries_total") == 1
    assert (
        telemetry.registry.get_sample_value("fulfillops_worker_retries_scheduled_total")
        == 1
    )
    assert telemetry.registry.get_sample_value("fulfillops_worker_completed_total") == 1
    assert (
        telemetry.registry.get_sample_value("fulfillops_worker_lease_renewals_total")
        == 1
    )
    assert telemetry.registry.get_sample_value("fulfillops_orders_failed_total") == 0


def test_terminal_crash_failure_metric_is_emitted_once(sessions):
    import io
    from worker.telemetry import Telemetry

    _, job_id = seed(sessions)
    telemetry = Telemetry("worker", stream=io.StringIO())
    repo = repository(sessions)
    repo.observer = telemetry.record
    for _ in range(3):
        assert repo.claim("worker")
        expire(sessions, job_id)
    assert repo.claim("reaper") is None
    assert repo.claim("reaper") is None
    assert telemetry.registry.get_sample_value("fulfillops_orders_failed_total") == 1
    assert (
        telemetry.registry.get_sample_value("fulfillops_worker_recoveries_total") == 2
    )


def test_rolled_back_claim_does_not_emit_metric(sessions):
    import io
    from worker.telemetry import Telemetry

    seed(sessions)
    telemetry = Telemetry("worker", stream=io.StringIO())
    repo = repository(sessions)
    repo.observer = telemetry.record
    with pytest.raises(DBAPIError):
        # The overly long identity fails only when ORM changes flush at commit.
        repo.claim("x" * 129)
    assert telemetry.registry.get_sample_value("fulfillops_worker_claims_total") == 0
    assert telemetry.registry.get_sample_value("fulfillops_worker_retries_total") == 0


def test_telemetry_failure_cannot_undo_committed_completion(sessions):
    seed(sessions)
    repo = repository(sessions)

    def unavailable_observer(*_args, **_kwargs):
        raise OSError("output unavailable")

    repo.observer = unavailable_observer
    assert repo.complete(repo.claim("worker"))
    assert stock(sessions) == (6, 0)


def wait_until(predicate, timeout=10):
    from time import monotonic, sleep

    deadline = monotonic() + timeout
    while monotonic() < deadline:
        result = predicate()
        if result:
            return result
        sleep(0.02)
    pytest.fail("Timed out waiting for worker lifecycle condition")


def launch_worker(sessions, log_path):
    """Run the production entry point with no fake processor or repository."""
    log = log_path.open("w")
    environment = dict(
        os.environ,
        DATABASE_URL=sessions.kw["bind"].url.render_as_string(hide_password=False),
        WORKER_METRICS_PORT="0",
        WORKER_LEASE_SECONDS="4",
        WORKER_RENEW_INTERVAL_SECONDS="1",
        WORKER_POLL_INTERVAL_SECONDS="0.05",
        LOG_LEVEL="INFO",
    )
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", "worker.main"],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            stdout=log,
            stderr=log,
        )
    finally:
        log.close()
    return child


def worker_records(path):
    import json

    records = []
    for line in path.read_text().splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # A concurrent read can see a partial final line.
    return records


def stop_children(children):
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def test_two_real_workers_expose_health_and_recover_killed_peer(sessions, tmp_path):
    from urllib.request import urlopen
    import json

    order_one, _ = seed(sessions)
    order_two, _ = seed(sessions)
    children = []
    paths = [tmp_path / "worker-one.log", tmp_path / "worker-two.log"]
    Inventory, Job, Order = (
        sessions.models.inventory,
        sessions.models.jobs,
        sessions.models.orders,
    )
    try:
        # Pause completion without changing production code or editing lease times.
        with sessions.begin() as blocker:
            blocker.scalar(
                select(Inventory).where(Inventory.sku == "KIT-100").with_for_update()
            )
            children.extend(launch_worker(sessions, path) for path in paths)
            starts = []
            for path in paths:
                starts.append(
                    wait_until(
                        lambda path=path: next(
                            (
                                r
                                for r in worker_records(path)
                                if r["event"] == "worker_started"
                            ),
                            None,
                        )
                    )
                )
            assert starts[0]["worker_id"] != starts[1]["worker_id"]
            for start in starts:
                base = f"http://127.0.0.1:{start['metrics_port']}"
                with urlopen(base + "/health/live", timeout=2) as response:
                    assert json.load(response) == {"status": "ok"}
                with urlopen(base + "/metrics", timeout=2) as response:
                    assert "fulfillops_worker_claims_total" in response.read().decode()

            def both_claimed():
                with sessions() as session:
                    jobs = session.scalars(
                        select(Job).where(Job.status == "processing")
                    ).all()
                    return len(jobs) == 2 and len({job.locked_by for job in jobs}) == 2

            wait_until(both_claimed, timeout=3)
            children[0].kill()
            children[0].wait(timeout=3)

        # Inventory lock released. Survivor finishes and recovers its peer after
        # natural lease expiry; no fixture SQL advances lease_expires_at.
        def all_completed():
            with sessions() as session:
                return all(
                    session.get(Order, oid).status == "completed"
                    for oid in (order_one, order_two)
                )

        wait_until(all_completed, timeout=12)
        children[1].terminate()
        assert children[1].wait(timeout=5) == 0
        assert stock(sessions) == (5, 0)
        with sessions() as session:
            jobs = session.scalars(select(Job)).all()
            assert sorted(job.attempts for job in jobs) == [1, 2]
            assert all(job.status == "completed" for job in jobs)
        assert any(
            record["event"] == "job_claimed" and record["recovered"]
            for record in worker_records(paths[1])
        )
    finally:
        stop_children(children)


def test_sigterm_during_active_completion_finishes_without_claiming_more(
    sessions, tmp_path
):
    from time import monotonic

    seed(sessions)
    seed(sessions)
    log_path = tmp_path / "worker.log"
    children = []
    Job, Inventory = sessions.models.jobs, sessions.models.inventory
    try:
        with sessions.begin() as blocker:
            blocker.scalar(
                select(Inventory).where(Inventory.sku == "KIT-100").with_for_update()
            )
            child = launch_worker(sessions, log_path)
            children.append(child)

            def active_claim():
                return any(
                    record["event"] == "job_claimed"
                    for record in worker_records(log_path)
                )

            wait_until(active_claim, timeout=3)
            started = monotonic()
            child.terminate()
            # The active job must not be released while completion is blocked.
            with sessions() as session:
                jobs = session.scalars(select(Job)).all()
                assert sorted(job.status for job in jobs) == ["processing", "queued"]
                active = next(job for job in jobs if job.status == "processing")
                assert active.lease_token is not None
        assert child.wait(timeout=5) == 0
        assert monotonic() - started < 8
        assert stock(sessions) == (6, 1)
        with sessions() as session:
            assert sorted(job.status for job in session.scalars(select(Job))) == [
                "completed",
                "queued",
            ]
        assert worker_records(log_path)[-1]["event"] == "worker_stopped"
    finally:
        stop_children(children)

import signal
import threading
from time import perf_counter
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.exc import SQLAlchemyError

from worker.config import Config
from worker.processor import process_claim
from worker.repository import Repository
from worker.telemetry import HealthServer, Telemetry


def main():
    config = Config.from_env()
    worker_id = str(uuid4())
    telemetry = Telemetry(worker_id, level=config.log_level)
    server = HealthServer(telemetry, port=config.metrics_port)
    server.start()
    engine = create_engine(
        config.database_url, pool_size=config.pool_size, pool_pre_ping=True
    )
    stopping = threading.Event()
    signals = [signal.SIGTERM, signal.SIGINT]

    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)

    for sig in signals:
        signal.signal(sig, lambda *_: stopping.set())
    try:
        # Worker reflects shared tables; it never creates or migrates them.
        models = automap_base()
        try:
            models.prepare(autoload_with=engine)
        except SQLAlchemyError:
            telemetry.errors.labels(operation="startup").inc()
            telemetry.log("database_unavailable", severity="ERROR", operation="startup")
            raise SystemExit(1) from None
        repository = Repository(
            sessionmaker(engine),
            models.classes.jobs,
            models.classes.orders,
            models.classes.inventory,
            models.classes.order_items,
            config.lease_seconds,
            config.backoff_base,
            config.backoff_max,
            observer=telemetry.record,
        )
        telemetry.log("worker_started", metrics_port=server.server.server_port)
        while not stopping.is_set():
            try:
                claim = repository.claim(worker_id)
            except SQLAlchemyError:
                telemetry.errors.labels(operation="claim").inc()
                telemetry.log(
                    "database_unavailable", severity="ERROR", operation="claim"
                )
                stopping.wait(config.poll_seconds)
                continue
            if claim is None:
                stopping.wait(config.poll_seconds)
                continue
            started = perf_counter()
            telemetry.active.inc()
            outcome = "database_error_awaiting_recovery"
            try:
                outcome = process_claim(
                    repository,
                    claim,
                    renew_seconds=config.renew_seconds,
                    telemetry=telemetry,
                )
            except SQLAlchemyError:
                # Commit outcome may be uncertain: never replay effects blindly.
                telemetry.errors.labels(operation="processing").inc()
                telemetry.log(
                    "database_error_awaiting_recovery",
                    severity="ERROR",
                    job_id=claim.job_id,
                )
                stopping.wait(config.poll_seconds)
            finally:
                telemetry.active.dec()
                telemetry.duration.labels(outcome=outcome).observe(
                    perf_counter() - started
                )
            if outcome == "claim_lost":
                telemetry.lost.inc()
                telemetry.log("claim_lost", severity="WARNING", job_id=claim.job_id)
    finally:
        telemetry.log("worker_stopped")
        engine.dispose()
        server.close()


if __name__ == "__main__":
    main()

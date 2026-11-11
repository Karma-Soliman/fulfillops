import json
import signal
import threading
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.exc import SQLAlchemyError
from worker.config import Config
from worker.processor import process_claim
from worker.repository import Repository


def main():
    config = Config.from_env()
    engine = create_engine(config.database_url, pool_size=config.pool_size, pool_pre_ping=True)
    #worker never creates or migrates shared schema.
    models = automap_base()
    models.prepare(autoload_with=engine)
    repository = Repository(sessionmaker(engine), models.classes.jobs,
                            models.classes.orders, models.classes.inventory,
                            models.classes.order_items, config.lease_seconds,
                            config.backoff_base, config.backoff_max)
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    worker_id = str(uuid4())
    try:
        while not stopping.is_set():
            try:
                claim = repository.claim(worker_id)
            except SQLAlchemyError:
                print(json.dumps({"event": "database_unavailable"}), flush=True)
                stopping.wait(config.poll_seconds)
                continue
            if claim is None:
                stopping.wait(config.poll_seconds)
                continue
            try:
                outcome = process_claim(repository, claim, renew_seconds=config.renew_seconds)
            except SQLAlchemyError:
                # Commit outcome may be uncertain: never blindly replay its effects.
                outcome = "database_error_awaiting_recovery"
                stopping.wait(config.poll_seconds)
            print(json.dumps({"event": outcome,
                              "job_id": str(claim.job_id), "worker_id": worker_id}), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

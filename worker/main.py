import json
import signal
import threading
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from worker.config import Config
from worker.repository import Repository


def main():
    config = Config.from_env()
    engine = create_engine(config.database_url, pool_size=config.pool_size, pool_pre_ping=True)
    #worker never creates or migrates shared schema.
    models = automap_base()
    models.prepare(autoload_with=engine)
    repository = Repository(sessionmaker(engine), models.classes.jobs,
                            models.classes.orders, config.lease_seconds)
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    worker_id = str(uuid4())
    try:
        while not stopping.is_set():
            claim = repository.claim(worker_id)
            if claim is None:
                stopping.wait(0.25)
                continue
            completed = repository.complete(claim)
            print(json.dumps({"event": "job_completed" if completed else "claim_lost",
                              "job_id": claim.job_id, "worker_id": worker_id}), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

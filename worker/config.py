import os
from dataclasses import dataclass
from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Config:
    database_url: str
    lease_seconds: int = 10
    pool_size: int = 5
    renew_seconds: float = 3
    backoff_base: float = 1
    backoff_max: float = 8
    poll_seconds: float = 0.5
    metrics_port: int = 9100
    log_level: str = "INFO"

    @classmethod
    def from_env(cls):
        url = os.environ["DATABASE_URL"]
        if make_url(url).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        lease = int(os.getenv("WORKER_LEASE_SECONDS", "10"))
        pool = int(os.getenv("DB_POOL_SIZE", "5"))
        if lease < 1 or pool < 1:
            raise ValueError("Lease and pool size must be positive")
        renew = float(os.getenv("WORKER_RENEW_INTERVAL_SECONDS", "3"))
        base = float(os.getenv("WORKER_BACKOFF_BASE_SECONDS", "1"))
        maximum = float(os.getenv("WORKER_BACKOFF_MAX_SECONDS", "8"))
        poll = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "0.5"))
        import math
        if (not all(math.isfinite(x) for x in (renew, base, maximum, poll))
            or not 0 < renew < lease or not 0 < base <= maximum or poll <= 0):
            raise ValueError("Invalid renewal, backoff or polling configuration")
        if int(os.getenv("WORKER_MAX_ATTEMPTS", "3")) != 3:
            raise ValueError("The agreed worker attempt limit is three")
        port = int(os.getenv("WORKER_METRICS_PORT", "9100"))
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        if not 0 <= port <= 65535 or level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid worker metrics port or log level")
        return cls(url, lease, pool, renew, base, maximum, poll, port, level)

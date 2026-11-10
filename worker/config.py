import os
from dataclasses import dataclass
from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Config:
    database_url: str
    lease_seconds: int = 10
    pool_size: int = 5

    @classmethod
    def from_env(cls):
        url = os.environ["DATABASE_URL"]
        if make_url(url).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        lease = int(os.getenv("WORKER_LEASE_SECONDS", "10"))
        pool = int(os.getenv("DB_POOL_SIZE", "5"))
        if lease < 1 or pool < 1:
            raise ValueError("Lease and pool size must be positive")
        return cls(url, lease, pool)

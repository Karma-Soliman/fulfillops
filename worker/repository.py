from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import func, select


@dataclass(frozen=True)
class Claim:
    job_id: str
    order_id: str
    token: str
    worker_id: str


class Repository:
    def __init__(self, sessions, job_model, order_model, lease_seconds=10):
        self.sessions = sessions
        self.job_model = job_model
        self.order_model = order_model
        self.lease_seconds = lease_seconds

    def claim(self, worker_id):
        Job, Order = self.job_model, self.order_model
        with self.sessions.begin() as session:
            job = session.scalar(select(Job).where(
                Job.status == "queued", Job.available_at <= func.now(),
                Job.attempts < Job.max_attempts,
            ).order_by(Job.available_at, Job.id).with_for_update(skip_locked=True).limit(1))
            if job is None:
                return None
            order = session.get(Order, job.order_id, with_for_update=True)
            if order.status not in ("queued", "processing"):
                raise RuntimeError("Job/order state mismatch")
            now = session.scalar(select(func.now()))
            job.status = "processing"
            job.attempts += 1
            job.locked_by = worker_id
            job.lease_token = str(uuid4())
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.updated_at = now
            order.status = "processing"
            return Claim(job.id, job.order_id, job.lease_token, worker_id)

    def complete(self, claim):
        Job, Order = self.job_model, self.order_model
        with self.sessions.begin() as session:
            #timestamp verification.
            job = session.scalar(select(Job).where(Job.id == claim.job_id)
                                 .with_for_update(skip_locked=True))
            if job is None:
                return False
            order = session.scalar(select(Order).where(Order.id == job.order_id)
                                   .with_for_update(skip_locked=True))
            now = session.scalar(select(func.now()))
            if (order is None or job.order_id != claim.order_id
                or job.status != "processing" or job.lease_token != claim.token
                or job.locked_by != claim.worker_id or job.lease_expires_at <= now
                or order.status != "processing"):
                return False
            order.status = "completed"
            job.status = "completed"
            job.updated_at = now
            job.locked_by = job.lease_token = job.lease_expires_at = None
            return True

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy import and_, func, or_, select


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    order_id: UUID
    token: UUID
    worker_id: str


class Repository:
    def __init__(
        self,
        sessions,
        job_model,
        order_model,
        inventory_model,
        item_model,
        lease_seconds=10,
        backoff_base=1,
        backoff_max=8,
        observer=None,
    ):
        self.sessions = sessions
        self.job_model = job_model
        self.order_model = order_model
        self.inventory_model = inventory_model
        self.item_model = item_model
        self.lease_seconds = lease_seconds
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.observer = observer

    @contextmanager
    def _transaction(self):
        events = []
        with self.sessions.begin() as session:
            yield session, events
        # Transaction has committed. Telemetry failure cannot undo business state.
        if self.observer is not None:
            for event, fields in events:
                try:
                    self.observer(event, **fields)
                except Exception:
                    pass

    def claim(self, worker_id):
        Job, Order = self.job_model, self.order_model
        with self._transaction() as (session, events):
            job = session.scalar(
                select(Job)
                .where(
                    or_(
                        and_(Job.status == "queued", Job.available_at <= func.now()),
                        and_(
                            Job.status == "processing",
                            Job.lease_expires_at <= func.now(),
                        ),
                    ),
                )
                .order_by(Job.available_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            order = session.get(Order, job.order_id, with_for_update=True)
            if order is None or order.status not in ("queued", "processing"):
                raise RuntimeError("Job/order state mismatch")
            # Order locking may have waited; start the lease from current DB time.
            now = session.scalar(select(func.clock_timestamp()))
            if job.attempts >= min(job.max_attempts, 3):
                self._terminal(job, order, now, "attempts_exhausted_after_interruption")
                events.append(
                    (
                        "job_failed",
                        {
                            "job_id": job.id,
                            "attempt": job.attempts,
                            "reason": job.last_error,
                        },
                    )
                )
                return None
            recovered = job.status == "processing"
            if recovered:
                job.last_error = "lease_expired_before_completion"
            job.status = "processing"
            job.attempts += 1
            job.locked_by = worker_id
            job.lease_token = uuid4()
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.updated_at = now
            order.status = "processing"
            order.updated_at = now
            events.append(
                (
                    "job_claimed",
                    {
                        "job_id": job.id,
                        "order_id": order.id,
                        "attempt": job.attempts,
                        "recovered": recovered,
                    },
                )
            )
            return Claim(job.id, job.order_id, job.lease_token, worker_id)

    def complete(self, claim):
        Job, Order = self.job_model, self.order_model
        with self._transaction() as (session, events):
            # Ownership rows are locked without waiting.
            job = session.scalar(
                select(Job)
                .where(Job.id == claim.job_id)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return False
            order = session.scalar(
                select(Order)
                .where(Order.id == job.order_id)
                .with_for_update(skip_locked=True)
            )
            now = session.scalar(select(func.now()))
            if (
                order is None
                or job.order_id != claim.order_id
                or job.status != "processing"
                or job.lease_token != claim.token
                or job.locked_by != claim.worker_id
                or job.lease_expires_at <= now
                or order.status != "processing"
            ):
                return False
            Inventory, Item = self.inventory_model, self.item_model
            items = session.scalars(
                select(Item).where(Item.order_id == order.id).order_by(Item.sku)
            ).all()
            if not items:
                raise RuntimeError("Order has no fulfillment items")
            rows = []
            for item in items:
                inventory = session.scalar(
                    select(Inventory).where(Inventory.sku == item.sku).with_for_update()
                )
                if (
                    inventory is None
                    or item.quantity <= 0
                    or inventory.quantity_reserved < item.quantity
                    or inventory.quantity_on_hand < item.quantity
                ):
                    raise RuntimeError("Insufficient inventory reservation")
                rows.append((inventory, item.quantity))
            # now() is transaction-start time; clock_timestamp() avoids stale checks.
            now = session.scalar(select(func.clock_timestamp()))
            if job.lease_expires_at <= now:
                return False
            for inventory, quantity in rows:
                inventory.quantity_on_hand -= quantity
                inventory.quantity_reserved -= quantity
                inventory.updated_at = now
            order.status = "completed"
            order.updated_at = now
            job.status = "completed"
            job.updated_at = now
            job.locked_by = job.lease_token = job.lease_expires_at = None
            events.append(("job_completed", {"job_id": job.id, "order_id": order.id}))
            return True

    @staticmethod
    def _owns(job, claim, now):
        return (
            job is not None
            and job.order_id == claim.order_id
            and job.status == "processing"
            and job.locked_by == claim.worker_id
            and job.lease_token == claim.token
            and job.lease_expires_at > now
        )

    @staticmethod
    def _clear_lease(job):
        job.locked_by = job.lease_token = job.lease_expires_at = None

    def _terminal(self, job, order, now, error):
        job.status = order.status = "failed"
        job.last_error = error
        job.updated_at = order.updated_at = now
        self._clear_lease(job)

    def renew(self, claim):
        with self._transaction() as (session, events):
            job = session.scalar(
                select(self.job_model)
                .where(self.job_model.id == claim.job_id)
                .with_for_update(skip_locked=True)
            )
            now = session.scalar(select(func.clock_timestamp()))
            if not self._owns(job, claim, now):
                return False
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.updated_at = now
            events.append(("lease_renewed", {"job_id": job.id}))
            return True

    def fail(self, claim, error="processing_failed"):
        # Fixed categories only: exception strings can contain SQL or credentials.
        if error not in {"processing_failed", "inventory_invariant_failed"}:
            error = "processing_failed"
        with self._transaction() as (session, events):
            job = session.scalar(
                select(self.job_model)
                .where(self.job_model.id == claim.job_id)
                .with_for_update(skip_locked=True)
            )
            now = session.scalar(select(func.clock_timestamp()))
            if not self._owns(job, claim, now):
                return False
            order = session.scalar(
                select(self.order_model)
                .where(self.order_model.id == job.order_id)
                .with_for_update(skip_locked=True)
            )
            now = session.scalar(select(func.clock_timestamp()))
            if (
                order is None
                or order.status != "processing"
                or not self._owns(job, claim, now)
            ):
                return False
            if job.attempts >= min(job.max_attempts, 3):
                self._terminal(job, order, now, error)
                events.append(
                    (
                        "job_failed",
                        {"job_id": job.id, "attempt": job.attempts, "reason": error},
                    )
                )
            else:
                delay = min(
                    self.backoff_max, self.backoff_base * 2 ** (job.attempts - 1)
                )
                job.status = "queued"
                job.available_at = now + timedelta(seconds=delay)
                job.last_error = error
                job.updated_at = now
                self._clear_lease(job)
                events.append(
                    (
                        "retry_scheduled",
                        {
                            "job_id": job.id,
                            "attempt": job.attempts,
                            "delay_seconds": delay,
                            "reason": error,
                        },
                    )
                )
            return True

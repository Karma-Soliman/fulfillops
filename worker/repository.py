from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy import func, select


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    order_id: UUID
    token: UUID
    worker_id: str


class Repository:
    def __init__(self, sessions, job_model, order_model, inventory_model, item_model, lease_seconds=10):
        self.sessions = sessions
        self.job_model = job_model
        self.order_model = order_model
        self.inventory_model = inventory_model
        self.item_model = item_model
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
            if order is None or order.status not in ("queued", "processing"):
                raise RuntimeError("Job/order state mismatch")
            now = session.scalar(select(func.now()))
            job.status = "processing"
            job.attempts += 1
            job.locked_by = worker_id
            job.lease_token = uuid4()
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.updated_at = now
            order.status = "processing"
            order.updated_at = now
            return Claim(job.id, job.order_id, job.lease_token, worker_id)

    def complete(self, claim):
        Job, Order = self.job_model, self.order_model
        with self.sessions.begin() as session:
            # Ownership rows are locked without waiting.
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
            Inventory, Item = self.inventory_model, self.item_model
            items = session.scalars(select(Item).where(
                Item.order_id == order.id).order_by(Item.sku)).all()
            if not items:
                raise RuntimeError("Order has no fulfillment items")
            rows = []
            for item in items:
                inventory = session.scalar(select(Inventory).where(
                    Inventory.sku == item.sku).with_for_update())
                if (inventory is None or item.quantity <= 0
                    or inventory.quantity_reserved < item.quantity
                    or inventory.quantity_on_hand < item.quantity):
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
            return True

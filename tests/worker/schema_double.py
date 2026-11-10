"""TEST DOUBLE. Replace with A's migrations at integration.
"""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('queued','processing','completed','failed')"),
        CheckConstraint("total_cents >= 0"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    total_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (CheckConstraint("available >= 0"), CheckConstraint("unit_price_cents >= 0"))
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    available: Mapped[int] = mapped_column(Integer)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','processing','completed','failed')"),
        CheckConstraint("max_attempts BETWEEN 1 AND 3 AND attempts BETWEEN 0 AND max_attempts"),
        CheckConstraint("status <> 'processing' OR (locked_by IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)"),
        Index("ix_jobs_eligible", "status", "available_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="3")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(128))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

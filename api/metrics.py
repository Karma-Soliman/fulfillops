from prometheus_client import (
    CONTENT_TYPE_LATEST as CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    REGISTRY,
    generate_latest as generate_latest,
)
from prometheus_client.core import CounterMetricFamily

from sqlalchemy import text

from api.database import SessionLocal


http_requests = Counter(
    "fulfillops_http_requests_total",
    "Total number of HTTP requests.",
    ["method", "status"],
)

http_request_duration = Histogram(
    "fulfillops_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method"],
)


class DatabaseMetricsCollector:
    """Expose durable application and worker metrics from PostgreSQL."""

    def collect(self):
        orders_created = CounterMetricFamily(
            "fulfillops_orders_created",
            "Total number of orders created.",
        )

        failed_orders = CounterMetricFamily(
            "fulfillops_orders_failed",
            "Total number of orders that failed.",
        )

        worker_retries = CounterMetricFamily(
            "fulfillops_worker_retries",
            "Total number of worker retries.",
        )

        with SessionLocal() as db:
            created_count = db.execute(text("SELECT COUNT(*) FROM orders")).scalar_one()

            failed_count = db.execute(
                text("SELECT COUNT(*) FROM orders WHERE status = 'failed'")
            ).scalar_one()

            retry_count = db.execute(
                text(
                    """
                    SELECT COALESCE(
                        SUM(GREATEST(attempts - 1, 0)),
                        0
                    )
                    FROM jobs
                    """
                )
            ).scalar_one()

        orders_created.add_metric([], created_count)
        failed_orders.add_metric([], failed_count)
        worker_retries.add_metric([], retry_count)

        yield orders_created
        yield failed_orders
        yield worker_retries


REGISTRY.register(DatabaseMetricsCollector())

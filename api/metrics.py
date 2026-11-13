from prometheus_client import Counter, Histogram
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest  # noqa: F401  # re-exported for api.main

orders_created = Counter(
    "fulfillops_orders_created_total", "Total number of orders successfully created."
)

orders_failed = Counter(
    "fulfillops_orders_failed_total", "Total number of orders that failed."
)

worker_retries = Counter(
    "fulfillops_worker_retries_total", "Total number of worker retries."
)

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

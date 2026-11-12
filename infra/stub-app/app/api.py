import json
import logging
import os
import time
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=__import__("sys").stdout
)
logger = logging.getLogger("fulfillops.stub")
REGISTRY = CollectorRegistry()
REQUESTS = Counter(
    "fulfillops_http_requests_total",
    "HTTP requests",
    ("method", "route", "status"),
    registry=REGISTRY,
)
LATENCY = Histogram(
    "fulfillops_http_request_duration_seconds",
    "HTTP request latency",
    ("method", "route"),
    registry=REGISTRY,
)
CATALOG = {
    "products": [
        {"sku": "KIT-100", "unit_price_cents": 1299},
        {"sku": "PART-200", "unit_price_cents": 599},
        {"sku": "PACK-300", "unit_price_cents": 249},
    ]
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def observe_request(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_name = getattr(route, "path", "unmatched")
        elapsed = time.perf_counter() - started
        REQUESTS.labels(request.method, route_name, str(status)).inc()
        LATENCY.labels(request.method, route_name).observe(elapsed)
        logger.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_seconds": elapsed,
                    "hostname": os.getenv("HOSTNAME", "unknown"),
                }
            )
        )


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return Response(
            '{"status":"not_ready"}', status_code=503, media_type="application/json"
        )
    try:
        database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(database_url, connect_timeout=1) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
                )
                migrated = cursor.fetchone()[0]
        if migrated:
            return {"status": "ready"}
    except psycopg.Error:
        pass
    return Response(
        '{"status":"not_ready"}', status_code=503, media_type="application/json"
    )


@app.get("/api/v1/catalog")
def catalog():
    return CATALOG


@app.get("/metrics")
def metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

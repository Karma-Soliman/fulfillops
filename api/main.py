import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, text

from api.database import SessionLocal
from api.metrics import (
    CONTENT_TYPE_LATEST,
    http_requests,
    http_request_duration,
    generate_latest,
)
from api.models import Product, Inventory
from api.orders import router as orders_router
from alembic.config import Config
from alembic.script import ScriptDirectory


app = FastAPI(title="FulfillOps API", version="1.0.0")
app.include_router(orders_router)


# HTTP request metrics middleware


@app.middleware("http")
async def collect_http_metrics(request: Request, call_next):
    start_time = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.perf_counter() - start_time

        http_requests.labels(
            method=request.method,
            status=str(status_code),
        ).inc()

        http_request_duration.labels(
            method=request.method,
        ).observe(duration)


# Standard error responses


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    detail = exc.detail

    if isinstance(detail, dict):
        error = detail
    else:
        error = {
            "code": "HTTP_ERROR",
            "message": str(detail),
        }

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error},
    )


def get_migration_heads():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    return set(script.get_heads())


# Health endpoints


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))

        result = (
            db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        )

        if set(result) != get_migration_heads():
            raise RuntimeError("Database migrations are not up to date.")

        return {"status": "ready"}

    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NOT_READY",
                "message": "The service is not ready to accept orders.",
            },
        )


# Catalog endpoint


@app.get("/api/v1/catalog")
def get_catalog():
    with SessionLocal() as db:
        products = db.scalars(
            select(Product).where(Product.active.is_(True)).order_by(Product.sku)
        ).all()

        return {
            "products": [
                {
                    "sku": product.sku,
                    "unit_price_cents": product.unit_price_cents,
                }
                for product in products
            ]
        }


# Inventory endpoint
@app.get("/api/v1/inventory/{sku}")
def get_inventory(sku: str):
    with SessionLocal() as db:
        inventory = db.get(Inventory, sku)

        if inventory is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "SKU_NOT_FOUND",
                    "message": "The requested SKU does not exist.",
                },
            )

        available = inventory.quantity_on_hand - inventory.quantity_reserved

        return {
            "sku": inventory.sku,
            "available": available,
        }


# Prometheus metrics endpoint


@app.get("/metrics")
def get_metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

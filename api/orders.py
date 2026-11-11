
import hashlib
import json
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select, text

from api.database import SessionLocal
from api.metrics import orders_created
from api.models import (
    IdempotencyKey,
    Inventory,
    Job,
    Order,
    OrderItem,
    Product,
)
from api.schemas import OrderCreateRequest


router = APIRouter()


def raise_api_error(status_code: int, code: str, message: str):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


@router.post("/api/v1/orders", status_code=202)
async def create_order(
    request: Request,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    # Check the required idempotency header.
    if idempotency_key is None:
        raise_api_error(
            400,
            "IDEMPOTENCY_REQUIRED",
            "The Idempotency-Key header is required.",
        )

    if (
        not 8 <= len(idempotency_key) <= 128
        or any(ord(char) < 32 or ord(char) > 126 for char in idempotency_key)
    ):
        raise_api_error(
            400,
            "IDEMPOTENCY_REQUIRED",
            "The Idempotency-Key must contain 8 to 128 printable ASCII characters.",
        )

    # Read and validate the request body.
    body = await request.body()

    if len(body) > 16 * 1024:
        raise_api_error(
            400,
            "INVALID_REQUEST",
            "The request body must not exceed 16 KiB.",
        )

    try:
        body_text = body.decode("utf-8")
        body_data = json.loads(body_text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise_api_error(
            400,
            "INVALID_JSON",
            "The request body must contain valid UTF-8 JSON.",
        )

    try:
        order_request = OrderCreateRequest.model_validate(body_data)
    except ValidationError as exc:
        errors = exc.errors()
        locations = [error["loc"] for error in errors]

        if any("quantity" in location for location in locations):
            raise_api_error(
                422,
                "INVALID_QUANTITY",
                "Each quantity must be an integer between 1 and 20.",
            )

        if any("sku" in location for location in locations):
            raise_api_error(
                422,
                "INVALID_SKU",
                "One or more SKUs are invalid.",
            )

        raise_api_error(
            400,
            "INVALID_REQUEST",
            "The order request has an invalid structure.",
        )

    # Combine repeated SKU lines and sort them for stable normalization.
    quantities = {}

    for item in order_request.items:
        quantities[item.sku] = quantities.get(item.sku, 0) + item.quantity

    normalized_items = [
        {"sku": sku, "quantity": quantity}
        for sku, quantity in sorted(quantities.items())
    ]

    normalized_payload = {
        "customer_id": order_request.customer_id,
        "items": normalized_items,
    }

    payload_hash = hashlib.sha256(
        json.dumps(
            normalized_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    # Perform idempotency, stock reservation and order creation
    # in one database transaction.
    new_order_created = False

    with SessionLocal() as db:
        with db.begin():
            # Serialize requests using the same idempotency key.
            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
                ),
                {"key": idempotency_key},
            )

            existing_key = db.get(IdempotencyKey, idempotency_key)

            if existing_key is not None:
                if existing_key.payload_hash != payload_hash:
                    raise_api_error(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "This idempotency key was already used with a different request.",
                    )

                order_id = existing_key.order_id

            else:
                # Lock inventory rows in sorted SKU order.
                inventory_rows = db.execute(
                    select(Inventory, Product)
                    .join(Product, Product.sku == Inventory.sku)
                    .where(Inventory.sku.in_(list(quantities.keys())))
                    .order_by(Inventory.sku)
                    .with_for_update(of=Inventory)
                ).all()

                inventory_by_sku = {
                    inventory.sku: (inventory, product)
                    for inventory, product in inventory_rows
                }

                if len(inventory_by_sku) != len(quantities):
                    raise_api_error(
                        422,
                        "INVALID_SKU",
                        "One or more SKUs are not available in the catalog.",
                    )

                # Check every requested item before reserving stock.
                for sku, quantity in quantities.items():
                    inventory, product = inventory_by_sku[sku]

                    if not product.active:
                        raise_api_error(
                            422,
                            "INVALID_SKU",
                            "One or more SKUs are not available in the catalog.",
                        )

                    available = (
                        inventory.quantity_on_hand
                        - inventory.quantity_reserved
                    )

                    if available < quantity:
                        raise_api_error(
                            409,
                            "OUT_OF_STOCK",
                            "Not enough items available.",
                        )

                # Calculate the total using current catalog prices.
                total_cents = sum(
                    quantity * inventory_by_sku[sku][1].unit_price_cents
                    for sku, quantity in quantities.items()
                )

                # Create the order.
                order = Order(
                    customer_id=order_request.customer_id,
                    status="queued",
                    total_cents=total_cents,
                )
                db.add(order)
                db.flush()

                order_id = order.id
                new_order_created = True

                # Reserve stock and save price snapshots.
                for sku, quantity in quantities.items():
                    inventory, product = inventory_by_sku[sku]

                    inventory.quantity_reserved += quantity

                    db.add(
                        OrderItem(
                            order_id=order_id,
                            sku=sku,
                            quantity=quantity,
                            unit_price_cents=product.unit_price_cents,
                        )
                    )

                # Create one queued worker job for this order.
                db.add(
                    Job(
                        order_id=order_id,
                        status="queued",
                        attempts=0,
                        max_attempts=3,
                    )
                )

                # Persist the idempotency mapping.
                db.add(
                    IdempotencyKey(
                        key=idempotency_key,
                        payload_hash=payload_hash,
                        order_id=order_id,
                    )
                )

        # The transaction has committed successfully here.

    # Count only genuinely new, successfully committed orders.
    if new_order_created:
        orders_created.inc()

    return {
        "order_id": str(order_id),
        "status": "queued",
    }


@router.get("/api/v1/orders/{order_id}")
def get_order(order_id: str):
    try:
        parsed_order_id = uuid.UUID(order_id)
    except ValueError:
        raise_api_error(
            404,
            "ORDER_NOT_FOUND",
            "The requested order does not exist.",
        )

    with SessionLocal() as db:
        order = db.get(Order, parsed_order_id)

        if order is None:
            raise_api_error(
                404,
                "ORDER_NOT_FOUND",
                "The requested order does not exist.",
            )

        return {
            "order_id": str(order.id),
            "status": order.status,
            "total_cents": order.total_cents,
        }

# FulfillOps – Integration Contract

## 1. Database Schema and Ownership

**Owner: Peushi – API and Database**

The application uses PostgreSQL as its shared source of truth. The database contains six core tables:

- `products`
- `inventory`
- `orders`
- `order_items`
- `idempotency_keys`
- `jobs`

### 1.1 Products

Stores the product catalogue.

| Column | Type | Rules |
|---|---|---|
| sku | VARCHAR(32) | Primary key |
| unit_price_cents | INTEGER | NOT NULL, greater than 0 |
| active | BOOLEAN | NOT NULL |
| created_at | TIMESTAMP | NOT NULL |
| updated_at | TIMESTAMP | NOT NULL |

Initial catalogue:

| SKU | Unit price |
|---|---:|
| KIT-100 | 1299 cents |
| PART-200 | 599 cents |
| PACK-300 | 249 cents |

### 1.2 Inventory

Stores stock quantities for each product.

| Column | Type | Rules |
|---|---|---|
| sku | VARCHAR(32) | Primary key, foreign key to products.sku |
| quantity_on_hand | INTEGER | NOT NULL, greater than or equal to 0 |
| quantity_reserved | INTEGER | NOT NULL, greater than or equal to 0 |
| updated_at | TIMESTAMP | NOT NULL |

Constraints:

- `quantity_reserved` must not exceed `quantity_on_hand`.
- Available stock is calculated as `quantity_on_hand - quantity_reserved`.
- Available stock must never be negative.

Initial inventory:

| SKU | Quantity on hand | Quantity reserved | Available |
|---|---:|---:|---:|
| KIT-100 | 7 | 0 | 7 |
| PART-200 | 12 | 0 | 12 |
| PACK-300 | 5 | 0 | 5 |

### 1.3 Orders

Stores accepted customer orders.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| customer_id | VARCHAR(64) | NOT NULL |
| status | VARCHAR(20) | NOT NULL |
| total_cents | INTEGER | NOT NULL, greater than or equal to 0 |
| created_at | TIMESTAMP | NOT NULL |
| updated_at | TIMESTAMP | NOT NULL |

Allowed statuses:

- `queued`
- `processing`
- `completed`
- `failed`

An order is created with status `queued`.

### 1.4 Order Items

Stores the individual products belonging to an order.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| order_id | UUID | Foreign key to orders.id |
| sku | VARCHAR(32) | Foreign key to products.sku |
| quantity | INTEGER | Between 1 and 200 |
| unit_price_cents | INTEGER | NOT NULL, greater than 0 |

A unique constraint on `(order_id, sku)` prevents duplicate SKU rows within the same order.

Each incoming request line is validated with a quantity between 1 and 20. A request can contain up to 10 lines. Duplicate SKU lines are aggregated before storage, so the aggregated quantity for one SKU can reach 200.

The unit price is stored as a snapshot when the order is created. Later catalogue price changes must not modify existing orders.

### 1.5 Idempotency Keys

Stores idempotency information for order creation.

| Column | Type | Rules |
|---|---|---|
| key | VARCHAR(128) | Primary key |
| payload_hash | VARCHAR(64) | NOT NULL |
| order_id | UUID | Foreign key to orders.id, UNIQUE |
| created_at | TIMESTAMP | NOT NULL |

Rules:

- The same idempotency key and same normalized request payload must return the original order.
- The same key with a different normalized payload must return a conflict.
- Idempotency information must persist in PostgreSQL.
- It must not rely on in-memory dictionaries or process-local state.

### 1.6 Jobs

Stores background work associated with accepted orders.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| order_id | UUID | Foreign key to orders.id, UNIQUE |
| status | VARCHAR(20) | NOT NULL |
| attempts | INTEGER | NOT NULL, default 0 |
| max_attempts | INTEGER | NOT NULL, default 3 |
| available_at | TIMESTAMP | NOT NULL |
| locked_by | VARCHAR(128) | Nullable |
| lease_token | UUID | Nullable |
| lease_expires_at | TIMESTAMP | Nullable |
| last_error | TEXT | Nullable |
| created_at | TIMESTAMP | NOT NULL |
| updated_at | TIMESTAMP | NOT NULL |

Allowed statuses:

- `queued`
- `processing`
- `completed`
- `failed`

Rules:

- Each order has at most one job.
- A new job starts with status `queued` and zero attempts.
- A job can only be claimed when it is available.
- A processing job must have a worker identity, lease token, and lease expiration.
- A job that is not processing must not retain active lease fields.
- Attempts must never exceed `max_attempts`.

### 1.7 Indexes

The database should support the main lookup and worker-claim operations with indexes on:

- `orders(status, created_at)`
- `order_items(order_id)` (the unique `(order_id, sku)` index also supports lookups by its leading `order_id` column)
- `jobs(status, available_at)`
- `jobs(status, lease_expires_at)`
- `idempotency_keys(order_id)`

## 2. API and Database Transaction Contract

**Owner: Person A – API and Database**

### 2.1 Order Creation

Endpoint:

`POST /api/v1/orders`

The API must validate the request before creating an order.

Validation rules:

- `customer_id` must be non-empty and no longer than 64 characters.
- `items` must contain between 1 and 10 lines.
- Each SKU must exist and be active.
- Each incoming line quantity must be an integer between 1 and 20.
- The request body must not exceed 16 KiB.
- Duplicate SKU lines must be aggregated before stock checks and order-item storage.

### 2.2 Atomic Order Creation

The following operations must happen inside one database transaction:

1. Validate and normalize the request.
2. Check whether the idempotency key already exists.
3. If the key exists with the same normalized payload, return the original order.
4. If the key exists with a different payload, return a conflict.
5. Aggregate quantities for duplicate SKUs.
6. Lock the relevant inventory rows in deterministic SKU order.
7. Verify that sufficient available stock exists for every SKU.
8. Increase `quantity_reserved` for each requested SKU.
9. Create the order with status `queued`.
10. Create the corresponding order items with price snapshots.
11. Store the idempotency key and normalized payload hash.
12. Create one queued job for the order.
13. Commit the transaction.

The API must return HTTP `202 Accepted` only after the transaction commits successfully.

If any operation fails, the transaction must roll back. No partial order, reservation, idempotency record, or job should remain.

### 2.3 Inventory Reservation

Stock is reserved when an order is accepted, not when the worker finishes processing it.

For example:

- Initial stock: 7
- Reserved stock: 0
- Available stock: 7

After accepting an order for 2 units:

- Quantity on hand: 7
- Quantity reserved: 2
- Available stock: 5

When the worker successfully completes the order:

- Quantity on hand decreases by 2.
- Quantity reserved decreases by 2.
- Available stock remains 5.

If an order fails, its reservation remains in place for operator review. The worker must not automatically release or restore reserved stock.

Worker retries and crashes must never reserve stock again.

### 2.4 Concurrent Requests

Inventory reservations must be safe under concurrent requests.

The API must use database-level locking and transactional updates to prevent overselling. Two concurrent requests must not both reserve the same remaining stock.

Process-local locks are not sufficient.

### 2.5 Catalogue and Inventory Endpoints

`GET /api/v1/catalog`

- Returns the three initial catalogue SKUs and their prices.
- Additional response fields are allowed.

`GET /api/v1/inventory/{sku}`

- Returns the available quantity for the requested SKU.
- The returned quantity must be a non-negative integer.

### 2.6 Database Seeding

The initial catalogue and inventory must be inserted through the database migration or another controlled one-time initialization process.

Seeding must not happen every time the API starts.

Repeated application restarts must not restore stock that has already been reserved or consumed.

Tests and destructive operations must use an isolated test database, never the development or production database.

## 3. Worker and Job Contract

**Owner: Person B – Worker**

### 3.1 Job Claiming

The worker claims jobs directly from PostgreSQL.

A job is eligible for claiming when:

- Its status is `queued` and `available_at` is in the past or equal to the current database time; or
- Its status is `processing` but its lease has expired.

Claiming must be atomic. The worker should use PostgreSQL row locking with `FOR UPDATE SKIP LOCKED` so multiple workers cannot claim the same job simultaneously.

The worker must use PostgreSQL time (`now()`) for lease comparisons.

### 3.2 Lease Policy

Agreed initial lease settings:

- Lease duration: 10 seconds.
- Lease renewal interval: approximately 3 seconds.
- Maximum attempts: 3 total attempts.

On every claim or reclaim:

- Increment the attempts counter.
- Set status to `processing`.
- Set `locked_by` to the worker identity.
- Generate a new lease token.
- Set `lease_expires_at` to the new expiration time.

A worker may renew its lease while it still owns the job.

### 3.3 Lease Ownership

The lease token identifies the current claim.

A worker must verify that its lease token is still valid before finalizing a job.

A worker whose lease has expired or whose token has been replaced must not finalize the job or modify its order and inventory.

This prevents an old worker from overwriting the result of a newer worker.

### 3.4 Retry and Crash Recovery

If a worker crashes while processing a job, the lease eventually expires.

Another worker can then reclaim the job if attempts remain.

The attempts counter includes claims and reclaims, including claims where the worker crashed.

If the third attempt also crashes or fails, the job must eventually become `failed` after its lease expires or its failure is recorded.

There must not be a fourth attempt.

### 3.5 Successful Completion

On successful processing, the worker must:

1. Verify lease ownership using the current lease token.
2. Mark the job as `completed`.
3. Mark the order as `completed`.
4. Decrease `quantity_on_hand` by the ordered quantity.
5. Decrease `quantity_reserved` by the same quantity.
6. Clear the lease fields.

The job, order, and inventory updates must happen in one database transaction.

### 3.6 Failed Completion

When a job reaches its maximum attempts and cannot be completed:

- Mark the job as `failed`.
- Mark the order as `failed`.
- Record the last error where possible.
- Clear the lease fields.
- Keep the inventory reservation unchanged.

The worker must not automatically restock failed orders.

Job and order status updates must be transactional.

## 4. Shared Integration Rules

All components must follow these rules:

- PostgreSQL is the shared source of truth.
- The API and worker must use the same database schema.
- No component may use process-local state as the authoritative source for inventory, idempotency, or job ownership.
- Database migrations must be committed to version control.
- Schema changes must be communicated to the other team members.
- Destructive tests must run only against an isolated test database.
- Monetary values are stored as integer cents, never floating-point values.
- All timestamps used for leases and scheduling must be handled consistently using database time.
- The API must not return an accepted order before its transaction commits.
- Worker retries must not create additional orders, jobs, or inventory reservations.

## 5. Responsibility Summary

| Area | Owner | Responsibility |
|---|---|---|
| Database schema and migrations | Person A | Tables, constraints, indexes, seed data |
| API routes and validation | Person A | Catalogue, inventory, order creation |
| Transactional correctness | Person A | Stock reservation, idempotency, concurrency |
| Worker claiming and leases | Person B | Claiming, renewal, reclaiming, crash recovery |
| Job processing | Person B | Retries, completion, failure handling |
| Runtime and deployment | Person C | Docker, CI/CD, Kubernetes, deployment |
| Integration | All | Shared contract, compatibility, testing |

---
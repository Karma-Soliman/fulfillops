# Individual Contribution – Person A

## My responsibilities

My role in FulfillOps was to work on the API, database and transactional correctness. My main responsibility was to make sure that orders are accepted and stored safely, including when requests are repeated or arrive at the same time.

## What I implemented

- Implemented the order API, including request validation, order creation and order retrieval.
- Worked on the PostgreSQL database models and Alembic migration for products, inventory, orders, order items, idempotency keys and jobs.
- Implemented transactional order creation so that inventory reservation, order data, the idempotency record and the worker job are stored together.
- Implemented idempotency handling so that repeating a request with the same key and payload returns the original order, while reusing the key with a different payload is rejected.
- Added API tests for order creation, validation, inventory and idempotency behaviour.
- Worked on database-backed readiness checks and the orders-created Prometheus metric.
- Created the Gate 1 demonstration to test concurrent requests through two API replicas, competing inventory reservations and replay after an API replica restart.

## Testing and evidence

I used automated tests to check the API and database behaviour. The Gate 1 evidence demonstrates that eight simultaneous requests with the same idempotency key create only one order, and that competing requests cannot reserve more stock than is available.

I also verified that the orders-created metric reports the database count consistently from both API replicas.

## Coordination with the team

I followed the API and integration contracts when implementing the database and API. I coordinated with the worker part so that accepted orders create durable jobs that workers can process using the shared PostgreSQL database.

## What I would improve

With more time, I would add more tests for database failures and less common concurrency scenarios. I would also expand the API documentation with more examples of error responses and add a visual database schema diagram.

## What I learned

This work helped me understand that a successful API response is not enough to guarantee a reliable system. Database transactions, idempotency and concurrency control are essential when multiple requests can modify the same inventory. I also learned how to verify these behaviours with automated tests and reproducible demonstrations.
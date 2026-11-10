# FulfillOps infrastructure stub

This is a temporary placeholder for infrastructure development. Delete this directory and use the
real FulfillOps image once it exists.

The image has one entry point and supports three commands: `api`, `worker`, and `migrate`. For
example, run `docker run --rm fulfillops-stub:dev api`. The API uses port 8080, the worker uses
port 9100, and all database configuration is supplied through `DATABASE_URL`. `APP_ENV` and
`LOG_LEVEL` are also read from the environment. The migration command creates the
`schema_migrations` readiness marker table and is safe to run repeatedly.

The Dockerfile pins the official `python:3.12-slim` multi-platform manifest digest inspected with
`docker buildx imagetools inspect python:3.12-slim` on 2026-11-10:
`sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`. Verify the current
digest with that same command before updating the pin.

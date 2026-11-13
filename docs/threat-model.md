# FulfillOps Threat Model

## 1. Purpose and Scope

This threat model identifies security and reliability threats affecting FulfillOps, an order-processing application built with FastAPI, PostgreSQL and background workers.

The main assets considered are:
- Customer order data.
- Product and inventory records.
- Idempotency keys and order-processing jobs.
- Database credentials and application configuration.
- API and worker availability.

The assessment focuses on the local application and deployment environment used for this project. It is not a complete external penetration test.

## 2. Threats and Mitigations

### Threat 1 – Overselling inventory through concurrent requests

**Risk:** Multiple clients may submit orders for the same product at nearly the same time. Without database-level concurrency control, both requests could read the same available stock and reserve more units than are available.

**Impact:** Negative or incorrect inventory, inconsistent orders and failed fulfilment.

**Mitigations:**
- Inventory reservation is performed inside a database transaction.
- Inventory rows are locked during reservation.
- Inventory is checked and updated before the order is committed.
- Requests that cannot be fulfilled are rejected without partially creating an order.
- The Gate 1 demonstration tests competing requests with different idempotency keys.

**Remaining limitation:** The concurrency tests cover the demonstrated scenarios, but do not replace extensive production-scale load testing.

### Threat 2 – Duplicate orders caused by request retries

**Risk:** A client may retry a request after a timeout or network failure, even if the original request was successfully processed.

**Impact:** Duplicate orders, repeated stock reservations and duplicate background jobs.

**Mitigations:**
- The API uses idempotency keys stored in PostgreSQL.
- Repeating the same key with the same request payload returns the original order.
- Reusing a key with a different payload is rejected.
- The order, reservation, idempotency record and job are committed in one transaction.
- The Gate 1 demonstration sends eight simultaneous requests with the same key and verifies that only one order and one job are created.

**Remaining limitation:** Clients must retain and reuse their idempotency key when retrying a request.

### Threat 3 – Unauthorized access to database credentials

**Risk:** Database credentials could be exposed through source control, logs, configuration files or an incorrectly configured deployment.

**Impact:** An attacker could read, modify or delete orders, inventory and job records.

**Mitigations:**
- Secrets are supplied through environment configuration rather than being hard-coded in application source.
- The repository provides `.env.example` as a configuration template.
- The project requires secrets to remain outside Git.
- Application containers use restricted runtime settings, including dropped Linux capabilities and `no-new-privileges`.

**Remaining limitation:** A production deployment should use a dedicated secrets manager, credential rotation and separate least-privilege database accounts for the API, worker and migration process.

### Threat 4 – Malicious or oversized API requests

**Risk:** An attacker or faulty client could submit malformed data, invalid quantities, unknown products or excessively large request bodies.

**Impact:** Increased resource consumption, unexpected application errors or invalid order data.

**Mitigations:**
- Request bodies are validated using Pydantic schemas.
- The API enforces limits on order lines and quantities.
- The request body is limited to 16 KiB.
- Unknown or unavailable products are rejected.
- Duplicate SKU lines are aggregated before inventory reservation.

**Remaining limitation:** Production deployments should also apply rate limiting, stronger abuse detection and appropriate network-level protections.

### Threat 5 – Worker crash while processing an order

**Risk:** A worker may stop unexpectedly after claiming a job but before completing it.

**Impact:** Jobs could remain unfinished or be processed more than once.

**Mitigations:**
- Jobs are stored durably in PostgreSQL.
- Workers claim jobs using row locking with `FOR UPDATE SKIP LOCKED`.
- Jobs use leases and lease tokens.
- Expired leases allow abandoned work to be recovered.
- Retries are bounded and use backoff.
- Finalization checks the lease information to prevent an outdated worker from completing a job after losing ownership.

**Remaining limitation:** The system provides at-least-once job execution. Business operations must remain safe against repeated processing.

### Threat 6 – Poison jobs and repeated processing failures

**Risk:** A job containing invalid data or triggering a persistent processing error may fail repeatedly.

**Impact:** Wasted worker capacity, repeated database activity and delayed processing of other orders.

**Mitigations:**
- Job attempts are bounded.
- Retry delays use backoff.
- Jobs that reach the configured attempt limit are moved out of normal processing for operator review.
- Worker failure and retry information is exposed through monitoring.

**Remaining limitation:** Operator review and recovery procedures should be documented and tested before production use.

### Threat 7 – Unhealthy application release

**Risk:** A new application version may contain a bug that causes API requests to fail or readiness checks to report that the application is unavailable.

**Impact:** Failed order submissions and service disruption.

**Mitigations:**
- CI checks are run before changes are accepted.
- Kubernetes uses readiness and liveness probes.
- Kubernetes rollout health checks prevent an unhealthy release from being treated as successful.
- GitOps reconciliation restores the declared configuration.
- The project includes evidence from a broken-release drill and recovery through Git.

**Remaining limitation:** Automated rollback and recovery still depend on correctly configured probes, rollout settings and GitOps reconciliation.

## 3. General Security Measures

The project also applies the following defensive measures:

- Containers run with restricted privileges.
- Application containers use read-only root filesystems where configured.
- Linux capabilities are dropped and privilege escalation is disabled.
- Database schema changes are managed through Alembic migrations.
- Health and metrics endpoints provide operational visibility.
- Application configuration is separated from source code.

## 4. Risk Summary

| Threat | Main protection |
|---|---|
| Inventory overselling | Database transactions and row locks |
| Duplicate orders | Persistent idempotency keys |
| Credential exposure | Environment-based configuration |
| Malformed or oversized requests | Input validation and request-size limit |
| Worker crashes | Leases and job recovery |
| Poison jobs | Bounded retries and operator review |
| Unhealthy releases | Probes, rollout checks and GitOps |

## 5. Limitations

FulfillOps is an academic project and has not undergone a full independent security assessment. Before production use, additional work should include rate limiting, centralized secret management, database least-privilege roles, network policies, credential rotation, and broader security and load testing.

This threat model should be reviewed whenever the architecture, deployment environment or security controls change.
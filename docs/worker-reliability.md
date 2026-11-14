# Worker reliability – Karma

## Scope and code

My responsibility as is the separate PostgreSQL-backed worker, its
reliability mechanisms, tests and telemetry. The API owns order acceptance and
reservation; the worker consumes an existing reservation on successful fulfillment.
The shared interface is defined in [integration-contract.md](integration-contract.md).

| File | Responsibility |
|---|---|
| `worker/config.py` | Validate environment configuration. |
| `worker/main.py` | Start the process, reflect existing tables, poll and handle shutdown. |
| `worker/repository.py` | Transactional claiming, renewal, completion and failure. |
| `worker/processor.py` | Coordinate preparation and heartbeat renewal. |
| `worker/telemetry.py` | JSON events and independent health/metrics HTTP server. |

## Ownership and lifecycle

The API commits the order, reservation and unique job together. `Repository.claim()`
selects either a due queued job or a processing job with an expired lease, using
`FOR UPDATE SKIP LOCKED`. It locks the order, increments attempts, assigns the worker
identity and a fresh UUID token, sets expiry, and commits. Other workers skip locked
candidates; after commit, an unexpired processing job is no longer eligible.

The short row lock protects acquisition. The persisted lease represents ownership
between transactions. `locked_by` uses HOSTNAME, falling back to a generated UUID;
the token distinguishes claims even when a worker identity is reused. Database time
avoids disagreements between machine clocks. Current-time checks after lock waits
use `clock_timestamp()`, since PostgreSQL `now()` is transaction-start time.

`Repository.complete()` locks the job/order, checks token, worker identity, state
and expiry, then locks inventory in sorted SKU order. After checking stock and
rechecking expiry, it consumes the reservation and completes both records in one
transaction. For one KIT-100, on-hand/reserved change from 7/1 to 6/0; availability
stays 6. A rollback leaves all these effects uncommitted. Duplicate or stale
completion is rejected. Fulfillment currently consists of database effects only,
not an external shipping or payment call.

Preparation has a heartbeat renewing approximately every three seconds against
a ten-second lease. Lost or uncertain renewal prevents finalization. The heartbeat
stops before the completion transaction; long inventory waits can therefore cause
completion to reject an expired lease and leave work for recovery.

| Event | Job | Order | Inventory |
|---|---|---|---|
| Accepted | queued, attempts 0 | queued | Reserved by API |
| Claimed/reclaimed | processing, increment attempts | processing | Unchanged |
| Retryable failure | queued, future available_at | processing | Reservation retained |
| Success | completed, lease cleared | completed | On-hand and reserved decrease equally |
| Attempts exhausted | failed, lease cleared | failed | Reservation retained |

Every committed claim consumes an attempt, including one interrupted by a crash.
Ordinary failures persist exponential backoff: `min(8, 1 * 2**(attempts - 1))`
seconds with defaults. There is a one-second delay after attempt 1 and two seconds
after attempt 2. Attempt 3 is terminal. The worker respects a lower persisted limit
and never exceeds three claims. If the third claim crashes, a later `claim()` call
marks the expired job and order failed without a fourth attempt.

Failed jobs retain their count, timestamps and safe last-error category for
operator review. They are not deleted or automatically restocked. Review means
inspecting the order/job and reservation before deciding a manual reconciliation;
this worker does not implement an automatic administrative retry/restock procedure.

## Startup, configuration and shutdown

From the repository root, with dependencies installed from `requirements.lock`,
the shared migrations already applied and DATABASE_URL exported:

```sh
python -m worker.main
```

The worker reads environment variables directly; it does not load `.env` itself.
Never commit a real connection string. Its table reflection requires the shared
schema and does not create or migrate it.

| Variable | Default / requirement |
|---|---|
| DATABASE_URL | Required; SQLAlchemy `postgresql+psycopg` URL |
| DB_POOL_SIZE | 5 |
| WORKER_LEASE_SECONDS | 10 |
| WORKER_RENEW_INTERVAL_SECONDS | 3; positive and shorter than lease |
| WORKER_MAX_ATTEMPTS | 3; other environment values rejected |
| WORKER_BACKOFF_BASE_SECONDS | 1 |
| WORKER_BACKOFF_MAX_SECONDS | 8 |
| WORKER_POLL_INTERVAL_SECONDS | 0.5 |
| WORKER_METRICS_PORT | 9100 |
| LOG_LEVEL | INFO |

SIGTERM/SIGINT stops new loop iterations and allows active work to finish. Windows
also supports SIGBREAK through the platform-specific test shutdown helper. The
worker does not release an active claim prematurely. Its connection pool and HTTP
server close on normal exit. There is no internal hard eight-second cancellation
deadline: if orchestration force-kills blocked work, lease recovery remains needed.

## Telemetry

Port 9100 serves `/health/live` without a database query and `/metrics` using a
private Prometheus registry. Liveness is not a proof of processing progress.
Prometheus scrapes each replica individually. Claims, retries, recoveries,
completion/failure, active jobs and attempt duration help diagnose behavior.
The attempt histogram excludes queue waiting; it is not end-to-end order latency.

Repository events increment outcome counters after successful commit. JSON stdout
events include UTC timestamps and permitted diagnostic fields, excluding customer
IDs, raw idempotency keys, credentials, lease tokens and raw exception text.
Counters reset on process restart and can miss observations if a process dies
between commit and recording. PostgreSQL remains authoritative. Do not sum worker
process counters together with duplicate database-wide totals exposed by the APIs.

## Tests and requirement matrix

Worker tests use actual PostgreSQL, shared Alembic migrations and committed fixtures
visible to independent sessions. Each test creates and drops its own unique schema.
Use a dedicated test-only database and restricted credentials, never shared data.

```sh
export APP_ENV=test
# Export TEST_DATABASE_URL using local test credentials; database name must
# begin fulfillops_test and the URL must use postgresql+psycopg.
python -m pytest tests/worker -q
python scripts/worker_reliability_demo.py
```

The evidence runner additionally refuses remote hosts and existing output
directories. Missing TEST_DATABASE_URL skips database tests; skips are not passes.

| Guarantee | Representative test in tests/worker/ |
|---|---|
| Atomic claims | `test_two_workers_claim_one_job_only_once` |
| Locked work does not block other claims | `test_locked_job_is_skipped_without_blocking_other_work` |
| Inventory consumed once | `test_simultaneous_completion_applies_business_effect_once` |
| Completion rollback | `test_database_failure_rolls_back_inventory_job_and_order` |
| Stale ownership rejected | `test_expired_job_reclaimed_and_stale_worker_fenced` |
| Real lease renewal | `test_heartbeat_allows_processing_beyond_original_lease` |
| Retry scheduling and limits | `test_poison_job_has_backoff_and_stops_after_three_attempts` |
| Final crashed attempt | `test_third_crashed_attempt_is_failed_without_fourth_claim` |
| Real process recovery | `test_two_real_workers_expose_health_and_recover_killed_peer` |
| Cooperative shutdown | `test_sigterm_during_active_completion_finishes_without_claiming_more` |
| Post-commit metrics | `test_metrics_track_committed_retry_and_completion_only` |
| Safe logs / test targets | `test_json_logging_filters_secrets_and_honors_log_level`; `test_evidence_runner_refuses_unsafe_targets` |

Repository tests are in `test_repository.py`; heartbeat coordination unit tests in
`test_processor.py`; HTTP/metric/log checks in `test_telemetry.py`; runner guard
tests in `test_evidence_safety.py`. The last directly observed local worker run
passed 44 tests. This is separate from the four-scenario historical evidence below;
these counts must not be added together. No tests were rerun for this guide.

## Recorded evidence and controlled worker incident

The [recorded run](evidence/worker-20261113T092847Z-7e0a2f/summary.json) contains
four passing scenarios, with revision, working-tree state, UTC timestamps and
limitations. It was captured from a dirty working tree and is not a claim that
every later commit was rerun. `results.xml` and `test-output.txt` record results;
per-scenario snapshots, logs and `.prom` files record actual observations.

| Scenario | Observed outcome / limitation |
|---|---|
| Kill one of two workers | Survivor recovered after natural four-second test-lease expiry; both jobs completed with attempt counts 1 and 2. |
| Deterministic poison callback | Job/order failed at attempt 3; reservation retained. Fixture SQL accelerates retry eligibility after checking stored backoff. |
| Third crashed attempt | Failed at attempt 3 with no fourth claim; fixture SQL advances expiry. |
| Shutdown during active completion | Active order completed, next job remained queued, process exited normally in approximately 0.139 seconds in this run. |

The crash was an intentional local drill, not a production incident. A test-held
inventory lock paused completion after two committed claims so termination happened
at a known point. Timeline from `database-snapshots.jsonl` (13 November 2026, UTC):

| Time | Observation |
|---|---|
| 09:28:48.754 | Two accepted queued jobs, zero attempts. |
| 09:28:49.130 | Two independent workers processing; each job at attempt 1. |
| 09:28:49.137 | One process killed, exit code -9; committed work still present. |
| 09:28:53.163 | Both jobs completed; recovered job at attempt 2. |

KIT-100 ended at on-hand 5/reserved 0 for two one-unit orders, demonstrating no
extra committed consumption. The disruption was contained by durable claims,
lease expiry and token-checked atomic completion. The prevention mechanism is
repeatable regression testing of those invariants; database failure and external
business side effects remain separate risks. The deployment incident is documented
in [incident-postmortem.md](incident-postmortem.md).

These demonstrations use local Python processes and real PostgreSQL, not a
container/Kubernetes kill drill. They exercise committed synthetic fixtures rather
than the full HTTP acceptance path. Default production-style leases remain ten
seconds. Actual evidence is retained; no metrics or logs are fabricated.

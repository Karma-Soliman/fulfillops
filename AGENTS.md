# AGENTS.md — FulfillOps

Instructions for AI coding agents working in this repository. Read this file fully before every task.

## 1. Project in one paragraph

FulfillOps is a graded DevOps capstone (EPITA, team of 3, deadline Sun 15 Nov 2026 23:59 Europe/Paris).
It is an order-processing platform: an HTTP API accepts orders and reserves stock exactly once,
a separate worker completes orders asynchronously, and everything is containerized, tested in CI,
deployed to a local kind cluster and managed by Argo CD (GitOps).
The authoritative specs are in `assessment/`:

- `assessment/API_CONTRACT_EN.md` — exact routes, status codes, error codes. Follow it literally.
- `assessment/FulfillOps_Assignment_EN.md` — requirements, evidence, grading.
- `assessment/SETUP_AND_SUBMISSION_EN.md` — environment and submission rules.
- `docs/integration-contract.md` — the team's agreed interface between API, worker and infrastructure.

The executable public contract checker and rolling-update probe are project utilities in `scripts/`,
not instructor files: `scripts/fulfillops_public_checker.py` and
`scripts/fulfillops_rollout_probe.py`.

If a request conflicts with these files, stop and say so instead of guessing.

## 2. Stack (agreed)

- Python 3.12, FastAPI, uvicorn (1 uvicorn worker per container; scale with replicas)
- PostgreSQL 16 as the only durable store AND the job queue (jobs table, `FOR UPDATE SKIP LOCKED`, leases)
- Alembic for migrations
- prometheus_client for metrics exposure; Prometheus (pinned image) for collection in Compose and kind
- pytest for tests, ruff for lint/format, hadolint for Dockerfiles
- Docker (multistage, non-root), Docker Compose v2
- kind (local Kubernetes), Kustomize, Argo CD
- GitHub Actions, Trivy (scan), Syft (SBOM), GHCR (registry)

Do not add new services (Redis, Kafka, Helm, etc.) or new major dependencies without asking.

## 3. Repository layout and ownership

```
api/                 Person A — API, validation, orders, idempotency
worker/              Person B — job processing, retries, metrics
db/migrations/       Person A (reviewed by B)
tests/api/           Person A
tests/worker/        Person B
tests/integration/   shared
tests/deployment/    Person C
infra/stub-app/      Person C — TEMPORARY placeholder app until the real image exists
infra/kind/          Person C
infra/k8s/           Person C — Kustomize base + overlays/kind
infra/argocd/        Person C
infra/prometheus/    Person C — scrape config (Compose); k8s version lives in infra/k8s/base
.github/workflows/   Person C
scripts/             shared (C owns cluster/release/drill/bootstrap scripts)
docs/                shared
assessment/          instructor files — NEVER modify
compose.yaml         Person C (reviewed by A/B)
Dockerfile           A and B
```

**Rule:** when working for Person C, do NOT edit `api/`, `worker/`, `db/migrations/`, `Dockerfile`
or another person's tests. If a task seems to require it, stop and explain what change is needed and why.

## 4. Runtime contract (summary of docs/integration-contract.md)

- ONE image `ghcr.io/<org>/fulfillops:<git-sha>`, two commands:
  - API: `uvicorn api.main:app --host 0.0.0.0 --port 8080 --workers 1`
  - Worker: `python -m worker.main` (serves `/health/live` and `/metrics` on port 9100)
- Migrations: one idempotent command (Alembic upgrade head), guarded by an advisory lock
- Config only through env vars: `DATABASE_URL` (secret), `APP_ENV` (dev|test|lab), `LOG_LEVEL`,
  `DB_POOL_SIZE`, `WORKER_LEASE_SECONDS`, `WORKER_MAX_ATTEMPTS`, `WORKER_BACKOFF_BASE_SECONDS`,
  `WORKER_BACKOFF_MAX_SECONDS`, `WORKER_POLL_INTERVAL_SECONDS`
- Agreed worker values: lease 10 s (renewed ~every 3 s, compared with Postgres `now()`),
  3 attempts including the first (an expired-lease reclaim counts as an attempt),
  backoff 1 s doubling to an 8 s cap, polling 0.5 s.
- Shutdown: on SIGTERM the worker stops claiming, finishes or releases its current job, and exits
  within 8 s → Kubernetes `terminationGracePeriodSeconds: 8`, Compose `stop_grace_period: 8s`.
- Schema (owned by A): one job per order (`UNIQUE jobs.order_id`), created in the same transaction
  as the order and the stock reservation. `jobs.locked_by` = `HOSTNAME` (= pod name in Kubernetes).
- Metrics: each process exposes its own counters (API :8080/metrics, worker :9100/metrics).
  Aggregation across replicas happens in Prometheus queries, never in application code.
  Latency is a histogram (not a summary) so p95 can be aggregated across pods.
- `/health/live` never touches the database. `/health/ready` checks DB connectivity (≈1 s timeout)
  and that migrations are at head; returns 503 `{"status":"not_ready"}` otherwise.
- API and worker handle SIGTERM gracefully. Logs are JSON to stdout.
- Seed runs only if the products table is empty. Test reset refuses unless `APP_ENV=test`.

## 5. Non-negotiable rules

Security

- Never commit secrets, tokens, private keys, real `.env` files or Secret manifests with values.
  `.env.example` contains placeholders only.
- Never print secrets in logs, CI output, or command output you show me. No `set -x` around secrets.
- Containers run as non-root (UID 10001), drop all capabilities, no privilege escalation.
- Never log or use as metric labels: customer IDs, idempotency keys, credentials, SQL, connection strings.
- Destructive scripts (reset, `down -v`) must refuse to run unless clearly targeting the test environment.

Reproducibility

- Pin everything: base images (tag + digest), Python deps (lockfile), Postgres/nginx/kind node images,
  Argo CD version, GitHub Actions (full commit SHA + version comment).
- Never use `:latest`. Kubernetes images use the git SHA tag with `imagePullPolicy: IfNotPresent`.
- Never invent versions, SHAs or CLI flags. If unsure, say so and show me where to verify
  (official release page / docs). For action SHAs, state the source of each SHA.

Kubernetes / GitOps

- Namespace `fulfillops`. Labels: `app.kubernetes.io/name`, `app.kubernetes.io/component` (api|worker|db).
- API: 2 replicas, RollingUpdate `maxSurge: 1`, `maxUnavailable: 0`, readiness + liveness + startup probes,
  resource requests and memory limits, preStop sleep, `readOnlyRootFilesystem` with an emptyDir at /tmp.
- Select the process role with `args: ["api"]` / `["worker"]` / `["migrate"]`. NEVER use
  `command:` for this: it replaces the image ENTRYPOINT (entrypoint.sh) and bypasses its
  dispatcher and its `exec` (signal handling).
- App pods run on the worker node (the kind control-plane has a NoSchedule taint).
- Worker: 2 replicas, liveness on port 9100, `terminationGracePeriodSeconds: 8`.
- Headless Services (`clusterIP: None`) `fulfillops-api-metrics` and `fulfillops-worker-metrics`
  so Prometheus scrapes every replica via `dns_sd_configs` (no RBAC needed).
- Postgres: StatefulSet + PVC with `argocd.argoproj.io/sync-options: Prune=false`.
- Migrations: Job as Argo `Sync` hook, `BeforeHookCreation` delete policy, sync waves DB(0) → Job(1) → app(2).
- The cluster is changed through Git only. Never leave a manual `kubectl patch`/`edit` as a final state.
- Expose the API via NodePort 30080 mapped to host 8080 by kind. Use port-forward only for the Argo CD UI.

CI

- Workflows default to `permissions: contents: read`; grant more only per job (e.g. `packages: write` on publish).
- The publish job must `needs:` every quality job. Build the image once and reuse it across jobs.
- Vulnerability policy: CRITICAL/HIGH with a fix available = blocking; everything else = informational report.

## 6. How to work on a task

1. Work on a branch named `c/<task-name>` (or `a/…`, `b/…` for other owners).
2. Do only the task asked. No unrelated refactors, renames or "improvements".
3. Keep the code simple and explainable. Use a design pattern only when you can state in one sentence
   what problem it removes.
4. **Run your verification commands and show the real output.** Never claim something works
   without output. If a command fails, show the error and fix it; do not hide failures.
5. At the end, report:
   - files created/changed, one line each
   - every design decision you made and the alternative you rejected
   - one thing that could break it, and how to diagnose it
   - exact commands for me to verify it myself
6. Use small, descriptive commits (`ci: add trivy scan job`, `k8s: add api deployment probes`).

## 7. Explanations

The human owner must be able to explain every line in an oral exam and is new to Kubernetes.
When asked to explain, go file by file: what each block does, why it exists, what breaks if removed,
and how to observe it working (`kubectl` / `docker` commands). Prefer plain language over jargon.

## 8. Useful commands

```bash
make up                 # local stack (docker compose up -d --build)
make down               # stop without deleting data (never -v)
make test-stack-up      # isolated test stack for the checker
make test-stack-down    # destroys TEST data only
python3 scripts/fulfillops_public_checker.py --base-url http://localhost:8080 --concurrency --stress
python3 scripts/fulfillops_rollout_probe.py --base-url http://localhost:8080 --path /health/ready --duration 30 --interval 0.25 --output docs/rolling_update_probe.csv
./scripts/cluster-up.sh / ./scripts/cluster-down.sh
kubectl -n fulfillops get pods,svc,endpoints
kubectl -n argocd get applications
```

Only one of Compose or kind can use host port 8080 at a time.

## 9. Assistance log

AI usage must be disclosed. After each task, append one line to `docs/assistance-log.md`:
date, task, tool used, what was generated, what the human reviewed or changed.

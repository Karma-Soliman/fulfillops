# Kubernetes manifests

The manifests under `infra/k8s/base/` describe the same local application roles as Compose.
The kind overlay selects the local image tag, while `scripts/k8s-apply.sh` creates the local
database Secret and applies the overlay by hand. Argo CD is not installed in this phase.

## Object map

| Object | What it does | Why these settings |
| --- | --- | --- |
| Namespace `fulfillops` | Isolates app resources. | Keeps this stack separate from cluster services. |
| ServiceAccount `fulfillops-app` | Gives app pods an identity. | Token automount is disabled because they do not call the Kubernetes API. |
| ConfigMap `fulfillops-config` | Holds non-secret runtime settings. | Shared API and worker values stay outside the images. |
| Headless Service `postgres` | Gives PostgreSQL stable DNS. | The StatefulSet pod has a stable identity and DNS record. |
| StatefulSet `postgres` | Runs the single PostgreSQL database. | A 1 GiB PVC preserves data across pod replacement; readiness and liveness use `pg_isready`. |
| Job `fulfillops-migrate` | Creates the application migration table. | Its init container waits for PostgreSQL, and `backoffLimit` retries transient failures. |
| Deployment `fulfillops-api` | Runs two HTTP API replicas. | Rolling updates keep one replica available; readiness checks DB and schema state. |
| NodePort Service `fulfillops-api` | Routes port 30080 to API pods. | kind maps host `localhost:8080` to this NodePort. |
| PodDisruptionBudget `fulfillops-api` | Protects API availability during voluntary disruption. | At least one of the two replicas must remain available. |
| Deployment `fulfillops-worker` | Runs two background workers. | Independent liveness checks and an 8 second termination grace period match the worker contract. |

## Compose to Kubernetes

| Compose role | Kubernetes object |
| --- | --- |
| `postgres` service and named volume | PostgreSQL StatefulSet, headless Service, and PVC |
| one-shot `migrate` service | `fulfillops-migrate` Job |
| scaled `api` service | API Deployment and NodePort Service |
| scaled `worker` service | Worker Deployment |
| `.env` database values | Secret `fulfillops-db`, created locally by `bootstrap-secrets.sh` |
| app environment values | ConfigMap `fulfillops-config` |

## Startup and readiness

Kubernetes has no Compose-style `depends_on` ordering for ordinary resources. The PostgreSQL
readiness probe makes its Service endpoint available only after it accepts connections. The
migration Job's init container also loops on `pg_isready` before running `migrate`. API pods start
after the Job is applied, and their readiness probe requires both a reachable database and the
`schema_migrations` table. If the database becomes unavailable later, API readiness fails and
removes those pods from Service endpoints; the liveness probe remains local and does not restart
the API just because PostgreSQL is down.

## Secret handling

There is deliberately no Secret manifest in Git. `scripts/bootstrap-secrets.sh` reads the ignored
`.env`, creates or updates namespace `fulfillops`, and applies Secret `fulfillops-db` with keys
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `DATABASE_URL`. The generated URL points
to `postgres:5432` and credentials are URL-encoded. The script prints the key names only. Keep
`.env` private and never paste Secret values into logs or command output.

## Argo CD annotations

The StatefulSet has `Prune=false` and sync wave `0`, protecting database storage and starting the
database first. The migration Job is a `Sync` hook at wave `1`, with `BeforeHookCreation` so a prior
immutable Job can be replaced on a later sync. API and worker workloads use wave `2`, after the
migration. These annotations are harmless when applying the manifests manually; they will control
ordering and cleanup after Argo CD is introduced.

## Local commands

- `make k8s-render` renders the kind overlay.
- `make k8s-apply` refreshes the local Secret, applies resources, and waits for migration and both
  Deployments.
- `make k8s-status` shows pods, services, endpoints, and PVCs.
- `make k8s-delete` removes app workloads and configuration while retaining the Secret and PVC.
- `make cluster-down` removes the entire kind cluster and its database data after confirmation.

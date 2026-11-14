# Individual contribution — Sasha (Person C: CI/CD, Kubernetes and GitOps)

## What I personally implemented

- **CI/CD pipeline** (`.github/workflows/ci.yml`): lint (Ruff, Hadolint), full test suite on PostgreSQL,
  a single image build reused by every later job, Trivy scan with a documented blocking policy
  (fixable HIGH/CRITICAL blocks, everything else informational), CycloneDX SBOM with Syft,
  the public checker as a blocking contract job on a fresh isolated stack, and publication to GHCR
  with the commit SHA as tag and the digest recorded. Least-privilege permissions, actions pinned by SHA.
- **Supply-chain gate evidence**: the deliberate red → green transition in PR #14
  (CVE-2021-33503 in urllib3 1.26.4 blocked the pipeline; removing it turned it green).
- **Containers and Compose integration**: the root multistage, non-root Dockerfile and entrypoint
  (one image, roles api/worker/migrate, `exec` for signal handling), the hashed lockfile, `compose.yaml`
  with 2 API + 2 workers behind nginx, healthchecks and hardening, the isolated test stack and the guarded
  `scripts/reset-test-data`. Image size: 380 MB vs 1.78 GB for the naive baseline.
- **Kubernetes on kind**: cluster definition with the 8080 → NodePort 30080 mapping, Kustomize base + kind
  overlay (API and worker Deployments with probes, rolling strategy and security contexts, Postgres
  StatefulSet + PVC, migration Job, ConfigMap, Secret created outside Git by a bootstrap script).
- **GitOps with Argo CD**: pinned installation, least-privilege AppProject, Application with automated
  sync, self-heal and prune protection for the database, sync waves and the migration hook.
- **Observability collection**: Prometheus in kind and Compose scraping every API and worker replica
  through headless Services; p95 query evidence.
- **Release and drill scripts**: `release.sh` (deploy through a Git PR), drift drill, rolling-update drill
  (120/120 probe requests OK) and broken-release drill (rollout halted at ProgressDeadlineExceeded,
  599/599 availability checks OK, orders 2 → 2, recovered by `git revert`).
- **Documentation**: `docs/ci-cd.md`, `docs/gitops.md`, `docs/kubernetes-local.md`,
  `docs/kubernetes-manifests.md`, the evidence index and the final report layout.

## What I reviewed

- The integration contract with Person A and Person B (runtime commands, ports, environment variables,
  `DATABASE_URL` format, worker lease and shutdown values, metrics exposure).
- Person A's API/schema PRs and Person B's worker PRs where they affected deployment: readiness and
  migration checks, the worker health/metrics listener, metric names, SIGTERM behaviour.
- The requirements audit against the brief, and the regression investigation on readiness and metrics.

## What I would improve next

- **Sealed Secrets** (or an external secret manager) so encrypted secrets can live in Git and the last
  manual bootstrap step disappears.
- **Least privilege in the cluster itself**: read-only RBAC for humans so only Argo CD can change
  resources, NetworkPolicies so only the API, workers and migration Job can reach Postgres, and image
  references pinned by digest instead of tag.
- **Stronger CI checks for deployment**: manifest validation (kubeconform) and `trivy config` on
  `infra/k8s/`, plus multi-arch images so the exact CI-published digest also runs on arm64 laptops.
- **Better observability**: persistent Prometheus storage, alerting on the SLO, and a small dashboard.
- **Process lessons**: commit evidence as soon as a drill runs (some of mine stayed local at first), and
  make every evidence script fail loudly instead of exiting silently.

# FulfillOps requirements traceability audit

**Audit date:** 2026-11-13  
**Snapshot:** `origin/main` at `e8a802a24e18231cbe4c2a07ce0928832c3a2511`; successful main CI run [43446679146](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146) built that exact commit. The run covers the audited snapshot and contains green build, lint, test, contract, scan, SBOM, and publish jobs.  
**Status rule:** Done means committed source/configuration or a CI/evidence artifact demonstrates the requirement. Partial means an implementation exists but required live/reproducible proof is absent, or evidence is for the temporary stub. Missing means the requested artifact/proof is not committed. Stub-only evidence is Partial whenever the assignment calls for the real application.

The API contract was read in full and used to assess application and checker claims. The tables below include the assignment sections explicitly requested; they do not repeat every individual API route and validation clause as separate rows.

## Section 2 — Definition of success

| Requirement | Source (section) | Owner | Status | Proof | What is missing |
|---|---|---:|---|---|---|
| HTTP API follows the API contract exactly | Assignment §2.1; API contract | A | Done | `api/`; [main CI contract run](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146) | None observed in the passing public checker; independent edge-case proof remains in the test requirements below. |
| Separate worker completes persisted orders | Assignment §2.2 | B | Done | `worker/`; `db/migrations/versions/a9602c25d278_create_initial_database_schema.py`; [main CI](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146) | Live recovery proof is tracked separately under §5A. |
| Explicit worker retry and recovery behavior | Assignment §2.2 | B | Partial | `worker/processor.py`; `tests/worker/test_processor.py`; `tests/worker/test_repository.py` | Committed tests exist, but no committed two-worker kill/reclaim and poison-job run evidence. |
| Atomic inventory reservation under concurrent requests | Assignment §2.3 | A | Done | `api/orders.py`; `tests/api/test_api.py`; main CI checker job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | No separate database-query evidence attached to the required eight-request demonstration. |
| Same idempotency key works across API replicas; no negative stock or double reserve | Assignment §2.3 | A | Partial | `api/orders.py`; `tests/api/test_api.py`; checker job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | CI checker passes, but committed evidence does not show the required 8 simultaneous same-key requests, stable ID, inventory queries, and replay after API restart as one reproducible proof. |
| Repeatable tests detect failure and show recovery | Assignment §2.4 | Team | Partial | `tests/api/`, `tests/worker/`; `docs/evidence/red-green.md`; main CI test job [131957828298](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131957828298) | Red-green record is a dependency scan demo against the former stub; no committed app bug injection/recovery output. |
| CI runs lint/static checks, tests, build and security checks | Assignment §2.5 | C | Done | `.github/workflows/ci.yml`; main CI [43446679146](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146) | None for the passing run. |
| CI produces an SBOM | Assignment §2.5 | C | Done | CI SBOM job [131958151474](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151474) (artifact uploaded); `.github/workflows/ci.yml` | Preserve/download artifact with final submission. |
| CI has a gated deploy/promotion stage | Assignment §2.5 | C | Done | `.github/workflows/ci.yml`; main publish job [131958729482](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958729482) | No gap seen in the latest main run. |
| Reproducible multistage non-root Docker image | Assignment §2.6 | C | Done | `Dockerfile`; `requirements.lock`; main build job [131957827839](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131957827839) | None for build/non-root configuration. |
| Local Compose orchestration | Assignment §2.6 | C | Done | `compose.yaml`; `compose.test.yaml`; main CI contract job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | No committed real-app persistence-after-restart transcript. |
| Kubernetes and Argo CD GitOps with 2 API and 2 independently operating workers | Assignment §2.7 | C | Partial | `infra/k8s/`; `infra/argocd/`; `docs/evidence/drift-20261111T121029Z.txt` | Manifests are committed, but the drift record predates the real app and there is no committed post-integration live proof for both real worker replicas. |
| Persistent storage and health probes in Kubernetes | Assignment §2.7 | C | Partial | `infra/k8s/base/postgres-statefulset.yaml`; `infra/k8s/base/api-deployment.yaml`; `infra/k8s/base/worker-deployment.yaml`; `scripts/smoke-cluster.sh` | Committed config and stub smoke script exist; no committed real-app cluster run/output demonstrating PVC and probes. |
| Observability evidence | Assignment §2.8 | B/C | Partial | `api/metrics.py`; `worker/telemetry.py`; `docs/evidence/prometheus-20261111T122643Z.txt` | Metrics output is from the temporary placeholder app; repeat evidence against the real image was missing at the audit snapshot. |
| Two distinct safe fault-injection exercises | Assignment §2.8 | B/C | Partial | `scripts/drill-broken-release.sh`; `scripts/drill-rolling-update.sh`; `scripts/prom-evidence.sh` | No committed real-app worker-kill and broken-rollout evidence pair. |
| Rolling-release verification | Assignment §2.8 | C | Partial | `scripts/drill-rolling-update.sh`; `scripts/fulfillops_rollout_probe.py`; `docs/evidence/README.md` | No committed 30-second CSV/revisions record for the real app. |
| Incident report | Assignment §2.8 | Team | Missing | None; expected `docs/incident-postmortem.md` | Write a blameless report with timeline, cause, impact, mitigation, and prevention after real fault exercises. |
| Secrets stay out of Git | Assignment §2.9 | C | Done | `.gitignore`; `.env.example`; `scripts/bootstrap-secrets.sh`; CI main run | Verify final student ZIP separately before submission. |
| Least privilege | Assignment §2.9 | C | Partial | `.github/workflows/ci.yml`; `infra/k8s/base/serviceaccount.yaml`; deployment manifests | No committed security review/evidence covering app, DB, CI, and cluster permissions end to end. |
| Validated input | Assignment §2.9 | A | Done | `api/schemas.py`; `tests/api/test_api.py`; main CI | None observed in the contract run. |
| Bounded request body | Assignment §2.9 | A | Done | `api/main.py`; `tests/api/test_api.py` | None observed in source/tests. |
| Safe logs | Assignment §2.9 | A/B | Partial | `api/`; `worker/`; `docs/integration-contract.md` | No committed verification that customer data, credentials, SQL, and idempotency keys are absent from emitted logs. |
| Professional README | Assignment §2.10 | C/team | Partial | `README.md` | README has operation instructions, but lacks a full project architecture explanation and contributions summary. |
| Architecture diagram | Assignment §2.10 | Team | Missing | None; expected `docs/architecture.md` or `docs/architecture.pdf` | Add a system/data-flow diagram. |
| Contribution proof | Assignment §2.10 | Team | Missing | None found in committed README/docs | Add per-person work, review, and improvement notes. |
| Individual technical defense | Assignment §2.10 | Team | Missing | No repository artifact can establish this | Prepare each member for the 20-point live defense; evaluator must assess it. |

## WP1–WP7 — each Evidence line

| Requirement | Source (section) | Owner | Status | Proof | What is missing |
|---|---|---:|---|---|---|
| Architecture Markdown/PDF diagram | WP1 Evidence | Team | Missing | None; `docs/architecture.md` and `docs/architecture.pdf` absent | Add diagram covering API, database/job table, worker, receipt, and metrics flow. |
| Architecture decision record | WP1 Evidence | Team | Missing | None; `docs/ADR-001.md` absent | Record selected architecture and alternatives. |
| Schema and migrations | WP1 Evidence | A | Done | `db/migrations/versions/a9602c25d278_create_initial_database_schema.py` | None for artifact presence. |
| Threat model with at least five realistic threats | WP1 Evidence | Team | Missing | None; `docs/threat-model.md` absent | Document five or more threats, controls, and residual risk. |
| Reproducible demo with 12+ concurrent limited-stock requests | WP2 Evidence | A/team | Partial | `tests/api/test_api.py`; checker CI job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | No committed demo output specifying 12+ concurrent calls and inventory before/after. |
| No negative inventory under the demo | WP2 Evidence | A | Partial | `api/orders.py`; API tests | Add recorded DB/inventory proof from the concurrent demo. |
| Idempotent replay demonstrated | WP2 Evidence | A | Partial | `api/orders.py`; `tests/api/test_api.py`; checker CI job | Add an evidence transcript showing replay response and unchanged stock. |
| No duplicated order ID from concurrent same-key requests | WP2 Evidence | A | Partial | API code/tests; checker CI job | Add explicit same-key concurrent result/order query evidence. |
| Accepted order completes after API or worker restart | WP2 Evidence | A/B | Partial | `tests/worker/test_processor.py`; `tests/worker/test_repository.py` | Add committed restart/recovery run transcript with order state before and after. |
| Clear local commands | WP3 Evidence | C/team | Done | `README.md`; `Makefile` | None for commands. |
| Test matrix by layer | WP3 Evidence | Team | Missing | No committed test-matrix document found | Add unit/integration/deployment matrix and mapping to requirements. |
| Passing pipeline screenshots or links | WP3 Evidence | C | Done | Main CI [43446679146](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146) | Include final run link in submission report. |
| Initial failing scenario and corrected run | WP3 Evidence | Team | Partial | `docs/evidence/red-green.md`; [red-green PR #14](https://github.com/Karma-Soliman/fulfillops/pull/14) | This proves a stub dependency scan transition; add an app test bug/fix transition if interpreting WP3 literally. |
| CI workflow committed | WP4 Evidence | C | Done | `.github/workflows/ci.yml` | None. |
| PR link | WP4 Evidence | C | Done | [PR #16](https://github.com/Karma-Soliman/fulfillops/pull/16); [PR #17](https://github.com/Karma-Soliman/fulfillops/pull/17) | None. |
| Build logs | WP4 Evidence | C | Done | Main build job [131957827839](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131957827839) | None. |
| CI failure recovery | WP4 Evidence | C | Partial | `docs/evidence/red-green.md`; [PR #14](https://github.com/Karma-Soliman/fulfillops/pull/14); red run 43080402689 and green run 43080798851 | The recorded intentional red-to-green scan used the stub image; no real-app red-to-green transition is recorded. |
| Immutable image tag (commit SHA) | WP4 Evidence | C | Done | `Dockerfile`; `scripts/release.sh`; publish job [131958729482](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958729482) | Capture final registry digest/tag in submission report. |
| Clean rebuild | WP5 Evidence | C | Done | Main build job [131957827839](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131957827839) | None for build. |
| `docker compose up -d --build` path | WP5 Evidence | C | Done | `Makefile`; `compose.yaml`; main CI contract job | None for configured path. |
| Healthy real-app services | WP5 Evidence | C | Done | Main CI contract job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | Consider preserving a human-readable local `docker compose ps` transcript. |
| Container user inspection | WP5 Evidence | C | Partial | `Dockerfile` sets non-root user; `docs/evidence/image-size.md` | No committed `docker inspect`/`id` output for the real image. |
| Persistence across process/container restart | WP5 Evidence | A/C | Partial | `api/`; DB migration; `compose.yaml` volume | No committed real-app order/database restart evidence. |
| Image size comparison with naive baseline | WP5 Evidence | C | Done | `docs/evidence/image-size.md` | Existing comparison is documented; retain build context/version in final report. |
| `infra/k8s/` manifests | WP6 Evidence | C | Done | `infra/k8s/base/`; `infra/k8s/overlays/kind/` | None for source presence. |
| Argo CD Application | WP6 Evidence | C | Done | `infra/argocd/application.yaml`; `infra/argocd/project.yaml` | None for source presence. |
| Synced and Healthy screenshots/logs | WP6 Evidence | C | Partial | `docs/evidence/drift-20261111T121029Z.txt`; `scripts/drill-drift.sh` | Existing log is from the stub image; capture post-real-app Argo status. |
| Manual drift detection and reconciliation | WP6 Evidence | C | Partial | `docs/evidence/drift-20261111T121029Z.txt`; `scripts/drill-drift.sh` | Stub-era log only; repeat and preserve output on current real app. |
| Rollout history | WP6 Evidence | C | Partial | `scripts/drill-rolling-update.sh`; K8s manifests | No committed real-app rollout history/evidence artifact. |
| Secure secret handling | WP6 Evidence | C | Done | `scripts/bootstrap-secrets.sh`; `infra/k8s/base/`; `.gitignore` | Confirm no secret values in final export. |
| Reproducible fault script | WP7 Evidence | B/C | Partial | `scripts/drill-broken-release.sh`; `scripts/drill-rolling-update.sh` | No committed worker-kill fault script with isolated order setup and assertions. |
| Before/during/after health and logs | WP7 Evidence | B/C | Missing | No real-app fault evidence file | Capture timestamps, health states, and relevant sanitized logs for both faults. |
| Metrics output | WP7 Evidence | B/C | Partial | `docs/evidence/prometheus-20261111T122643Z.txt` | Current record measures stub; rerun against the real image. |
| Incident timeline | WP7 Evidence | Team | Missing | None; `docs/incident-postmortem.md` absent | Record the real fault timeline. |
| Root cause | WP7 Evidence | Team | Missing | None | Analyze observed real fault, not just expected failure behavior. |
| Mitigations and prevention action | WP7 Evidence | Team | Missing | None | Document corrective and preventive actions with owners. |

## Section 4 — Mandatory delivery tree and clean-clone requirements

| Requirement | Source (section) | Owner | Status | Proof | What is missing |
|---|---|---:|---|---|---|
| `README.md` | Assignment §4 | C/team | Partial | `README.md` | Add architecture, contributions, and any structural deviations to the current quick-start documentation. |
| `docs/architecture.md` | Assignment §4 | Team | Missing | Absent from `origin/main` | Create architecture diagram/document. |
| `docs/ADR-001.md` | Assignment §4 | Team | Missing | Absent from `origin/main` | Create decision record. |
| `docs/threat-model.md` | Assignment §4 | Team | Missing | Absent from `origin/main` | Create threat model. |
| `docs/incident-postmortem.md` | Assignment §4 | Team | Missing | Absent from `origin/main` | Create after controlled incident exercise. |
| `api/` source | Assignment §4 | A | Done | `api/` | None. |
| `worker/` source | Assignment §4 | B | Done | `worker/` | None. |
| `db/migrations/` | Assignment §4 | A | Done | `db/migrations/` | None. |
| `tests/` | Assignment §4 | A/B/team | Done | `tests/api/`; `tests/worker/`; `tests/deployment/` | Add the explicitly required race/fault evidence where noted above. |
| `infra/k8s/` | Assignment §4 | C | Done | `infra/k8s/` | None. |
| `infra/argocd/` | Assignment §4 | C | Done | `infra/argocd/` | None. |
| `.github/workflows/` | Assignment §4 | C | Done | `.github/workflows/ci.yml` | None. |
| `compose.yaml` | Assignment §4 | C | Done | `compose.yaml` | None. |
| `.env.example` with placeholders only | Assignment §4 | C | Done | `.env.example` | Recheck final exported ZIP for secrets. |
| Clean clone contains source, dependency manifests/lockfiles, migrations, docs, and scripts | Assignment §4 | Team | Partial | `requirements.txt`; `requirements.lock`; tracked source/docs/scripts | Key architecture/threat/postmortem docs and final operational evidence remain absent. |
| No `node_modules`, virtualenvs, personal-data DB dumps, credentials, or private keys in submission | Assignment §4 | Team | Partial | `.gitignore`; tracked-file listing | Perform and record a final archive/secrets review; `git ls-files` alone cannot prove no sensitive content inside files. |

## Section 5A–D — Required proof

| Requirement | Source (section) | Owner | Status | Proof | What is missing |
|---|---|---:|---|---|---|
| A: Start two worker instances | Assignment §5A Required proof | B | Partial | `infra/k8s/base/worker-deployment.yaml`; `compose.yaml` | No preserved real-app proof showing both workers running during the exercise. |
| A: Terminate one worker during processing | Assignment §5A Required proof | B | Missing | No committed fault output | Create isolated deterministic exercise and capture termination during an in-flight job. |
| A: Show order persists and eventually completes exactly once after recovery | Assignment §5A Required proof | A/B | Partial | `tests/worker/`; `worker/processor.py` | No evidence transcript with order/job state and exactly-once business effect before/after recovery. |
| A: Inject deterministic poison job in isolated lab | Assignment §5A Required proof | B | Missing | No committed proof | Add safe reproducible poison-job drill. |
| A: Show poison attempt count | Assignment §5A Required proof | B | Missing | No committed proof | Capture persisted attempt counter across retries. |
| A: Show final failed/operator-review state | Assignment §5A Required proof | B | Partial | `worker/processor.py`; worker tests | Capture real stored failed state and operator visibility. |
| A: Show no infinite retry loop | Assignment §5A Required proof | B | Missing | No committed proof | Include bounded time window and unchanged final attempt count. |
| B: Run at least two API instances against one persistent DB | Assignment §5B Required proof | A/C | Partial | `compose.yaml`; `infra/k8s/base/api-deployment.yaml` | Add captured real-app replica and shared DB state output for the race. |
| B: Eight simultaneous identical requests with same key/payload | Assignment §5B Required proof | A | Partial | `scripts/fulfillops_public_checker.py`; main contract CI | Public checker passes, but no committed transcript explicitly demonstrates the required exact 8 same-key request set against two replicas. |
| B: All eight accepted responses return one stable order ID | Assignment §5B Required proof | A | Partial | API source/tests; checker CI | Preserve response IDs from the explicit test. |
| B: Stock decremented once | Assignment §5B Required proof | A | Partial | API transaction; API tests | Preserve before/after DB query for same-key test. |
| B: Competing different-key orders for remaining inventory | Assignment §5B Required proof | A | Partial | `tests/api/test_api.py`; checker CI | Preserve exact competing-key race and inventory result. |
| B: Demonstrate multi-line SKU aggregation before reservation | Assignment §5B Required proof | A | Partial | `api/orders.py`; checker CI | Add focused output/DB proof. |
| B: Restart one API instance and prove replay remains idempotent | Assignment §5B Required proof | A/C | Missing | No committed restart/replay record | Run against persistent DB and preserve response and stock query. |
| B: Required proof includes tests, order/inventory queries, and DB-boundary diagram/ADR | Assignment §5B Required proof | A/team | Partial | `tests/api/`; API source; migrations | Queries and diagram/ADR are absent. |
| C: Readiness probes and availability-preserving rolling strategy | Assignment §5C Required proof | C | Done | `infra/k8s/base/api-deployment.yaml` | No gap in configured strategy/probes. |
| C: Continuous timestamped 30-second health probe during good update | Assignment §5C Required proof | C | Missing | `scripts/fulfillops_rollout_probe.py`; no CSV committed | Run and commit `docs/rolling_update_probe.csv` plus revision/time metadata. |
| C: Inject broken revision/readiness; detect unhealthy rollout and stop promotion | Assignment §5C Required proof | C | Partial | `scripts/drill-broken-release.sh` | No committed run log proving halted real-app rollout. |
| C: Recover to known-good Git revision through GitOps | Assignment §5C Required proof | C | Partial | `scripts/drill-broken-release.sh`; `scripts/release.sh` | Capture Git revision and Argo reconciliation on actual drill; no final manual cluster patch. |
| C: Preserve deployment events | Assignment §5C Required proof | C | Missing | No committed event log | Save relevant `kubectl describe`/event output. |
| C: Preserve before/after Git revisions | Assignment §5C Required proof | C | Missing | No committed drill record | Record exact SHAs and recovery operation. |
| C: Preserve probe log | Assignment §5C Required proof | C | Missing | No CSV committed | Commit timestamped 30-second probe output. |
| C: Preserve Argo reconciliation evidence | Assignment §5C Required proof | C | Partial | Stub-era `docs/evidence/drift-20261111T121029Z.txt` | Repeat against real image and broken rollout. |
| C: Prove no committed-order loss | Assignment §5C Required proof | A/B/C | Missing | No committed incident record | Query order before/after broken release and recovery. |
| C: Explain rollback versus fix-forward | Assignment §5C Required proof | Team | Missing | No ADR/postmortem rationale | Document why recovery choice fits the observed fault. |
| D: Record at least 200 local HTTP samples | Assignment §5D Required proof | C | Partial | `docs/evidence/prometheus-20261111T122643Z.txt` | Stub-based 250-request record exists; repeat on real image. |
| D: State local measurement limitations | Assignment §5D Required proof | Team | Partial | `docs/evidence/prometheus-20261111T122643Z.txt` | Add limitations for real-image measurement, host load, sample distribution, and lack of production traffic. |
| D: CI publishes machine-readable SBOM for built image | Assignment §5D Required proof | C | Done | SBOM job [131958151474](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151474); `.github/workflows/ci.yml` | Download/retain the artifact in final submission package. |
| D: CI runs vulnerability scan | Assignment §5D Required proof | C | Done | Scan job [131958151451](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151451) | None for scan execution. |
| D: Distinguish blocking and informational scan findings | Assignment §5D Required proof | C | Done | `docs/ci-cd.md`; `.github/workflows/ci.yml`; scan job | None for policy/configuration. |
| D: Document intentional fail-to-green pipeline transition | Assignment §5D Required proof | C | Partial | `docs/evidence/red-green.md`; PR #14 | Demonstration is stub-image dependency scan; clarify that it is not real-image evidence. |
| D: Record final immutable image digest/tag | Assignment §5D Required proof | C | Partial | Publish job [131958729482](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958729482); `docs/environment-person-C.md` | Publish job proves publication, but committed environment note has an older stub digest; add current real image digest/tag. |
| D: Required raw sample summary and metric query/calculation | Assignment §5D Required proof | C | Partial | `docs/evidence/prometheus-20261111T122643Z.txt` | Existing sample/query record is stub-based; regenerate and store real-app raw summary/query. |
| D: Required SBOM artifact/manifest and scan logs | Assignment §5D Required proof | C | Partial | CI SBOM/scan jobs linked above | CI artifacts are available in the run, but no committed/downloaded evidence bundle is linked from the repository. |
| D: PR workflow link | Assignment §5D Required proof | C | Done | [PR #16](https://github.com/Karma-Soliman/fulfillops/pull/16); main CI run | None. |

## Four hard acceptance gates

| Requirement | Source (section) | Owner | Status | Proof | What is missing |
|---|---|---:|---|---|---|
| Gate 1: Same-key concurrency across API replicas | Assignment §5 hard gates | A | Partial | `api/orders.py`; main contract CI [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | Explicit eight-request/two-replica/inventory evidence is not committed. |
| Gate 2: Worker crash recovery and bounded poison retries | Assignment §5 hard gates | B | Partial | Worker implementation/tests | No live worker-kill recovery and poison-job proof artifact. |
| Gate 3: Halt unhealthy rollout and restore through GitOps | Assignment §5 hard gates | C | Partial | `scripts/drill-broken-release.sh`; stub drift evidence | No real-app broken-release and Git restoration log. |
| Gate 4: CI-produced SBOM plus enforced quality gate | Assignment §5 hard gates | C | Done | Main SBOM and scan jobs [43446679146](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146); `.github/workflows/ci.yml` | Retain artifact and scan evidence with final submission. |

## Section 9 — Submission items 1–6

| Requirement | Source (section) | Owner | Status | Proof | What is missing |
|---|---|---:|---|---|---|
| Repository URL | Assignment §9.1 | Team | Done | https://github.com/Karma-Soliman/fulfillops | None. |
| Instructor access explicitly granted | Assignment §9.1 | Team | Missing | No committed proof | Verify repository visibility/access with instructor. |
| Default branch is `main` | Assignment §9.1 | Team | Done | GitHub repository; `origin/main` | None. |
| Readable commit/PR history | Assignment §9.1 | Team | Done | GitHub PR history, including PRs #14, #16, #17 | None observed. |
| Contribution evidence | Assignment §9.1 | Team | Missing | None found in README/docs | Add individual contribution notes. |
| PDF report, maximum eight pages | Assignment §9.2 | Team | Missing | No report PDF tracked | Produce compliant report with architecture, tests, pipeline, deployment, incident, limitations, credits. |
| Demo <=15 minutes, video or live presentation | Assignment §9.3 | Team | Missing | No demo artifact tracked | Record or schedule demo covering all required scenarios. |
| Demo: failing test and successful replay | Assignment §9.3 | Team | Missing | No demo artifact | Include both steps in the demo. |
| Demo: cross-replica same-key and competing-key races | Assignment §9.3 | A | Missing | No demo artifact | Include real API replicas and output. |
| Demo: worker crash and poison handling | Assignment §9.3 | B | Missing | No demo artifact | Include worker recovery and bounded retries. |
| Demo: Kubernetes/GitOps rolling recovery | Assignment §9.3 | C | Missing | No demo artifact | Include broken revision, probe, Git recovery, Argo state. |
| Demo: incident timeline | Assignment §9.3 | Team | Missing | No postmortem/demo artifact | Create timeline and present it. |
| Fresh isolated public checker: exact command/options | Assignment §9.4 | C/team | Done | `scripts/fulfillops_public_checker.py`; main contract job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | Use fresh test DB as CI does; preserve output in final submission. |
| Checker has 15 passed, no skips | Assignment §9.4 | C/team | Done | Main contract CI checker artifact/job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | Download/retain exact checker output as submission evidence. |
| CI run URLs | Assignment §9.5 | C | Done | [Main CI run](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146) | Put links in report. |
| SBOM and scan artifacts | Assignment §9.5 | C | Partial | Main CI SBOM [131958151474](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151474); scan [131958151451](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151451) | Attach/download artifacts for final submission. |
| Final image digest or immutable tag | Assignment §9.5 | C | Partial | Publish job [131958729482](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958729482) | Add current real-app digest to committed environment/evidence docs. |
| Installation and teardown commands | Assignment §9.5 | C | Done | `README.md`; `Makefile` | None. |
| Two-worker resilience evidence | Assignment §9.6 | B | Partial | `worker/`; worker tests | No live crash/recovery evidence. |
| Poison-job evidence | Assignment §9.6 | B | Missing | No committed proof | Add attempt/final-state evidence. |
| 30-second rollout CSV | Assignment §9.6 | C | Missing | No `docs/rolling_update_probe.csv` | Run probe during update and commit CSV. |
| Individual README note: implemented/reviewed/improve | Assignment §9.6 | Team | Missing | No individual notes found | Each member adds a short note. |

## Setup guide — §8 Submission checklist

| Requirement | Source (section) | Owner | Status | Proof | What is missing |
|---|---|---:|---|---|---|
| Git repository and instructor access verified | Setup guide §8 checklist 1 | Team | Partial | GitHub repository https://github.com/Karma-Soliman/fulfillops | Instructor access confirmation is not recorded. |
| Source, lockfiles, migrations, tests, Compose and Kubernetes committed | Setup guide §8 checklist 2 | Team | Done | `api/`; `worker/`; `requirements.lock`; `db/migrations/`; `tests/`; `compose.yaml`; `infra/k8s/` | None for listed artifact presence. |
| README has exact fresh-install and teardown commands | Setup guide §8 checklist 3 | C | Done | `README.md`; `Makefile` | None observed. |
| 15 public checker checks pass on fresh isolated database with concurrency/stress | Setup guide §8 checklist 4 | C/team | Done | Main CI contract job [131958151540](https://github.com/Karma-Soliman/fulfillops/actions/runs/43446679146/job/131958151540) | Archive its checker output for the submission. |
| PR pipeline has red-to-green evidence, SBOM, and scan artifact | Setup guide §8 checklist 5 | C | Partial | `docs/evidence/red-green.md`; PR #14; main SBOM/scan run | Red-green proof targets stub; preserve current real-app SBOM/scan artifacts. |
| Docker build and Compose evidence, persistent order after restart | Setup guide §8 checklist 6 | C/A | Partial | Main build/contract CI; `compose.yaml`; `docs/evidence/image-size.md` | No committed persistence-after-restart transcript for real order data. |
| kind/Argo deployment evidence, drift reconciliation, two API and two worker pods | Setup guide §8 checklist 7 | C | Partial | `infra/k8s/`; `infra/argocd/`; stub drift file | Repeat on real image and save pod/Argo/drift output. |
| Two fault injections, retry/dead-letter, 30-second probe, recovery, metrics, SLO, postmortem | Setup guide §8 checklist 8 | B/C/team | Partial | Drill scripts; stub metrics evidence | Real fault outputs, CSV, SLO statement, and postmortem are missing. |
| <=8-page report and 12–15-minute demo | Setup guide §8 checklist 9 | Team | Missing | No report/demo committed | Produce both and verify limits. |
| Individual contributions and assistance disclosures | Setup guide §8 checklist 10 | Team | Partial | `docs/assistance-log.md` | Assistance log exists; individual contribution notes are missing. |
| No secrets, production/personal data, or instructor files in student ZIP | Setup guide §8 checklist 11 | Team | Partial | `.gitignore`; tracked file listing | Final ZIP content scan/review not recorded. |

## Missing work by owner, ordered by rubric points

The rubric assigns points by category, not by individual deliverable. The ordering below follows the relevant category weights; shared items are listed under the team and are not an additional point allocation.

### A — API, persistence, concurrency (12 points; concurrency alone 16 points)

1. **16-point concurrency gate:** preserve explicit eight-identical-key cross-replica run, stable response IDs, one stock decrement, competing-key result, and inventory/order queries. Current source and checker pass, but proof is incomplete.
2. **12-point API/persistence evidence:** record replay after API restart with DB query, accepted-order survival across process/container restart, and multi-line aggregation proof.
3. **10-point test evidence:** add/record two independently owned race tests as required by WP3, including distinct-key and identical-key races; keep CI-readable output.

### B — worker reliability (9 points)

1. **9-point hard gate:** run two workers; kill one while processing; show persisted job/order reclaimed and exactly one business effect.
2. **9-point poison path:** show deterministic poison attempt count, bounded retry completion, persisted `failed`/operator-review state, and no retry loop.
3. Preserve sanitized before/during/after logs and worker metrics for the exercise.

### C — CI, containers, Kubernetes, observability (9 + 9 + 6 + 5 points)

1. **9-point Kubernetes/GitOps:** repeat drift proof on real image; execute broken readiness/revision drill and restore by Git; save events, Argo reconciliation, revisions, and no-order-loss proof.
2. **9-point CI/supply chain:** retain current main SBOM/scan artifacts; update committed docs with the real image digest; distinguish stub red-green record from real-app evidence and, if needed, demonstrate real-app fail-to-green.
3. **6-point Compose/Docker:** preserve `id`/container-user output and persistent real order across restart; current Compose/real CI configuration exists.
4. **5-point observability/incident:** regenerate 200+ sample p95/query evidence on real image, state limitations and SLO, commit 30-second rollout CSV, and write the incident postmortem.

### Team — architecture, security, tests, submission, defense

1. **12-point architecture/API/persistence:** create `docs/architecture.md` (diagram) and `docs/ADR-001.md`.
2. **10-point tests/red-green:** add test matrix and app-level failure-detection/recovery evidence; the existing red-green dependency scan used the stub.
3. **4-point security:** write `docs/threat-model.md` with at least five realistic threats; document least privilege and safe-log review.
4. **20-point individual defense:** prepare each member for architectural reasoning, code walkthrough, failure diagnosis, security/reliability/CI/GitOps questions; this is evaluated live.
5. Submission: create <=8-page PDF, <=15-minute demo, individual contribution notes, verify instructor access, and archive CI artifacts/checker output.

### Priority summary by rubric weight

| Rubric category | Points | Highest-impact remaining proof |
|---|---:|---|
| Atomic concurrency, cross-replica idempotency | 16 | Explicit 8-request run and persisted stock/order evidence. |
| Architecture, API correctness and persistence | 12 | Architecture/ADR and restart/replay/persistence evidence. |
| Automated tests, red-green and fault injection | 10 | Owned race tests, app failure/recovery, worker and rollout fault outputs. |
| Worker retries/dead-letter | 9 | Two-worker kill/recovery plus poison attempt/final-state proof. |
| Kubernetes/Argo CD | 9 | Real-app drift and broken-release recovery evidence. |
| CI/supply chain | 9 | Retain artifacts and document current real-image digest; current main CI is green. |
| Docker/Compose | 6 | Persisted-order restart transcript and actual non-root inspection. |
| Observability/incident | 5 | Real-app samples/p95, 30-second CSV, SLO, postmortem. |
| Security/threat model | 4 | Threat model and end-to-end least-privilege/safe-log review. |
| Individual defense | 20 | Live preparation; no static artifact substitutes for oral evaluation. |


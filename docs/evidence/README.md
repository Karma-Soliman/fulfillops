# Release drill evidence

Each `rolling-update-<UTC timestamp>/` directory records the pre- and post-rollout Kubernetes and Argo CD state, ReplicaSets, events, and a 30-second readiness probe CSV; it proves a harmless GitOps change rolled the API without failed requests. Each `broken-release-<UTC timestamp>/` directory records the bad rollout halted by readiness and the progress deadline, availability samples while the old pods serve traffic, the Git revert recovery, and a manifest diff against the known-good revision. The rolling drill also copies its probe CSV to `docs/rolling_update_probe.csv` for the assessment hand-in path.

## Gate 1 — API idempotency and transactional stock reservation

`gate1-idempotency-20261113.txt` records a reproducible proof against the Docker Compose test stack, with two healthy API replicas behind the nginx load balancer. Run `python scripts/gate1_idempotency_demo.py` with the isolated `fulfillops-test` stack running and its database clean. The script verifies eight simultaneous requests using the same idempotency key create one order and reserve stock once; two competing requests with different keys cannot oversell inventory; and replaying the original request after restarting one API replica returns the original order ID without creating duplicates. Database snapshots are captured before and after each stage.

# Evidence index

## Stub-era evidence (infrastructure mechanics only)

These files were generated before the real application image was deployed. They show that the infrastructure paths and observability wiring worked with the temporary stub; they are not end-to-end proof for the real API or worker:

- `drift-20261111T121029Z.txt` and `drift-20261113T171209Z.txt`
- `prometheus-20261111T122643Z.txt` and `prometheus-20261113T171238Z.txt`
- `image-size.md`
- `red-green.md` (the CI vulnerability gate demonstration used the stub image)

## Real-application evidence (end-to-end)

- `drift-20261113T174208Z.txt` records Argo CD correcting a replica-count drift on the real app.
- `prometheus-20261113T174220Z.txt` records four real API/worker scrape targets, API request rate, and API histogram p95 using catalog GET traffic.
- `rolling-update-20261113T180034Z/` contains before/after cluster snapshots, a 30-second readiness probe, and `summary.md`; all 120 probes succeeded. Its CSV is also copied to `../rolling_update_probe.csv`.
- `broken-release-20261113T180416Z/` records the readiness failure, `ProgressDeadlineExceeded`, old-pod availability, Git revert recovery, unchanged order count, and empty manifest diff.
- `real-app-ops-20261113T182049Z.md` records UID 10001, healthy workers, and an order that remained completed across a non-destructive Compose restart.

## Partial real-application run

`rolling-update-20261113T174258Z/` is retained to document the first real-app rollout attempt. Its probe passed 120/120, but the script exited before after-snapshots and summary generation due to the strict-mode Argo status parser bug fixed in PR #26. See the complete rerun above.

The complete rolling-update drill records the pre- and post-rollout Kubernetes and Argo CD state, ReplicaSets, events, and a 30-second readiness probe CSV. The broken-release drill records the failed rollout and its recovery through Git and Argo CD. The standalone worker test artifacts under `worker-20261113T092847Z-7e0a2f/` are real application test evidence rather than stub evidence.

# Broken release and Git revert drill

- Drill started: 2026-11-13T18:04:16Z
- Bad revision merged: 2026-11-13T18:07:47Z (779751bae7320190fb0378cf448c67c7bf86889e)
- Halt detected: 2026-11-13T18:09:38Z (90 seconds; ProgressDeadlineExceeded, Argo Degraded)
- Revert merged: 2026-11-13T18:15:10Z (1bf6538abb11361b004f9a3f0337f16fbbf58516)
- Argo Healthy again: 2026-11-13T18:17:52Z
- Known-good revision: 4c85863607a0332f5862e47b47cdf1d433748c2a
- Bad revision: 779751bae7320190fb0378cf448c67c7bf86889e
- Recovery revision: 1bf6538abb11361b004f9a3f0337f16fbbf58516
- Deployment halted because the API readiness probe failed at /health/broken. With maxUnavailable 0, the old ready replicas stayed available; ProgressDeadlineExceeded stopped the rollout.
- Availability samples: 599
- Availability failures: 0 (expected 0)
- Orders count before/after: 2 / 2 (SKIP means the stub has no orders table)
- Manifest diff against known-good: empty; see known-good-manifest-diff.txt.

## Rollback versus fix-forward

The Git revert was chosen because a known-good revision exists, the correct fix is not yet known, and this drill made no schema migration. Reverting restores the reviewed manifest state through the normal PR and Argo CD path.

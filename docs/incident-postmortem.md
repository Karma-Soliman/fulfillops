# Incident Postmortem â€“ Broken Release and Git Revert Drill

**Date:** 13 November 2026
**Environment:** FulfillOps Kubernetes environment
**Incident type:** Deliberately introduced deployment failure (controlled drill)
**Severity:** No recorded service outage during the drill
**Status:** Recovered

## 1. Summary

On 13 November 2026, we performed a controlled deployment failure drill to verify that FulfillOps could detect an unhealthy API release, stop the rollout and recover through GitOps.

The test introduced an invalid API readiness probe path: `/health/broken`. The new API pods could not become ready, so Kubernetes stopped the rollout after the deployment exceeded its progress deadline.

The previous healthy replicas remained available because the deployment was configured with `maxUnavailable: 0`. Availability monitoring recorded 599 successful samples and zero failures during the drill.

The team reverted the bad Git change. Argo CD reconciled the cluster with the known-good configuration and returned to Healthy.

No order-count change was observed: the database contained two orders both before and after the drill.

This was an intentional test, not an unplanned production incident.

## 2. Impact

Observed impact:

- The new API ReplicaSet could not become ready.
- The deployment reported `ProgressDeadlineExceeded`.
- Argo CD reported a Degraded state while the bad revision was applied.
- Existing ready API replicas remained available.
- Availability monitoring recorded 599 samples and zero failures.
- The order count remained at two before and after the drill.

The evidence demonstrates that the rollout was halted without recorded availability failures. It does not establish that every possible client operation was tested during the drill.

## 3. Timeline

All timestamps are UTC.

| Time | Event |
|---|---|
| 18:04:16 | Drill started and baseline evidence collected. |
| 18:07:47 | Bad revision `779751bae7320190fb0378cf448c67c7bf86889e` merged. |
| 18:09:38 | Rollout halt detected after 90 seconds. Kubernetes reported `ProgressDeadlineExceeded`; Argo CD was Degraded. |
| 18:15:10 | Revert revision `1bf6538abb11361b004f9a3f0337f16fbbf58516` merged. |
| 18:17:52 | Argo CD returned to Healthy after reconciliation. |

## 4. Technical Cause

The bad revision configured the API readiness probe to use `/health/broken` instead of the application's valid readiness endpoint.

As a result, the new API pods failed readiness checks and could not become available.

Kubernetes stopped the rollout after the progress deadline was exceeded. The deployment's `maxUnavailable: 0` setting protected the existing ready replicas from being removed while the replacement pods were unhealthy.

The failure was therefore contained by the deployment's readiness and rollout configuration.

## 5. Detection and Recovery

The deployment conditions showed:

- `Available=True`, with reason `MinimumReplicasAvailable`.
- `Progressing=False`, with reason `ProgressDeadlineExceeded`.

The team chose a Git revert rather than a fix-forward change because a known-good revision was available and the correct fix had not yet been established. The drill did not involve a database schema migration.

After the revert was merged, Argo CD reconciled the cluster to the known-good configuration.

The recovered deployment reported:

- `Available=True`, with reason `MinimumReplicasAvailable`.
- `Progressing=True`, with reason `NewReplicaSetAvailable`.

Argo CD returned to Healthy at 18:17:52 UTC.

## 6. What Went Well

- Readiness checks prevented unhealthy replacement pods from becoming available.
- The rollout configuration preserved the old healthy replicas.
- The failure was detected through Kubernetes deployment conditions and Argo CD status.
- Availability monitoring recorded zero failed samples.
- The Git revert restored the known-good configuration through the normal GitOps workflow.
- The order count remained unchanged throughout the drill.

## 7. Lessons Learned

- A successful container start does not necessarily mean an application is ready to serve traffic.
- Readiness probe paths must match real application endpoints.
- Keeping existing replicas available during a rollout is important for service continuity.
- Deployment health must be checked at both the Kubernetes and GitOps levels.
- A known-good Git revision provides a clear recovery path when the correct fix is not yet known.

## 8. Follow-up Actions

| Action | Purpose |
|---|---|
| Validate probe paths during CI or deployment review. | Catch invalid readiness endpoints before deployment. |
| Keep readiness and liveness checks separate. | Distinguish application availability from process health. |
| Preserve rollout availability settings. | Avoid removing healthy replicas before replacements are ready. |
| Keep timestamped rollout and availability evidence. | Make future deployment failures easier to investigate. |
| Repeat the failure drill after significant deployment changes. | Verify that recovery protections continue to work. |

These are follow-up improvements and review practices, not claims that every item is already automated.

## 9. Evidence

Evidence is stored in:

`docs/evidence/broken-release-20261113T180416Z/`

Important files:

- `summary.md` â€“ drill timeline and result.
- `availability.log` â€“ timestamped availability samples.
- `before-deployment-conditions.txt` â€“ deployment state before the bad release.
- `halted-deployment-conditions.txt` â€“ rollout failure conditions.
- `halted-workloads.txt` â€“ workload state during the failed rollout.
- `recovered-deployment-conditions.txt` â€“ deployment state after recovery.
- `recovered-workloads.txt` â€“ workload state after recovery.
- `orders-count.txt` â€“ order count before and after the drill.
- `known-good-manifest-diff.txt` â€“ comparison against the known-good manifest.

## 10. Conclusion

The controlled drill demonstrated that FulfillOps could detect an unhealthy API release, halt the rollout while preserving existing availability, and recover through a Git revert followed by Argo CD reconciliation.

The result supports the project's deployment resilience design, while further testing is still needed for other failure scenarios.
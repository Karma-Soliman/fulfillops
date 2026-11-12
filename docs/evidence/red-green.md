# Trivy red-to-green gate evidence

- PR: https://github.com/Karma-Soliman/fulfillops/pull/14
- Red run (deliberately vulnerable image): https://github.com/Karma-Soliman/fulfillops/actions/runs/43080402689
- Green run (dependency removed): https://github.com/Karma-Soliman/fulfillops/actions/runs/43080798851
- Red commit: `123424d6462bfc6c8dcb59de57bec399cfac7051`
- Green commit: `be9f40fb8a5ca432e41673ef3ff3f4a6e2957ad6`

## Finding and gate result

The red image included `urllib3==1.26.4`. Trivy 0.70.0 reported CVE-2021-33503 as HIGH,
with fixed version 1.26.5; the same scan also reported other HIGH urllib3 findings. The blocking
`scan` job failed with exit code 1. The `publish` job was skipped, so the vulnerable image was not
published. Build, test, lint, contract, and SBOM passed on the red run.

The green commit removed the extra urllib3 dependency and its lockfile entry. A local scan of the
rebuilt image with the same pinned Trivy version and blocking flags exited 0 with no HIGH/CRITICAL
findings. On the green run, build, test, lint, contract, SBOM, and scan passed; publish was skipped
because this is a pull request.

## Policy applied

From `docs/ci-cd.md`: “Trivy blocks the pipeline on fixable HIGH or CRITICAL findings
(`ignore-unfixed: true`). Findings without an available fix do not block because there is no
actionable patch to apply yet; they are still included in the informational report.”

The workflow's blocking scan uses Trivy v0.70.0, `severity: HIGH,CRITICAL`,
`ignore-unfixed: true`, and `exit-code: 1`.

# Development environment

Reference machine used by Person C for the Compose, kind and Argo CD work.
Recorded on 2026-11-10. Teammates with a different setup should add their own section below.

## Published images (from CI publish job)

| Date       | Commit  | Image                                                                     | Digest                                                                  | CI run                                                               |
| ---------- | ------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------------------- |
| 2026-11-11 | 7287fd9 | ghcr.io/karma-soliman/fulfillops:7287fd9d098f190e388fb368935626b134de22ef | sha256:d02e181fa820d64e1fadfe98d5dcc5c05e39dc1d91f007b04f80056a018968a3 | https://github.com/Karma-Soliman/fulfillops/actions/runs/42992492491 |

## Host

| Item                     | Value                                                             |
| ------------------------ | ----------------------------------------------------------------- |
| Machine                  | MacBook Pro, Apple Silicon                                        |
| Architecture             | `arm64` (`uname -m`)                                              |
| OS                       | macOS (darwin/arm64)                                              |
| Docker Desktop resources | 8 CPUs, 16 GB memory, 1 GB swap (Settings → Resources → Advanced) |

## Tool versions

| Tool                              | Version                          | Command                    |
| --------------------------------- | -------------------------------- | -------------------------- |
| Docker Desktop                    | 4.87.0 (236836)                  | `docker version`           |
| Docker Engine (client and server) | 29.7.2, API 1.55                 | `docker version`           |
| containerd                        | v2.2.5                           | `docker version`           |
| runc                              | 1.3.6                            | `docker version`           |
| Docker Compose                    | v5.4.0                           | `docker compose version`   |
| kind                              | v0.33.0 (go1.27.1, darwin/arm64) | `kind version`             |
| kubectl                           | v1.36.1                          | `kubectl version --client` |
| Kustomize (bundled with kubectl)  | v5.8.1                           | `kubectl version --client` |
| Python                            | 3.12.6                           | `python3 --version`        |

## Architecture note (important)

This laptop is **arm64**, while GitHub Actions runners build **amd64** images by default.
An amd64 image pulled into this kind cluster fails with `exec format error`.

Chosen approach (update if it changes):

- Local kind deployments use images **built on this Mac** (arm64) and copied into the cluster with
  `kind load docker-image fulfillops:<git-sha> --name fulfillops`.
- CI builds and scans the amd64 image and publishes it to GHCR with the same commit SHA tag.
- The commit SHA is the shared identifier across both: same source, same tag, different CPU architecture.
- Alternative not chosen for now: multi-arch builds (`docker buildx --platform linux/amd64,linux/arm64`),
  which are slow in CI because arm64 is emulated.

## Pinned versions used by the project

Filled in as each task pins a version. Every image and tool below must be referenced by an exact
version (and digest where possible), never `latest`.

| Component                     | Pinned version / digest           | Where it is set                           |
| ----------------------------- | --------------------------------- | ----------------------------------------- |
| kind node image (Kubernetes)  | `kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5` | `infra/kind/cluster.yaml` |
| Argo CD                       | TODO (Task 7)                     | `infra/argocd/install/kustomization.yaml` |
| Prometheus                    | TODO (Task 7b)                    | `infra/k8s/base/`, `compose.yaml`         |
| PostgreSQL                    | TODO (Task 3), 16.x               | `compose.yaml`, `infra/k8s/base/`         |
| nginx (Compose load balancer) | TODO (Task 3)                     | `compose.yaml`                            |
| Python base image             | TODO (Task 2), 3.12-slim + digest | `Dockerfile`                              |
| Trivy                         | TODO (Task 4)                     | `.github/workflows/ci.yml`                |
| Syft                          | TODO (Task 4)                     | `.github/workflows/ci.yml`                |

## How to reproduce this record

```bash
uname -m
docker version
docker compose version
kind version
kubectl version --client
python3 --version
```

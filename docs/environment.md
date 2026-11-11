# Pinned local Kubernetes environment

| Component | Version and digest | Defined in |
| --- | --- | --- |
| kind node image | `kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5` | `infra/kind/cluster.yaml` |
| Argo CD | `v3.6.1` | `infra/argocd/install/kustomization.yaml` |

This is the default node image listed in the [kind v0.33.0 release notes](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0). The release notes state that the image supports both amd64 and arm64.

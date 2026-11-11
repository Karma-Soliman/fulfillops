# Local Kubernetes with kind

kind runs Kubernetes nodes as Docker containers. This configuration creates one control-plane
container and one worker container with the Kubernetes v1.37.0 node image pinned to the digest
listed in the kind v0.33.0 release notes.

## Request path

```text
Mac localhost:8080 -> control-plane container:30080 -> NodePort Service -> API pod:8080
```

The control-plane container maps host port 8080 to NodePort 30080. The Service selects the API
pods and forwards traffic to their port 8080. `listenAddress: 127.0.0.1` limits access to this
Mac; other machines on the network cannot connect to this published port.

The host port mapping belongs to the kind node container, so it is set when the cluster is created.
Changing it later requires deleting and recreating the cluster. `cluster-up.sh` checks port 8080
before creation and leaves an existing cluster untouched so the script remains safe to repeat.

## Commands

- `make cluster-up` checks Docker and port 8080, creates the cluster if needed, selects
  `kind-fulfillops`, and prints the nodes.
- `make cluster-smoke` loads the local arm64 stub image, deploys two API replicas behind NodePort
  30080, checks ten liveness responses, tests the default StorageClass with a PVC, and removes its
  temporary `smoke` namespace.
- `make cluster-down` asks before deleting the cluster. Use `./scripts/cluster-down.sh --yes` only
  when intentionally removing it; all data in the cluster, including volumes, is lost.

Compose and kind both use host port 8080. Stop Compose with `make down` before creating kind, and
stop kind before bringing Compose back up.

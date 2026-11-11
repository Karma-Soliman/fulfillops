.PHONY: up down ps logs test-stack-up test-stack-down cluster-up cluster-down cluster-smoke k8s-render k8s-apply k8s-status k8s-delete

# Start the development stack and build its stub image.
up:
	docker compose up -d --build

# Stop the development stack while keeping the named database volume.
down:
	docker compose down

# Show the development service states.
ps:
	docker compose ps

# Follow development service logs.
logs:
	docker compose logs -f

# Start the isolated destructive-checker stack on localhost:8080.
test-stack-up:
	docker compose -f compose.yaml -f compose.test.yaml -p fulfillops-test up -d --build

# Destroy only disposable test containers and their database volume.
test-stack-down:
	docker compose -f compose.yaml -f compose.test.yaml -p fulfillops-test down -v

# Create or reuse the local fulfillops kind cluster.
cluster-up:
	./scripts/cluster-up.sh

# Delete the local fulfillops kind cluster after a confirmation prompt.
cluster-down:
	./scripts/cluster-down.sh

# Exercise the local NodePort and default dynamic storage provisioner.
cluster-smoke:
	./scripts/smoke-cluster.sh

# Render the kind Kustomize overlay to standard output for inspection.
k8s-render:
	kubectl kustomize infra/k8s/overlays/kind

# Create the local Secret and apply the stack, waiting for migration and rollouts.
k8s-apply:
	./scripts/k8s-apply.sh

# Show workload, endpoint, and persistent volume claim state in the app namespace.
k8s-status:
	kubectl -n fulfillops get pods,svc,endpoints,pvc -o wide

# Remove app workloads while retaining the local Secret and database PVC for data safety.
k8s-delete:
	kubectl -n fulfillops delete deployment/fulfillops-api deployment/fulfillops-worker statefulset/postgres job/fulfillops-migrate service/fulfillops-api service/postgres poddisruptionbudget/fulfillops-api configmap/fulfillops-config serviceaccount/fulfillops-app --ignore-not-found=true

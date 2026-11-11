#!/usr/bin/env bash
set -euo pipefail

if ! kind get clusters | grep -Fxq fulfillops; then
  echo "Cluster fulfillops does not exist. Run 'make cluster-up' first." >&2
  exit 1
fi

kubectl config use-context kind-fulfillops
kind load docker-image fulfillops-stub:dev --name fulfillops
kubectl create namespace smoke

cleanup_smoke_namespace() {
  if kubectl get namespace smoke >/dev/null 2>&1; then
    kubectl delete namespace smoke --wait=true --timeout=120s >/dev/null || true
  fi
}
trap cleanup_smoke_namespace EXIT

kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: stub-api
  namespace: smoke
spec:
  replicas: 2
  selector:
    matchLabels:
      app: stub-api
  template:
    metadata:
      labels:
        app: stub-api
    spec:
      containers:
        - name: api
          image: fulfillops-stub:dev
          imagePullPolicy: IfNotPresent
          # The image entrypoint dispatches its api command from this argument.
          args: ["api"]
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/live
              port: 8080
            periodSeconds: 2
            timeoutSeconds: 1
---
apiVersion: v1
kind: Service
metadata:
  name: stub-api
  namespace: smoke
spec:
  type: NodePort
  selector:
    app: stub-api
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      nodePort: 30080
EOF

kubectl -n smoke rollout status deployment/stub-api --timeout=120s
for request in $(seq 1 10); do
  printf 'Request %02d: ' "$request"
  curl --fail --silent --show-error http://localhost:8080/health/live
done

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: smoke-data
  namespace: smoke
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Mi
---
apiVersion: v1
kind: Pod
metadata:
  name: smoke-storage-writer
  namespace: smoke
spec:
  restartPolicy: Never
  containers:
    - name: writer
      image: fulfillops-stub:dev
      imagePullPolicy: IfNotPresent
      command: ["python"]
      args:
        - -c
        - from pathlib import Path; Path('/data/smoke-check').write_text('storage ok')
      volumeMounts:
        - name: smoke-data
          mountPath: /data
  volumes:
    - name: smoke-data
      persistentVolumeClaim:
        claimName: smoke-data
EOF

kubectl -n smoke wait --for=jsonpath='{.status.phase}'=Pending pvc/smoke-data --timeout=30s
echo "PVC state before a pod consumes it:"
kubectl -n smoke get pvc smoke-data -o wide
kubectl -n smoke wait --for=jsonpath='{.status.phase}'=Succeeded pod/smoke-storage-writer --timeout=120s
kubectl -n smoke logs pod/smoke-storage-writer
kubectl -n smoke wait --for=jsonpath='{.status.phase}'=Bound pvc/smoke-data --timeout=60s
echo "PVC state after the writer pod used it:"
kubectl -n smoke get pvc smoke-data -o wide

kubectl delete namespace smoke --wait=true --timeout=120s
trap - EXIT
if kubectl get namespace smoke >/dev/null 2>&1; then
  echo "Namespace smoke still exists after deletion." >&2
  exit 1
fi
echo "Namespace smoke is gone."

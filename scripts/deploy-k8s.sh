#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
: "${IMAGE:?Set IMAGE to the versioned image tag or digest}"
kubectl apply -f k8s/namespace.yaml
python3 scripts/k8s-secret.py
# Render and substitute locally so existing deployments never briefly receive the placeholder image.
kubectl kustomize k8s | IMAGE="$IMAGE" python3 -c 'import os,sys; print(sys.stdin.read().replace("image: school-api:local", "image: " + os.environ["IMAGE"]))' | kubectl apply -f -
kubectl -n school rollout status statefulset/db --timeout=180s
kubectl -n school rollout status deployment/school-api --timeout=180s

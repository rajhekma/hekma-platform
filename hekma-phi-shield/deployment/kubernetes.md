# Kubernetes

## 1. Namespace

```bash
kubectl create namespace privacy
```

## 2. Secrets

Copy `k8s/secret.example.yaml` → `k8s/secret.yaml`, fill values. **Do not commit `secret.yaml`.**

```bash
kubectl apply -f deployment/k8s/secret.yaml -n privacy
```

## 3. Deploy

```bash
kubectl apply -f deployment/k8s/deployment.yaml -n privacy
kubectl apply -f deployment/k8s/service.yaml -n privacy
kubectl get pods -n privacy -w
```

## 4. Verify

```bash
kubectl port-forward -n privacy svc/phi-pii-service 8080:80
curl http://localhost:8080/health
```

Expect `model_loaded: true`. First start can take 1–2 minutes (model load).

## Internal URL

Other pods call:

```
http://phi-pii-service.privacy.svc.cluster.local/predict
```

## Sizing

| Resource | Suggested |
|----------|-----------|
| Memory request | 2 Gi |
| Memory limit | 4 Gi |
| CPU request | 500m |
| Replicas | 1–2 (CPU inference) |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `model_loaded: false` | Rebuild image with real weights (not LFS pointers) |
| Pod OOMKilled | Raise memory limit to 4 Gi |
| Readiness fails early | `initialDelaySeconds` is 60s; wait for model load |
| PHI errors | Set `OPENAI_API_KEY` in Secret |

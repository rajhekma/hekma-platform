# Deployment

Short guides to run **phi-pii-service** in Docker and Kubernetes.

| Doc | What it covers |
|-----|----------------|
| [docker.md](docker.md) | Build and run the container locally |
| [kubernetes.md](kubernetes.md) | Deploy to a Kubernetes cluster |

## What gets deployed

- **PII**: local RoBERTa model (`models/roberta-pii-synthetic/`, ~500 MB)
- **PHI**: OpenAI API (optional; needs `OPENAI_API_KEY`)
- **Port**: `8080`
- **Health**: `GET /health` → `model_loaded: true`

## Before you build

1. Model weights must be real files, not Git LFS pointers (~496 MB `model.safetensors`).
2. Set production secrets via env or K8s Secret — never commit keys.

## Files in this folder

```
deployment/
  README.md
  docker.md
  kubernetes.md
  Dockerfile
  k8s/
    deployment.yaml
    service.yaml
    secret.example.yaml
```

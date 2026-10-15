# Docker

## Prerequisites

- Docker installed
- Model weights present: `wc -c models/roberta-pii-synthetic/model.safetensors` → ~496 MB

## Build

From repo root (`PHI-PII/`):

```bash
docker build -f deployment/Dockerfile -t phi-pii-service:latest .
```

## Run

```bash
docker run --rm -p 8080:8080 \
  -e ENVIRONMENT=production \
  -e OPENAI_API_KEY=your-key \
  phi-pii-service:latest
```

PII-only (no PHI / OpenAI):

```bash
docker run --rm -p 8080:8080 \
  -e ENVIRONMENT=production \
  -e PHI_DETECTOR_BACKEND=openai \
  -e OPENAI_API_KEY= \
  phi-pii-service:latest
```

## Verify

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"text":"John Smith lives at 123 Main St"}'
```

## Push to registry

```bash
docker tag phi-pii-service:latest your-registry/phi-pii-service:1.0.0
docker push your-registry/phi-pii-service:1.0.0
```

Update the image in `k8s/deployment.yaml` before applying to Kubernetes.

# IONOS Managed Kubernetes Deployment Guide

**Service:** `privacy-detection-service`  
**Repository:** `HekmaAI/privacy-detection-service`  
**Target Cluster:** IONOS Cloud Managed Kubernetes (`dev-k8s` / `prod-k8s`)  
**Domain:** `https://pii-phi.hekma.ai` (Prod) & `https://dev-pii-phi.hekma.ai` (Dev)  
**Database:** Existing Application Database (`87.106.50.234:5432/hekmaai`)  

---

## 1. End-to-End Architecture & Traffic Flow

```
========================================================================================================================
                                     IONOS KUBERNETES TOPOLOGY
========================================================================================================================

  [ CLIENT / PIPELINE: hekma_data_pipleline ]
         │
         │  HTTPS 443
         ▼
  [ IONOS DNS / Cloud Load Balancer (Public IP) ]
         │  Route: pii-phi.hekma.ai (Port 443 with TLS Secret)
         ▼
  [ IONOS NGINX Ingress Controller ]
         │  Routes traffic to Service Port 8080
         ▼
  [ Kubernetes ClusterIP Service: privacy-detection-service:8080 ]
         │
         ▼
  [ Kubernetes Pods (2 - 6 Replicas via HPA) ]
  ┌────────────────────────────────────────────────────────────┐
  │  Container: privacy-detection-service (Port 8080)          │
  │  • Fast RoBERTa Token Classification (In-Memory Pre-warmed)│
  │  • Clinical PHI Detector (OpenAI gpt-4o-mini)              │
  │  • Probes: /health (Liveness) & /ready (Readiness)         │
  └────────────────────────────────────────────────────────────┘
         │
         │  Asyncpg Connection Pool (10-20 connections)
         ▼
  [ EXISTING APPLICATION DATABASE (87.106.50.234:5432 / hekmaai) ]
  ┌────────────────────────────────────────────────────────────┐
  │  Application Tables (Fasten Health / EHR Data):            │
  │  • fastenhealth_patients, medications, etc.                │
  │                                                            │
  │  Dedicated Isolated Token Vault Tables:                    │
  │  • token_mappings (AES-256 / HMAC Indexed surrogate vault) │
  │  • policies (Tenant PII handling rules)                    │
  │  • audit_logs (Immutable HIPAA access trail)               │
  │  • organizations (Tenant registry)                         │
  └────────────────────────────────────────────────────────────┘
========================================================================================================================
```

---

## 2. Step-by-Step Deployment Runbook

### Step 1: Connect to IONOS Kubernetes Cluster
Ensure your `kubectl` context is pointing to your IONOS cluster:
```bash
# Verify connection
kubectl cluster-info
kubectl get nodes
```

---

### Step 2: Build & Push Container to Container Registry
Build the Docker image containing the fine-tuned RoBERTa model:
```bash
# Build image
docker build -t registry.ionos.com/hekma/privacy-detection-service:latest .

# Authenticate and push to your container registry (IONOS / Harbor / DockerHub)
docker push registry.ionos.com/hekma/privacy-detection-service:latest
```

---

### Step 3: Create Namespace & Secrets
Apply the Kubernetes namespace, configmap, and secrets:
```bash
# 1. Create namespace
kubectl apply -f k8s/namespace.yaml

# 2. Apply ConfigMap
kubectl apply -f k8s/configmap.yaml

# 3. Apply Secret (Points to hekmaai database)
kubectl apply -f k8s/secret.yaml
```

---

### Step 4: Run Database Migration Job (One-Time / Pre-Deploy)
Run the database migration job to ensure the 4 Token Vault tables exist in `hekmaai`:
```bash
kubectl apply -f k8s/migration-job.yaml

# Check migration logs
kubectl logs -n privacy-detection job/privacy-detection-db-migration -f
```

---

### Step 5: Deploy the Service & Autoscaler
Deploy the pods and ClusterIP service:
```bash
# Apply Deployment, Service, and HPA
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# Check rollout status
kubectl rollout status deployment/privacy-detection-service -n privacy-detection
```

---

### Step 6: Configure Ingress & TLS (Custom Domain)
Apply the Ingress manifest to route `pii-phi.hekma.ai` to the service:
```bash
kubectl apply -f k8s/ingress.yaml

# Check Ingress IP
kubectl get ingress -n privacy-detection
```

* Point your DNS `A` record for **`pii-phi.hekma.ai`** and **`dev-pii-phi.hekma.ai`** to the Ingress Load Balancer IP provided by IONOS.

---

## 3. Health Checks & Verification

Verify that all pods are healthy and the model is warm in RAM:

```bash
# 1. Check Pod Status (All pods should be 1/1 Running)
kubectl get pods -n privacy-detection

# 2. Test Readiness Probe via port-forward
kubectl port-forward -n privacy-detection svc/privacy-detection-service 8080:8080

# 3. In another terminal, verify readiness:
curl http://localhost:8080/ready
# Output: {"status":"ready","database":"connected","model_loaded":true}

# 4. Test Live PII Detection:
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient John Doe with SSN 999-91-1291"}'
```

---

## 4. Rollback & Troubleshooting

* **Rollback to previous revision:**
  ```bash
  kubectl rollout undo deployment/privacy-detection-service -n privacy-detection
  ```
* **View Live Container Logs:**
  ```bash
  kubectl logs -n privacy-detection -l app=privacy-detection-service -f --tail=100
  ```
* **Scale Manually (if needed):**
  ```bash
  kubectl scale deployment/privacy-detection-service --replicas=4 -n privacy-detection
  ```

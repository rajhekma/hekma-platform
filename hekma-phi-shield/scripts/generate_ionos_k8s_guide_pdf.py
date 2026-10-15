"""
Generates the IONOS Managed Kubernetes Deployment & Flow Guide PDF for:
Privacy Detection & Security Service (privacy-detection-service)
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def generate_ionos_pdf():
    pdf_filename = "IONOS_Kubernetes_Deployment_Guide_Privacy_Detection_Service.pdf"
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=2,
    )

    meta_style = ParagraphStyle(
        'MetaBar',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#475569'),
        spaceAfter=6,
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontSize=10.5,
        leading=13.5,
        textColor=colors.HexColor('#1e3a8a'),
        spaceBefore=7,
        spaceAfter=3,
    )

    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=3,
    )

    code_style = ParagraphStyle(
        'CodeSnippet',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#f8fafc'),
        backColor=colors.HexColor('#0f172a'),
        borderPadding=5,
        spaceBefore=3,
        spaceAfter=5,
    )

    story = []

    # Title & Metadata
    story.append(Paragraph("IONOS Managed Kubernetes Deployment & Flow Guide", title_style))
    story.append(Paragraph("<b>Service:</b> privacy-detection-service &nbsp;|&nbsp; <b>Cluster:</b> IONOS Managed K8s &nbsp;|&nbsp; <b>DB:</b> 87.106.50.234:5432/hekmaai", meta_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563eb'), spaceBefore=1, spaceAfter=5))

    # Section 1: Architecture & Topology
    story.append(Paragraph("1. IONOS Kubernetes Production Topology & Traffic Flow", h2_style))
    story.append(Paragraph("The microservice deploys as a highly available, auto-scaling Kubernetes workload on IONOS Cloud, routing HTTPS 443 traffic to container port 8080 and storing token mappings directly in the existing application database (<code>hekmaai</code>).", body_style))

    topo = """[ Consumer: hekma_data_pipleline ]
       │ HTTPS 443
       ▼
[ IONOS Cloud Load Balancer & DNS (pii-phi.hekma.ai) ]
       │
       ▼
[ IONOS NGINX Ingress Controller (TLS Termination) ]
       │
       ▼
[ Kubernetes Service: privacy-detection-service:8080 (ClusterIP) ]
       │
       ▼
[ Pod Replicas (2 - 6 via HPA) | 2 CPU / 4GB RAM ]
  • Pre-Warmed RoBERTa Model in RAM  • OpenAI Clinical PHI Detector
       │
       ▼ (Asyncpg Connection Pool: 10-20 connections)
[ EXISTING APPLICATION DATABASE (87.106.50.234:5432 / hekmaai) ]
  • App Tables: fastenhealth_patients, medications, etc.
  • Dedicated Vault Tables: token_mappings, policies, audit_logs, organizations"""
    story.append(Preformatted(topo, code_style))

    # Section 2: Step-by-Step Deployment Runbook
    story.append(Paragraph("2. Step-by-Step Deployment Runbook (Commands)", h2_style))
    commands = """# 1. Apply Namespace, ConfigMap & Secret:
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# 2. Run Database Migration Job (Initializes 4 vault tables in hekmaai):
kubectl apply -f k8s/migration-job.yaml
kubectl logs -n privacy-detection job/privacy-detection-db-migration -f

# 3. Deploy Workload, Service & Autoscaler:
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# 4. Apply Ingress for Custom Domain (pii-phi.hekma.ai):
kubectl apply -f k8s/ingress.yaml
kubectl rollout status deployment/privacy-detection-service -n privacy-detection"""
    story.append(Preformatted(commands, code_style))

    # Section 3: Kubernetes Resource Matrix
    story.append(Paragraph("3. Kubernetes Manifests Summary in Repository (k8s/)", h2_style))
    k8s_data = [
        ["Manifest File", "Resource Type", "Configuration Details"],
        ["k8s/namespace.yaml", "Namespace", "privacy-detection (Dedicated tenant isolation)"],
        ["k8s/configmap.yaml", "ConfigMap", "CUSTOM_DOMAIN=https://pii-phi.hekma.ai, STORAGE=postgresql"],
        ["k8s/secret.yaml", "Secret", "DATABASE_URL (87.106.50.234:5432/hekmaai), OPENAI_API_KEY"],
        ["k8s/deployment.yaml", "Deployment", "2 Replicas, Requests: 1 CPU/2Gi, Limits: 2 CPU/4Gi, /ready probe"],
        ["k8s/service.yaml", "Service", "ClusterIP exposing Port 8080"],
        ["k8s/ingress.yaml", "Ingress", "NGINX Ingress routing pii-phi.hekma.ai (TLS Enabled)"],
        ["k8s/hpa.yaml", "Autoscaler", "Auto-scales 2 to 6 pods at 70% CPU / 80% RAM"],
        ["k8s/migration-job.yaml", "Job", "Creates token_mappings in hekmaai before pod traffic"],
    ]
    t1 = Table(k8s_data, colWidths=[110, 85, 330])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(t1)
    story.append(Spacer(1, 4))

    # Section 4: Health Probes & Rollback
    story.append(Paragraph("4. Observability Probes & Instant Rollback", h2_style))
    story.append(Paragraph("• <b>Liveness Probe:</b> <code>GET /health</code> on port 8080 (initial delay: 15s)<br/>• <b>Readiness Probe:</b> <code>GET /ready</code> on port 8080 (initial delay: 20s, ensures RoBERTa model is warm in RAM)<br/>• <b>Rollback Command:</b> <code>kubectl rollout undo deployment/privacy-detection-service -n privacy-detection</code><br/>• <b>Live Pod Logs:</b> <code>kubectl logs -n privacy-detection -l app=privacy-detection-service -f --tail=100</code>", body_style))

    doc.build(story)
    print(f"✅ Generated {pdf_filename} successfully!")


if __name__ == "__main__":
    generate_ionos_pdf()

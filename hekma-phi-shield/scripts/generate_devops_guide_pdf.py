"""
Generates the DevOps Deployment & Operations Guide PDF for:
Privacy Detection & Security Service (privacy-detection-service)
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def generate_reportlab_pdf():
    pdf_filename = "DevOps_Deployment_Guide_Privacy_Detection_Service.pdf"
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
    story.append(Paragraph("DevOps Deployment & Operations Guide", title_style))
    story.append(Paragraph("<b>Service:</b> privacy-detection-service &nbsp;|&nbsp; <b>Repository:</b> HekmaAI/privacy-detection-service &nbsp;|&nbsp; <b>DB:</b> Existing App DB (hekmaai)", meta_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563eb'), spaceBefore=1, spaceAfter=5))

    # Section 1: Executive Summary
    story.append(Paragraph("1. Executive Summary & Production Topology", h2_style))
    story.append(Paragraph("The <b>privacy-detection-service</b> provides high-speed PII token classification (sub-40ms RoBERTa) and swappable Clinical PHI detection (OpenAI <code>gpt-4o-mini</code>) storing encrypted surrogate mappings directly in the application database (<code>hekmaai</code>).", body_style))

    topo_text = """[ hekma_data_pipleline (Lambda / ECS API) ]
       │ HTTPS 443 (Persistent Connection Pool)
       ▼
[ Route 53 / DNS (pii-phi.hekma.ai) ] ──> [ Load Balancer / Ingress (HTTPS:443 -> Port 8080) ]
       │
       ▼
[ Container Workload: privacy-detection-service (2 CPU / 4GB RAM) ]
       │
       ▼ (Asyncpg Connection Pool: 10-20 connections)
[ EXISTING APPLICATION DATABASE (87.106.50.234:5432 / hekmaai) ]
  • App Tables: fastenhealth_patients, medications, etc.
  • Dedicated Vault Tables: token_mappings, policies, audit_logs, organizations"""
    story.append(Preformatted(topo_text, code_style))

    # Section 2: Multi-Branch & Multi-Environment Matrix
    story.append(Paragraph("2. Multi-Branch & Multi-Environment Matrix", h2_style))
    matrix_data = [
        ["Git Branch", "Environment", "Custom Domain Endpoint", "Database", "Service / Deployment Name"],
        ["develop / dev / Pii", "development", "https://dev-pii-phi.hekma.ai", "hekmaai", "privacy-detection-service-dev"],
        ["demo", "demo", "https://demo-pii-phi.hekma.ai", "hekma_demo", "privacy-detection-service-demo"],
        ["staging", "staging", "https://staging-pii-phi.hekma.ai", "hekma_staging", "privacy-detection-service-staging"],
        ["main", "production", "https://pii-phi.hekma.ai", "hekma_prod / hekmaai", "privacy-detection-service-production"],
    ]
    t1 = Table(matrix_data, colWidths=[65, 65, 140, 95, 155])
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

    # Section 3: Container & Compute Specifications
    story.append(Paragraph("3. Container & Compute Specifications", h2_style))
    story.append(Paragraph("• <b>Compute:</b> <b>2 CPU (2000m)</b> and <b>4 GB RAM (4096 MB)</b>.<br/>• <b>Process Manager:</b> Gunicorn with 2 Uvicorn async workers on container port <code>8080</code>.<br/>• <b>Security:</b> Runs as non-root user <code>appuser</code> (UID 1001) with read-only root filesystem.<br/>• <b>Warmup:</b> RoBERTa model weights load during <code>lifespan</code> startup for instant sub-40ms inference.", body_style))

    # Section 4: Environment Variables & Secrets Reference
    story.append(Paragraph("4. Environment Variables & Secrets Reference", h2_style))
    env_data = [
        ["Variable Name", "Source", "Purpose / Sample Value"],
        ["DATABASE_URL", "Kubernetes Secret / Vault", "postgresql+asyncpg://admin:SECRET@host:5432/hekmaai"],
        ["OPENAI_API_KEY", "Kubernetes Secret / Vault", "sk-proj-... (Used strictly for clinical notes)"],
        ["CUSTOM_DOMAIN", "ConfigMap / Env", "https://pii-phi.hekma.ai (Portless clean URL)"],
        ["STORAGE_BACKEND", "ConfigMap / Env", "postgresql (or json for zero-database test mode)"],
    ]
    t2 = Table(env_data, colWidths=[120, 110, 290])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
    ]))
    story.append(t2)
    story.append(Spacer(1, 4))

    # Section 5: Database Migration Runbook
    story.append(Paragraph("5. Database Migration Runbook", h2_style))
    story.append(Paragraph("Creates 4 isolated tables directly in <code>hekmaai</code>: <code>token_mappings</code>, <code>policies</code>, <code>audit_logs</code>, and <code>organizations</code>.", body_style))
    mig_text = """# Automated Multi-Environment CLI Migration:
./scripts/migrate_database.sh dev
./scripts/migrate_database.sh demo
PROD_DATABASE_URL="postgresql+asyncpg://admin:SECRET@host:5432/hekma_prod" ./scripts/migrate_database.sh prod"""
    story.append(Preformatted(mig_text, code_style))

    # Section 6: Health Probes & Rollback
    story.append(Paragraph("6. Observability Probes & Rollback", h2_style))
    story.append(Paragraph("• <b>Liveness Probe:</b> <code>GET /health</code> &nbsp;|&nbsp; <b>Readiness Probe:</b> <code>GET /ready</code> &nbsp;|&nbsp; <b>Metrics:</b> <code>GET /metrics</code><br/>• <b>Rollback:</b> <code>kubectl rollout undo deployment/privacy-detection-service -n privacy-detection</code>", body_style))

    doc.build(story)
    print(f"✅ Generated {pdf_filename} successfully!")


if __name__ == "__main__":
    generate_reportlab_pdf()

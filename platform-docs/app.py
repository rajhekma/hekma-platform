"""Hekma platform API catalog + Swagger, grouped by microservice."""

from __future__ import annotations

import copy
import os
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

DOCS_PORT = int(os.getenv("PLATFORM_DOCS_PORT", "8099"))
DOCS_PUBLIC_URL = os.getenv("PLATFORM_DOCS_PUBLIC_URL", f"http://127.0.0.1:{DOCS_PORT}").rstrip("/")

EXTRACTED = [
    {
        "id": "patient-health",
        "code": "S3",
        "name": "Patient Health",
        "port": int(os.getenv("PATIENT_HEALTH_PORT", "8010")),
        "origin": os.getenv("PATIENT_HEALTH_URL", "http://127.0.0.1:8010").rstrip("/"),
        "summary": "Profile, Fasten EHR, FHIR, medications, HealthKit, account deletion.",
    },
    {
        "id": "scanner",
        "code": "S4",
        "name": "Scanner",
        "port": int(os.getenv("SCANNER_PORT", "8011")),
        "origin": os.getenv("SCANNER_URL", "http://127.0.0.1:8011").rstrip("/"),
        "summary": "Clinical document scan (MS-11) and EHR summary (MS-13).",
    },
    {
        "id": "ai-usage",
        "code": "AI",
        "name": "AI Usage",
        "port": int(os.getenv("COMMERCE_PORT", "8090")),
        "origin": os.getenv("AI_USAGE_URL", "http://127.0.0.1:8090").rstrip("/"),
        "summary": "Per-patient AI cost, event list, prices, and internal ingest.",
    },
]

NOT_EXTRACTED = [
    {
        "code": "S1",
        "name": "Identity & Access",
        "host": "hekma_api :8080",
        "summary": "Login, JWT, session, signup, password reset. Still Java.",
        "routes": ["/login", "/auth", "/session", "/signup", "/forgetpassword"],
    },
    {
        "code": "S2",
        "name": "CTMS",
        "host": "hekma_api :8080",
        "summary": "Studies, sites, sponsors, enrollment, support, webhooks. Still Java.",
        "routes": ["/graphql", "/api/v1/support", "/webhook"],
    },
    {
        "code": "S5",
        "name": "Trial Matching",
        "host": "TrialGPT",
        "summary": "Patient↔trial matching. Called when TRIALGPT_* env is set.",
        "routes": ["/api/internal/trial-gpt-ehr/ingest"],
    },
    {
        "code": "S6",
        "name": "PHI Shield",
        "host": "PHI-PII",
        "summary": "De-identification. Called when PRIVACY_SERVICE_ENABLED is set.",
        "routes": ["PRIVACY_SERVICE_URL"],
    },
]

SKIP_MERGE_PATHS = {"/health", "/ready", "/docs", "/redoc", "/openapi.json"}

app = FastAPI(
    title="Hekma Platform APIs",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _by_id(service_id: str) -> dict[str, Any]:
    for item in EXTRACTED:
        if item["id"] == service_id:
            return item
    raise HTTPException(status_code=404, detail=f"Unknown service: {service_id}")


def _count_operations(spec: dict[str, Any]) -> int:
    total = 0
    for item in (spec.get("paths") or {}).values():
        if not isinstance(item, dict):
            continue
        total += sum(
            1
            for method, op in item.items()
            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}
            and isinstance(op, dict)
        )
    return total


def _rewrite_refs(node: Any, prefix: str) -> Any:
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/components/"):
                parts = value.split("/")
                if len(parts) >= 4:
                    parts[-1] = f"{prefix}{parts[-1]}"
                    value = "/".join(parts)
            out[key] = _rewrite_refs(value, prefix)
        return out
    if isinstance(node, list):
        return [_rewrite_refs(item, prefix) for item in node]
    return node


def _namespace_spec(spec: dict[str, Any], service: dict[str, Any]) -> dict[str, Any]:
    namespaced = _rewrite_refs(copy.deepcopy(spec), f"{service['id']}_")
    namespaced["servers"] = [
        {
            "url": f"{DOCS_PUBLIC_URL}/try/{service['id']}",
            "description": service["name"],
        }
    ]
    components = namespaced.get("components") or {}
    schemas = components.get("schemas") or {}
    if schemas:
        components["schemas"] = {f"{service['id']}_{name}": value for name, value in schemas.items()}
        namespaced["components"] = components

    for path, item in (namespaced.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        item["servers"] = namespaced["servers"]
        for method, op in item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not isinstance(op, dict):
                continue
            tags = op.get("tags") or ["API"]
            op["tags"] = [f"{service['name']} · {tag}" for tag in tags]
            op_id = op.get("operationId") or f"{method}_{path}"
            op["operationId"] = f"{service['id']}_{op_id}"
    return namespaced


async def _fetch_spec(service: dict[str, Any]) -> dict[str, Any]:
    url = f"{service['origin']}/openapi.json"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{service['name']} OpenAPI is unavailable at {url}: {exc}",
        ) from exc


async def _probe(origin: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{origin}/health")
            body = {}
            try:
                body = response.json()
            except Exception:
                body = {"raw": response.text[:120]}
            return {"ok": response.status_code < 400, "status_code": response.status_code, "body": body}
    except Exception as exc:
        return {"ok": False, "status_code": 0, "error": str(exc)}


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": "hekma-platform-docs"}


@app.get("/services", include_in_schema=False)
async def services():
    rows = []
    for service in EXTRACTED:
        probe = await _probe(service["origin"])
        spec = None
        api_count = None
        if probe["ok"]:
            try:
                spec = await _fetch_spec(service)
                api_count = _count_operations(spec)
            except HTTPException:
                api_count = None
        rows.append(
            {
                **service,
                "live": probe["ok"],
                "api_count": api_count,
                "docs": f"/docs?urls.primaryName={service['code']} · {service['name']}",
                "direct_docs": f"{service['origin']}/docs",
            }
        )
    return {"extracted": rows, "not_extracted": NOT_EXTRACTED}


@app.get("/openapi/{service_id}.json", include_in_schema=False)
async def service_openapi(service_id: str):
    service = _by_id(service_id)
    return _namespace_spec(await _fetch_spec(service), service)


@app.get("/openapi.json", include_in_schema=False)
async def merged_openapi():
    merged: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Hekma Platform APIs",
            "version": "1.0.0",
            "description": (
                "Extracted microservices only. Use the **definition dropdown** "
                "to switch Patient Health, Scanner, or AI Usage. "
                "Identity, CTMS, Trial Matching, and PHI Shield are still on the old apps."
            ),
        },
        "tags": [],
        "paths": {},
        "components": {"schemas": {}, "securitySchemes": {}},
    }
    seen_tags: list[str] = []
    errors: list[str] = []
    for service in EXTRACTED:
        try:
            spec = _namespace_spec(await _fetch_spec(service), service)
        except HTTPException as exc:
            errors.append(str(exc.detail))
            continue
        for path, item in (spec.get("paths") or {}).items():
            if path in SKIP_MERGE_PATHS:
                continue
            merged["paths"][path] = item
            if isinstance(item, dict):
                for op in item.values():
                    if isinstance(op, dict):
                        for tag in op.get("tags") or []:
                            if tag not in seen_tags:
                                seen_tags.append(tag)
        components = spec.get("components") or {}
        merged["components"]["schemas"].update(components.get("schemas") or {})
        merged["components"]["securitySchemes"].update(components.get("securitySchemes") or {})
    merged["tags"] = [{"name": name} for name in seen_tags]
    if errors:
        merged["info"]["description"] += "\n\nUnavailable: " + "; ".join(errors)
    return merged


@app.api_route(
    "/try/{service_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    include_in_schema=False,
)
async def try_proxy(service_id: str, path: str, request: Request):
    service = _by_id(service_id)
    target = f"{service['origin']}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    excluded = {"host", "content-length", "connection", "keep-alive", "transfer-encoding"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in excluded}
    body = await request.body()
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
        forwarded = await client.request(request.method, target, headers=headers, content=body)
    hop = {"content-encoding", "transfer-encoding", "connection"}
    return Response(
        content=forwarded.content,
        status_code=forwarded.status_code,
        headers={k: v for k, v in forwarded.headers.items() if k.lower() not in hop},
    )


def _swagger_html() -> str:
    urls = [
        {"url": "/openapi.json", "name": "All extracted services"},
        *[
            {"url": f"/openapi/{item['id']}.json", "name": f"{item['code']} · {item['name']}"}
            for item in EXTRACTED
        ],
    ]
    import json

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Hekma Platform APIs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css"/>
  <style>
    :root {{
      --ink: #10232b;
      --muted: #5b6b72;
      --line: #d7e0e4;
      --bg: #f4f7f6;
      --card: #fff;
      --teal: #0f6b64;
      --live: #1b7f4a;
      --wait: #8a6d1b;
    }}
    html, body {{ margin: 0; background: var(--bg); color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
    .bar {{ background: var(--ink); color: #e8f2f1; padding: 18px 28px;
      display: flex; justify-content: space-between; align-items: baseline; gap: 16px; }}
    .bar h1 {{ margin: 0; font-size: 18px; font-weight: 620; letter-spacing: .01em; }}
    .bar a {{ color: #9fe1d8; text-decoration: none; font-size: 13px; }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 22px 22px 8px; }}
    .lede {{ color: var(--muted); font-size: 14px; margin: 0 0 16px; max-width: 72ch; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
    .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; }}
    .card h2 {{ margin: 0 0 6px; font-size: 15px; }}
    .card p {{ margin: 0; color: var(--muted); font-size: 13px; line-height: 1.45; }}
    .meta {{ margin-top: 10px; font-size: 12px; color: var(--ink); display: flex; gap: 10px; flex-wrap: wrap; }}
    .pill {{ border-radius: 999px; padding: 2px 8px; font-weight: 600; }}
    .live {{ background: #e5f6ec; color: var(--live); }}
    .down {{ background: #f8ead0; color: var(--wait); }}
    .later .card {{ background: #f7f5ef; }}
    h3 {{ margin: 22px 0 10px; font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
    .swagger {{ border-top: 1px solid var(--line); margin-top: 18px; background: #fff; }}
    .swagger-ui .topbar {{ display: none; }}
    .swagger-ui .info {{ margin: 18px 0 10px; }}
  </style>
</head>
<body>
  <div class="bar">
    <h1>Hekma Platform · APIs by service</h1>
    <a href="/">Catalog JSON also at /services</a>
  </div>
  <div class="wrap">
    <p class="lede">
      Extracted services are live below. Use the Swagger <strong>definition</strong> dropdown
      to switch service, then <strong>Authorize</strong> with a JWT (Patient Health / Scanner)
      or <code>X-API-Key</code> (AI Usage). Identity, CTMS, Trial Matching, and PHI Shield
      stay on the old apps until they move here.
    </p>
    <h3>Extracted</h3>
    <div class="grid" id="extracted"></div>
    <h3>Still on the old apps</h3>
    <div class="grid later" id="later"></div>
  </div>
  <div class="swagger"><div id="swagger-ui"></div></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-standalone-preset.js"></script>
  <script>
    const URLS = {json.dumps(urls)};
    const LATER = {json.dumps(NOT_EXTRACTED)};
    function card(s) {{
      const pill = s.live
        ? `<span class="pill live">${{s.api_count ?? "—"}} APIs · :${{s.port}}</span>`
        : `<span class="pill down">not running · :${{s.port}}</span>`;
      return `<article class="card"><h2>${{s.code}} · ${{s.name}}</h2><p>${{s.summary}}</p><div class="meta">${{pill}}</div></article>`;
    }}
    function laterCard(s) {{
      return `<article class="card"><h2>${{s.code}} · ${{s.name}}</h2><p>${{s.summary}} <em>${{s.host}}</em></p><div class="meta">${{(s.routes || []).join(" · ")}}</div></article>`;
    }}
    fetch("/services").then(r => r.json()).then(data => {{
      document.getElementById("extracted").innerHTML = data.extracted.map(card).join("");
      document.getElementById("later").innerHTML = data.not_extracted.map(laterCard).join("");
    }}).catch(() => {{
      document.getElementById("later").innerHTML = LATER.map(laterCard).join("");
    }});
    window.ui = SwaggerUIBundle({{
      url: "/openapi.json",
      urls: URLS,
      "urls.primaryName": "All extracted services",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
      layout: "StandaloneLayout",
      deepLinking: true,
      persistAuthorization: true,
      displayRequestDuration: true,
      tryItOutEnabled: true,
    }});
  </script>
</body>
</html>
"""


@app.get("/", include_in_schema=False)
@app.get("/docs", include_in_schema=False)
def docs_page():
    return HTMLResponse(_swagger_html())


@app.get("/redoc", include_in_schema=False)
def redoc_page():
    return HTMLResponse(
        """<!DOCTYPE html>
<html><head><title>Hekma Platform APIs</title>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
<style>body{margin:0}redoc{display:block}</style>
</head><body>
<redoc spec-url="/openapi.json"></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body></html>"""
    )

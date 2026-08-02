"""FastAPI application - REST API for the incident responder."""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.agent.graph import IncidentAgent
from src.collectors.k8s_logs import K8sLogCollector
from src.db.database import Database
from src.models.schemas import (
    AlertManagerPayload,
    IncidentResponse,
    IncidentStatus,
    PrometheusAlert,
    RootCauseAnalysis,
    Severity,
)
from src.notifiers.slack import SlackNotifier

load_dotenv()
logger = structlog.get_logger()

# Global instances
db: Database | None = None
agent: IncidentAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    global db, agent

    # Initialize database
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./incidents.db")
    db = Database(database_url)
    await db.init()

    # Initialize agent
    google_key = os.getenv("GOOGLE_API_KEY", "")
    model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")

    log_collector = K8sLogCollector(live_mode=bool(os.getenv("KUBECONFIG")))
    slack_notifier = SlackNotifier(slack_url) if slack_url else None

    agent = IncidentAgent(
        google_api_key=google_key,
        model=model,
        log_collector=log_collector,
        slack_notifier=slack_notifier,
    )

    logger.info("app.started", model=model, slack_enabled=bool(slack_url))
    yield
    logger.info("app.shutdown")


app = FastAPI(
    title="K8s Incident Responder",
    description="AI-powered Kubernetes incident analysis using LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/v1/webhook/alertmanager", response_model=dict)
async def receive_alertmanager_webhook(payload: AlertManagerPayload):
    """Receive AlertManager webhook and trigger analysis.

    This endpoint is compatible with Prometheus AlertManager webhook config.
    """
    if not agent or not db:
        raise HTTPException(status_code=503, detail="Service not ready")

    alerts = payload.to_prometheus_alerts()
    incident_ids = []

    for alert in alerts:
        if alert.status.value == "resolved":
            logger.info("webhook.alert_resolved", alert=alert.alert_name)
            continue

        incident = await agent.analyze_incident(alert)
        await db.save_incident(incident)
        incident_ids.append(incident.id)
        logger.info("webhook.incident_created", incident_id=incident.id)

    return {
        "status": "accepted",
        "incidents_created": len(incident_ids),
        "incident_ids": incident_ids,
    }


@app.post("/api/v1/incidents/analyze", response_model=IncidentResponse)
async def analyze_alert(alert: PrometheusAlert):
    """Manually submit an alert for analysis.

    Use this endpoint to test with individual alerts.
    """
    if not agent or not db:
        raise HTTPException(status_code=503, detail="Service not ready")

    incident = await agent.analyze_incident(alert)
    await db.save_incident(incident)

    return IncidentResponse(
        id=incident.id,
        status=incident.status,
        alert_name=incident.alert.alert_name,
        severity=incident.analysis.severity if incident.analysis else Severity.WARNING,
        namespace=incident.alert.namespace,
        root_cause=incident.analysis.root_cause if incident.analysis else None,
        confidence=incident.analysis.confidence if incident.analysis else None,
        remediation_steps=incident.analysis.remediation_steps if incident.analysis else [],
        created_at=incident.created_at,
    )


@app.get("/api/v1/incidents", response_model=list[IncidentResponse])
async def list_incidents(limit: int = 50):
    """List all incidents."""
    if not db:
        raise HTTPException(status_code=503, detail="Service not ready")

    records = await db.get_all_incidents(limit=limit)
    results = []
    for record in records:
        analysis = json.loads(record.analysis_data) if record.analysis_data else None
        alert_data = json.loads(record.alert_data) if record.alert_data else {}

        results.append(
            IncidentResponse(
                id=record.id,
                status=IncidentStatus(record.status),
                alert_name=alert_data.get("alert_name", "Unknown"),
                severity=Severity(analysis.get("severity", "warning")) if analysis else Severity.WARNING,
                namespace=alert_data.get("namespace", "default"),
                root_cause=analysis.get("root_cause") if analysis else None,
                confidence=analysis.get("confidence") if analysis else None,
                remediation_steps=analysis.get("remediation_steps", []) if analysis else [],
                created_at=record.created_at,
            )
        )
    return results


@app.get("/api/v1/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str):
    """Get a specific incident by ID."""
    if not db:
        raise HTTPException(status_code=503, detail="Service not ready")

    record = await db.get_incident(incident_id)
    if not record:
        raise HTTPException(status_code=404, detail="Incident not found")

    analysis = json.loads(record.analysis_data) if record.analysis_data else None
    alert_data = json.loads(record.alert_data) if record.alert_data else {}

    return IncidentResponse(
        id=record.id,
        status=IncidentStatus(record.status),
        alert_name=alert_data.get("alert_name", "Unknown"),
        severity=Severity(analysis.get("severity", "warning")) if analysis else Severity.WARNING,
        namespace=alert_data.get("namespace", "default"),
        root_cause=analysis.get("root_cause") if analysis else None,
        confidence=analysis.get("confidence") if analysis else None,
        remediation_steps=analysis.get("remediation_steps", []) if analysis else [],
        created_at=record.created_at,
    )

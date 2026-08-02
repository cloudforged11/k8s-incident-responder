"""Pydantic models for incidents and alerts."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertStatus(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


class IncidentStatus(str, Enum):
    OPEN = "open"
    ANALYZING = "analyzing"
    RESOLVED = "resolved"


class PrometheusAlert(BaseModel):
    """Incoming Prometheus AlertManager webhook payload (simplified)."""

    status: AlertStatus
    alert_name: str = Field(..., alias="alertName")
    severity: Severity = Severity.WARNING
    namespace: str = "default"
    pod: Optional[str] = None
    container: Optional[str] = None
    description: str = ""
    summary: str = ""
    starts_at: Optional[str] = Field(None, alias="startsAt")
    labels: dict = Field(default_factory=dict)
    annotations: dict = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class AlertManagerPayload(BaseModel):
    """Full AlertManager webhook payload."""

    version: str = "4"
    status: AlertStatus = AlertStatus.FIRING
    alerts: list[dict] = Field(default_factory=list)

    def to_prometheus_alerts(self) -> list[PrometheusAlert]:
        """Convert AlertManager payload to list of PrometheusAlert."""
        results = []
        for alert in self.alerts:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            results.append(
                PrometheusAlert(
                    status=alert.get("status", self.status),
                    alertName=labels.get("alertname", "Unknown"),
                    severity=labels.get("severity", "warning"),
                    namespace=labels.get("namespace", "default"),
                    pod=labels.get("pod"),
                    container=labels.get("container"),
                    description=annotations.get("description", ""),
                    summary=annotations.get("summary", ""),
                    startsAt=alert.get("startsAt"),
                    labels=labels,
                    annotations=annotations,
                )
            )
        return results


class PodLog(BaseModel):
    """Kubernetes pod log entry."""

    namespace: str
    pod: str
    container: str
    timestamp: Optional[str] = None
    message: str


class RootCauseAnalysis(BaseModel):
    """Output of the LangGraph reasoning agent."""

    incident_id: str
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    remediation_steps: list[str] = Field(default_factory=list)
    severity: Severity = Severity.WARNING
    affected_resources: list[str] = Field(default_factory=list)


class Incident(BaseModel):
    """Full incident record."""

    id: str
    status: IncidentStatus = IncidentStatus.OPEN
    alert: PrometheusAlert
    logs: list[PodLog] = Field(default_factory=list)
    analysis: Optional[RootCauseAnalysis] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class IncidentResponse(BaseModel):
    """API response for incident."""

    id: str
    status: IncidentStatus
    alert_name: str
    severity: Severity
    namespace: str
    root_cause: Optional[str] = None
    confidence: Optional[float] = None
    remediation_steps: list[str] = Field(default_factory=list)
    created_at: datetime

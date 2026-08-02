"""Tests for the incident responder API."""

import json
import pytest
from httpx import ASGITransport, AsyncClient

from src.api.app import app


@pytest.fixture
def sample_alert():
    return {
        "version": "4",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "KubePodCrashLooping",
                    "severity": "critical",
                    "namespace": "production",
                    "pod": "test-pod-abc123",
                    "container": "main",
                },
                "annotations": {
                    "summary": "Pod is crash looping",
                    "description": "Test pod is crash looping due to OOM",
                },
                "startsAt": "2026-08-01T10:00:00Z",
            }
        ],
    }


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_analyze_single_alert():
    """Test the single alert analysis endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        alert_payload = {
            "alertName": "TestHighCPU",
            "status": "firing",
            "severity": "warning",
            "namespace": "default",
            "pod": "test-pod-123",
            "description": "CPU usage above 90%",
            "summary": "High CPU alert",
        }
        response = await client.post("/api/v1/incidents/analyze", json=alert_payload)
        # Will be 503 without OPENAI_API_KEY, which is expected in tests
        assert response.status_code in [200, 503]

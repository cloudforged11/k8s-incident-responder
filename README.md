# 🤖 K8s Incident Responder

**AI-powered Kubernetes incident analysis using LangGraph for automated root cause detection and remediation suggestions.**

🔗 **Live Demo:** [https://k8s-incident-responder.onrender.com/docs](https://k8s-incident-responder.onrender.com/docs)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple.svg)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](https://docker.com)
[![Helm](https://img.shields.io/badge/Helm-3.x-navy.svg)](https://helm.sh)

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  Prometheus          │────▶│  FastAPI              │────▶│  LangGraph Agent    │
│  AlertManager        │     │  Ingestion API        │     │  (Multi-step        │
│  (webhook)           │     │                       │     │   reasoning)        │
└─────────────────────┘     └──────────────────────┘     └──────────┬──────────┘
                                                                     │
┌─────────────────────┐     ┌──────────────────────┐                │
│  Kubernetes API      │────▶│  Log Collector        │───────────────┘
│  (pod logs)          │     │  (live + simulated)   │                │
└─────────────────────┘     └──────────────────────┘                ▼
                                                          ┌─────────────────────┐
                                                          │  Output:            │
                                                          │  • Root Cause       │
                                                          │  • Remediation      │
                                                          │  • Slack Alert      │
                                                          │  • SQLite Store     │
                                                          └─────────────────────┘
```

### LangGraph Agent Pipeline

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌────────┐
│  Triage  │───▶│  Gather      │───▶│  Analyze      │───▶│  Suggest     │───▶│ Notify │
│          │    │  Context     │    │  Root Cause   │    │  Remediation │    │        │
└──────────┘    └──────────────┘    └───────────────┘    └──────────────┘    └────────┘
```

Each node in the graph performs a specialized task:
1. **Triage** - Classifies severity and identifies the affected component
2. **Gather Context** - Fetches Kubernetes pod logs (live or simulated)
3. **Analyze Root Cause** - LLM reasons over alerts + logs to determine root cause
4. **Suggest Remediation** - Generates actionable kubectl commands and fixes
5. **Notify** - Sends formatted Slack notification with full analysis

---

## Features

- 🔍 **Automated Root Cause Analysis** - LLM-powered reasoning over alerts and logs
- 📊 **Prometheus AlertManager Integration** - Drop-in webhook receiver
- 🐳 **Kubernetes Native** - Reads pod logs, RBAC-aware, Helm deployable
- 💬 **Slack Notifications** - Rich formatted incident reports
- 🧪 **Simulation Mode** - Works without a live cluster for demos
- 💾 **Incident History** - SQLite persistence with full audit trail
- 🏗️ **Production Ready** - Docker, Helm chart, health checks, structured logging

---

## Quick Start

### Prerequisites
- Python 3.11+
- Groq API key (FREE - [get one here](https://console.groq.com/keys))

### 1. Clone & Setup

```bash
git clone https://github.com/YOUR_USERNAME/k8s-incident-responder.git
cd k8s-incident-responder

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env → set GROQ_API_KEY=your-key-from-console.groq.com
```

### 3. Run

```bash
python main.py
```

Server starts at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

> 💡 **Don't want to set up locally?** Try the live demo: [https://k8s-incident-responder.onrender.com/docs](https://k8s-incident-responder.onrender.com/docs)

### 4. Test with a sample alert

```bash
curl -X POST http://localhost:8000/api/v1/webhook/alertmanager \
  -H "Content-Type: application/json" \
  -d @fixtures/sample_alert_crashloop.json
```

Or use the direct analysis endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/incidents/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "alertName": "KubePodCrashLooping",
    "status": "firing",
    "severity": "critical",
    "namespace": "production",
    "pod": "payment-service-7d4b8c6f9-x2k4m",
    "description": "Pod is crash looping with 5 restarts in 10 minutes",
    "summary": "CrashLoopBackOff detected"
  }'
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/webhook/alertmanager` | AlertManager webhook receiver |
| `POST` | `/api/v1/incidents/analyze` | Analyze a single alert |
| `GET` | `/api/v1/incidents` | List all incidents |
| `GET` | `/api/v1/incidents/{id}` | Get incident details |

---

## Deploy to Kubernetes

### Using Helm

```bash
# Build the Docker image
docker build -t k8s-incident-responder:latest .

# Install with Helm
helm install incident-responder ./helm/k8s-incident-responder \
  --set env.GROQ_API_KEY=your-key-here \
  --set env.SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Configure AlertManager

Add to your AlertManager config:

```yaml
receivers:
  - name: 'incident-responder'
    webhook_configs:
      - url: 'http://incident-responder:8000/api/v1/webhook/alertmanager'
        send_resolved: true
```

---

## Docker Compose

```bash
# Copy and configure .env
cp .env.example .env

# Run
docker compose up --build
```

---

## Project Structure

```
k8s-incident-responder/
├── src/
│   ├── agent/
│   │   └── graph.py          # LangGraph agent with 5-node pipeline
│   ├── api/
│   │   └── app.py            # FastAPI REST API
│   ├── collectors/
│   │   └── k8s_logs.py       # Kubernetes log collector (live + simulated)
│   ├── db/
│   │   └── database.py       # SQLAlchemy async + SQLite
│   ├── models/
│   │   └── schemas.py        # Pydantic models
│   └── notifiers/
│       └── slack.py          # Slack webhook integration
├── helm/                      # Helm chart for K8s deployment
├── fixtures/                  # Sample alerts for testing
├── tests/                     # Pytest test suite
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── main.py
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI/Reasoning | LangGraph, LangChain, Groq (Llama 3.3 70B - free tier) |
| API | FastAPI, Pydantic v2 |
| Database | SQLAlchemy (async), SQLite |
| Container | Docker, Helm 3 |
| Orchestration | Kubernetes (RBAC, pod log access) |
| Monitoring | Prometheus AlertManager (webhook) |
| Notifications | Slack Incoming Webhooks |
| Logging | structlog |

---

## Sample Output

```json
{
  "id": "INC-A3F2B1C8",
  "status": "resolved",
  "alert_name": "KubePodCrashLooping",
  "severity": "critical",
  "namespace": "production",
  "root_cause": "Database connection pool exhaustion causing cascading failures. The payment-service pod exceeded its HikariCP connection pool limit (max 10), leading to request timeouts and eventual OOMKill when pending requests accumulated in memory.",
  "confidence": 0.87,
  "remediation_steps": [
    "Increase connection pool size: kubectl set env deployment/payment-service HIKARI_MAX_POOL_SIZE=25 -n production",
    "Increase memory limit: kubectl patch deployment payment-service -n production -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"payment-api\",\"resources\":{\"limits\":{\"memory\":\"1Gi\"}}}]}}}}'",
    "Add connection timeout configuration: Set HIKARI_CONNECTION_TIMEOUT=60000 environment variable",
    "Scale the database: Consider read replicas or PgBouncer for connection pooling at the database level",
    "Add horizontal pod autoscaler: kubectl autoscale deployment payment-service --min=2 --max=5 --cpu-percent=70 -n production"
  ]
}
```

---

## License

MIT

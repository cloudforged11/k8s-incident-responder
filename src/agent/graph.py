"""LangGraph-based incident reasoning agent.

Graph Structure:
    ┌─────────────┐
    │   Triage     │  ← Classify severity & affected component
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │  Gather      │  ← Collect K8s logs & related context
    │  Context     │
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │  Analyze     │  ← LLM reasons about root cause
    │  Root Cause  │
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │  Suggest     │  ← Generate remediation steps
    │  Remediation │
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │  Notify      │  ← Send Slack/webhook notification
    └─────────────┘
"""

import uuid
from datetime import datetime
from typing import Annotated, TypedDict

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.collectors.k8s_logs import K8sLogCollector
from src.models.schemas import (
    Incident,
    IncidentStatus,
    PodLog,
    PrometheusAlert,
    RootCauseAnalysis,
    Severity,
)
from src.notifiers.slack import SlackNotifier

logger = structlog.get_logger()


class AgentState(TypedDict):
    """State that flows through the LangGraph agent."""

    incident_id: str
    alert: dict
    logs: list[dict]
    severity: str
    affected_component: str
    context_summary: str
    root_cause: str
    confidence: float
    evidence: list[str]
    remediation_steps: list[str]
    notification_sent: bool
    messages: Annotated[list, add_messages]


class IncidentAgent:
    """LangGraph-powered incident analysis agent."""

    def __init__(
        self,
        groq_api_key: str,
        model: str = "llama-3.3-70b-versatile",
        log_collector: K8sLogCollector | None = None,
        slack_notifier: SlackNotifier | None = None,
    ):
        self.llm = ChatGroq(
            model=model,
            api_key=groq_api_key,
            temperature=0.1,
        )
        self.log_collector = log_collector or K8sLogCollector()
        self.slack_notifier = slack_notifier
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("triage", self._triage_node)
        workflow.add_node("gather_context", self._gather_context_node)
        workflow.add_node("analyze_root_cause", self._analyze_root_cause_node)
        workflow.add_node("suggest_remediation", self._suggest_remediation_node)
        workflow.add_node("notify", self._notify_node)

        # Define edges
        workflow.set_entry_point("triage")
        workflow.add_edge("triage", "gather_context")
        workflow.add_edge("gather_context", "analyze_root_cause")
        workflow.add_edge("analyze_root_cause", "suggest_remediation")
        workflow.add_edge("suggest_remediation", "notify")
        workflow.add_edge("notify", END)

        return workflow.compile()

    async def analyze_incident(self, alert: PrometheusAlert) -> Incident:
        """Run the full incident analysis pipeline."""
        incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        logger.info("agent.starting_analysis", incident_id=incident_id, alert=alert.alert_name)

        initial_state: AgentState = {
            "incident_id": incident_id,
            "alert": alert.model_dump(),
            "logs": [],
            "severity": alert.severity.value,
            "affected_component": "",
            "context_summary": "",
            "root_cause": "",
            "confidence": 0.0,
            "evidence": [],
            "remediation_steps": [],
            "notification_sent": False,
            "messages": [],
        }

        # Run the graph
        final_state = await self.graph.ainvoke(initial_state)

        # Build incident from final state
        incident = Incident(
            id=incident_id,
            status=IncidentStatus.RESOLVED,
            alert=alert,
            logs=[PodLog(**log) for log in final_state["logs"]],
            analysis=RootCauseAnalysis(
                incident_id=incident_id,
                root_cause=final_state["root_cause"],
                confidence=final_state["confidence"],
                evidence=final_state["evidence"],
                remediation_steps=final_state["remediation_steps"],
                severity=Severity(final_state["severity"]),
                affected_resources=[final_state["affected_component"]],
            ),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        logger.info(
            "agent.analysis_complete",
            incident_id=incident_id,
            root_cause=final_state["root_cause"][:100],
        )
        return incident

    async def _triage_node(self, state: AgentState) -> dict:
        """Triage: classify severity and identify affected component."""
        alert = state["alert"]

        prompt = f"""You are a Kubernetes SRE triaging an incident.

Alert: {alert.get('alert_name', 'Unknown')}
Description: {alert.get('description', 'N/A')}
Summary: {alert.get('summary', 'N/A')}
Namespace: {alert.get('namespace', 'default')}
Pod: {alert.get('pod', 'unknown')}
Labels: {alert.get('labels', {})}

Determine:
1. The severity (critical/warning/info)
2. The affected component (e.g., "payment-service pod", "database connection", "memory")

Respond in this exact format:
SEVERITY: <critical|warning|info>
COMPONENT: <affected component description>"""

        response = await self.llm.ainvoke([
            SystemMessage(content="You are a Kubernetes SRE expert. Be concise."),
            HumanMessage(content=prompt),
        ])

        # Parse response
        content = response.content
        severity = state["severity"]
        component = "unknown"

        for line in content.split("\n"):
            if line.startswith("SEVERITY:"):
                sev = line.split(":", 1)[1].strip().lower()
                if sev in ("critical", "warning", "info"):
                    severity = sev
            elif line.startswith("COMPONENT:"):
                component = line.split(":", 1)[1].strip()

        logger.info("agent.triage_complete", severity=severity, component=component)
        return {
            "severity": severity,
            "affected_component": component,
            "messages": [HumanMessage(content=f"Triaged: {severity} - {component}")],
        }

    async def _gather_context_node(self, state: AgentState) -> dict:
        """Gather K8s logs and additional context."""
        alert = state["alert"]
        namespace = alert.get("namespace", "default")
        pod = alert.get("pod")
        container = alert.get("container")

        logs = await self.log_collector.get_pod_logs(
            namespace=namespace,
            pod=pod,
            container=container,
        )

        # Build context summary
        log_messages = [f"[{log.timestamp}] {log.message}" for log in logs]
        context_summary = f"""
Namespace: {namespace}
Pod: {pod or 'unknown'}
Container: {container or 'main'}
Log entries ({len(logs)} lines):
{chr(10).join(log_messages[-20:])}
"""

        logger.info("agent.context_gathered", namespace=namespace, log_count=len(logs))
        return {
            "logs": [log.model_dump() for log in logs],
            "context_summary": context_summary,
            "messages": [HumanMessage(content=f"Gathered {len(logs)} log entries")],
        }

    async def _analyze_root_cause_node(self, state: AgentState) -> dict:
        """Use LLM to analyze root cause from alert + logs."""
        alert = state["alert"]
        context = state["context_summary"]

        prompt = f"""You are a senior Kubernetes SRE performing root cause analysis.

ALERT: {alert.get('alert_name', 'Unknown')}
SEVERITY: {state['severity']}
DESCRIPTION: {alert.get('description', 'N/A')}
AFFECTED COMPONENT: {state['affected_component']}

KUBERNETES LOGS & CONTEXT:
{context}

Analyze the root cause. Provide:
1. ROOT_CAUSE: A clear, concise explanation of what went wrong
2. CONFIDENCE: A number between 0.0 and 1.0 indicating your confidence
3. EVIDENCE: List 2-4 specific log entries or indicators that support your conclusion

Format your response exactly as:
ROOT_CAUSE: <explanation>
CONFIDENCE: <0.0-1.0>
EVIDENCE:
- <evidence 1>
- <evidence 2>
- <evidence 3>"""

        response = await self.llm.ainvoke([
            SystemMessage(
                content="You are a Kubernetes SRE expert specializing in incident analysis. "
                "Be specific, reference actual log entries, and provide actionable insights."
            ),
            HumanMessage(content=prompt),
        ])

        content = response.content
        root_cause = "Unable to determine root cause"
        confidence = 0.5
        evidence = []

        for line in content.split("\n"):
            if line.startswith("ROOT_CAUSE:"):
                root_cause = line.split(":", 1)[1].strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    pass
            elif line.startswith("- "):
                evidence.append(line[2:].strip())

        logger.info("agent.root_cause_analyzed", confidence=confidence)
        return {
            "root_cause": root_cause,
            "confidence": confidence,
            "evidence": evidence,
            "messages": [HumanMessage(content=f"Root cause: {root_cause[:80]}...")],
        }

    async def _suggest_remediation_node(self, state: AgentState) -> dict:
        """Generate specific remediation steps."""
        prompt = f"""You are a Kubernetes SRE suggesting remediation steps.

INCIDENT: {state['alert'].get('alert_name', 'Unknown')}
ROOT CAUSE: {state['root_cause']}
AFFECTED: {state['affected_component']}
SEVERITY: {state['severity']}

Provide 3-5 specific, actionable remediation steps. Include actual kubectl commands or configuration changes where applicable.

Format as:
STEPS:
1. <step with command if applicable>
2. <step>
3. <step>"""

        response = await self.llm.ainvoke([
            SystemMessage(
                content="You are a Kubernetes SRE. Provide specific, copy-pasteable commands. "
                "Include kubectl commands, Helm values changes, or YAML patches as needed."
            ),
            HumanMessage(content=prompt),
        ])

        content = response.content
        steps = []
        in_steps = False
        for line in content.split("\n"):
            if line.strip().startswith("STEPS:"):
                in_steps = True
                continue
            if in_steps and line.strip():
                # Remove leading number and dot
                step = line.strip()
                if step[0].isdigit() and "." in step[:3]:
                    step = step.split(".", 1)[1].strip()
                steps.append(step)

        if not steps:
            # Fallback: just split the response into lines
            steps = [line.strip() for line in content.split("\n") if line.strip() and len(line) > 10]

        logger.info("agent.remediation_suggested", step_count=len(steps))
        return {
            "remediation_steps": steps[:5],
            "messages": [HumanMessage(content=f"Suggested {len(steps)} remediation steps")],
        }

    async def _notify_node(self, state: AgentState) -> dict:
        """Send notification via Slack webhook."""
        if self.slack_notifier:
            try:
                await self.slack_notifier.send_incident_notification(
                    incident_id=state["incident_id"],
                    alert_name=state["alert"].get("alert_name", "Unknown"),
                    severity=state["severity"],
                    root_cause=state["root_cause"],
                    remediation_steps=state["remediation_steps"],
                )
                logger.info("agent.notification_sent", incident_id=state["incident_id"])
                return {"notification_sent": True}
            except Exception as e:
                logger.error("agent.notification_failed", error=str(e))

        return {"notification_sent": False}

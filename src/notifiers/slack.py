"""Slack webhook notifier."""

import httpx
import structlog

logger = structlog.get_logger()


class SlackNotifier:
    """Sends incident notifications to Slack via webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_incident_notification(
        self,
        incident_id: str,
        alert_name: str,
        severity: str,
        root_cause: str,
        remediation_steps: list[str],
    ) -> bool:
        """Send a formatted incident notification to Slack."""
        severity_emoji = {
            "critical": "🔴",
            "warning": "🟡",
            "info": "🔵",
        }

        emoji = severity_emoji.get(severity, "⚪")
        steps_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(remediation_steps))

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} Incident: {alert_name}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*ID:*\n{incident_id}"},
                        {"type": "mrkdwn", "text": f"*Severity:*\n{severity.upper()}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Root Cause:*\n{root_cause}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Remediation Steps:*\n{steps_text}",
                    },
                },
                {"type": "divider"},
            ],
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("slack.notification_sent", incident_id=incident_id)
                return True
        except Exception as e:
            logger.error("slack.notification_failed", error=str(e), incident_id=incident_id)
            return False

"""Kubernetes log collector - fetches pod logs for context."""

import structlog
from typing import Optional

from src.models.schemas import PodLog

logger = structlog.get_logger()


class K8sLogCollector:
    """Collects logs from Kubernetes pods.

    In simulation mode, returns mock logs from fixtures.
    In live mode, uses the kubernetes client.
    """

    def __init__(self, live_mode: bool = False):
        self.live_mode = live_mode
        self._k8s_client = None

        if self.live_mode:
            try:
                from kubernetes import client, config

                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()
                self._k8s_client = client.CoreV1Api()
                logger.info("k8s_collector.live_mode_enabled")
            except Exception as e:
                logger.warning("k8s_collector.live_mode_failed", error=str(e))
                self.live_mode = False

    async def get_pod_logs(
        self,
        namespace: str,
        pod: Optional[str] = None,
        container: Optional[str] = None,
        tail_lines: int = 50,
    ) -> list[PodLog]:
        """Fetch pod logs. Falls back to simulation if live mode unavailable."""
        if self.live_mode and self._k8s_client and pod:
            return await self._fetch_live_logs(namespace, pod, container, tail_lines)
        return self._get_simulated_logs(namespace, pod, container)

    async def _fetch_live_logs(
        self,
        namespace: str,
        pod: str,
        container: Optional[str],
        tail_lines: int,
    ) -> list[PodLog]:
        """Fetch real logs from Kubernetes API."""
        try:
            kwargs = {
                "name": pod,
                "namespace": namespace,
                "tail_lines": tail_lines,
                "timestamps": True,
            }
            if container:
                kwargs["container"] = container

            log_text = self._k8s_client.read_namespaced_pod_log(**kwargs)
            logs = []
            for line in log_text.strip().split("\n"):
                if " " in line:
                    ts, msg = line.split(" ", 1)
                else:
                    ts, msg = None, line
                logs.append(
                    PodLog(
                        namespace=namespace,
                        pod=pod,
                        container=container or "main",
                        timestamp=ts,
                        message=msg,
                    )
                )
            logger.info("k8s_collector.fetched_live_logs", pod=pod, count=len(logs))
            return logs
        except Exception as e:
            logger.error("k8s_collector.live_log_error", error=str(e))
            return self._get_simulated_logs(namespace, pod, container)

    def _get_simulated_logs(
        self,
        namespace: str,
        pod: Optional[str],
        container: Optional[str],
    ) -> list[PodLog]:
        """Return realistic simulated logs for demo/testing."""
        pod_name = pod or "app-deployment-7d4b8c6f9-x2k4m"
        container_name = container or "main"

        # Simulate different failure scenarios based on pod/namespace
        simulated_logs = [
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:00:01Z",
                message="INFO: Application starting on port 8080",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:00:05Z",
                message="INFO: Connected to database at postgres-svc:5432",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:05:12Z",
                message="WARN: Connection pool exhausted, waiting for available connection",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:05:15Z",
                message="ERROR: Failed to acquire database connection within 30s timeout",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:05:15Z",
                message="ERROR: java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:05:16Z",
                message="ERROR: GET /api/v1/users returned 503 Service Unavailable",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:05:20Z",
                message="WARN: Health check /healthz failing - downstream dependency unhealthy",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:05:25Z",
                message="ERROR: OOMKilled: container exceeded memory limit of 512Mi (current: 498Mi)",
            ),
            PodLog(
                namespace=namespace,
                pod=pod_name,
                container=container_name,
                timestamp="2026-08-01T10:05:30Z",
                message="FATAL: Pod restarting due to liveness probe failure (3/3 consecutive failures)",
            ),
        ]
        logger.info("k8s_collector.simulated_logs", pod=pod_name, count=len(simulated_logs))
        return simulated_logs

import logging
import os
from k3s_client.exceptions import K3sClientError
from k3s_client.agent import SwarmAgentClient

logger = logging.getLogger(__name__)


def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except K3sClientError:
            raise
        except Exception as e:
            logger.exception("Error in %s", func.__name__)
            raise K3sClientError(str(e))

    return wrapper


class PodManager:
    """Manage pods by delegating operations to swarm-agent."""

    @handle_errors
    def __init__(
        self,
        kubeconfig_path=None,
        default_namespace=None,
        execution_mode="swarm-agent",
        swarm_agent_url=None,
        swarm_agent_token=None,
    ):
        self.execution_mode = str(execution_mode or "swarm-agent").strip().lower()
        if self.execution_mode != "swarm-agent":
            raise ValueError("execution_mode must be 'swarm-agent'")

        # Legacy init param accepted for backward compatibility.
        _ = kubeconfig_path
        base_url = swarm_agent_url or os.getenv("SWARM_AGENT_URL")
        token = swarm_agent_token or os.getenv("SWARM_AGENT_TOKEN")
        self.agent = SwarmAgentClient(base_url=base_url, token=token)

        self.default_namespace = default_namespace or "default"
        logger.info(
            "Initialized PodManager with namespace=%s mode=%s",
            self.default_namespace,
            self.execution_mode,
        )

    def _agent_execute(self, action, params):
        return self.agent.execute(action=action, params=params)

    @handle_errors
    def list_pods(self, namespace=None, label_selector=None):
        namespace = namespace or self.default_namespace
        return self._agent_execute(
            "pods.list_pods",
            {"namespace": namespace, "label_selector": label_selector},
        )

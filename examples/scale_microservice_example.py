from k3s_client.api.applications import ApplicationManager

DEPLOYMENT_NAME = "my-app"
REPLICAS = 3
NAMESPACE = "default"
SWARM_AGENT_URL = "http://swarm-agent.default.svc.cluster.local:8080"


def scale_microservice_example(
    deployment_name: str = DEPLOYMENT_NAME,
    replicas: int = REPLICAS,
    namespace: str = NAMESPACE,
    swarm_agent_url: str | None = None,
) -> str:
    """
    Scale a microservice to an exact replica count.

    Args:
        deployment_name: Name of the Kubernetes deployment.
        replicas: Desired number of replicas.
        namespace: Kubernetes namespace.
        swarm_agent_url: Optional swarm-agent base URL.

    Returns:
        The API response from the scaling operation.
    """
    manager = ApplicationManager(swarm_agent_url=swarm_agent_url)
    result = manager.scale_to(
        msid=deployment_name,
        count=replicas,
        namespace=namespace,
    )
    print(f"✅ Scaled deployment {deployment_name} to {replicas} replicas")
    return str(result)


if __name__ == "__main__":
    scale_microservice_example(
        deployment_name=DEPLOYMENT_NAME,
        replicas=REPLICAS,
        namespace=NAMESPACE,
        swarm_agent_url=SWARM_AGENT_URL,
    )

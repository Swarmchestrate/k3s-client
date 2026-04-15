from k3s_client.api.applications import ApplicationManager

DEPLOYMENT_NAME = "my-app"
REPLICAS = 3
NAMESPACE = "default"


def scale_microservice_example(
    deployment_name: str = DEPLOYMENT_NAME,
    replicas: int = REPLICAS,
    namespace: str = NAMESPACE,
) -> str:
    """
    Scale a microservice up or down by changing replica count.

    Args:
        deployment_name: Name of the Kubernetes deployment.
        replicas: Desired number of replicas.
        namespace: Kubernetes namespace.

    Returns:
        The API response from the scaling operation.
    """
    manager = ApplicationManager()
    result = manager.scale_microservice(
        deployment_name=deployment_name, replicas=replicas, namespace=namespace
    )
    print(f"✅ Scaled deployment {deployment_name} to {replicas} replicas")
    return str(result)


if __name__ == "__main__":
    scale_microservice_example(
        deployment_name=DEPLOYMENT_NAME,
        replicas=REPLICAS,
        namespace=NAMESPACE,
    )

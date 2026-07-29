from k3s_client.api.applications import ApplicationManager

DEPLOYMENT_NAME = "my-app"
REPLICAS = 3


def scale_microservice_example(
    deployment_name: str = DEPLOYMENT_NAME,
    replicas: int = REPLICAS,
) -> str:
    """
    Scale a microservice to an exact replica count.

    Args:
        deployment_name: Name of the Kubernetes deployment.
        replicas: Desired number of replicas.

    Returns:
        The API response from the scaling operation.
    """
    manager = ApplicationManager()
    result = manager.scale_to(msid=deployment_name, count=replicas)
    print(f"✅ Scaled deployment {deployment_name} to {replicas} replicas")
    return str(result)


if __name__ == "__main__":
    scale_microservice_example(deployment_name=DEPLOYMENT_NAME, replicas=REPLICAS)

from k3s_client.api.applications import ApplicationManager

REGISTRY = "index.docker.io"
USERNAME = "user"
PASSWORD = "pass"
NAMESPACE = "default"
SECRET_NAME = "my-registry-secret"


def create_registry_secret_example(
    registry: str = REGISTRY,
    username: str = USERNAME,
    password: str = PASSWORD,
    namespace: str = NAMESPACE,
    secret_name: str = SECRET_NAME,
) -> str:
    """
    Create a registry secret for pulling private images.

    Args:
        registry: Docker registry URL (e.g., "index.docker.io", "my-registry.com")
        username: Registry username
        password: Registry password
        namespace: Kubernetes namespace
        secret_name: Name for the secret

    Returns:
        Success message from the API
    """
    manager = ApplicationManager()
    result = manager.create_registry_secret(
        name=secret_name,
        registry=registry,
        username=username,
        password=password,
        namespace=namespace,
    )
    print(f"Registry secret created: {result}")
    return result


if __name__ == "__main__":
    create_registry_secret_example(
        registry=REGISTRY,
        username=USERNAME,
        password=PASSWORD,
        email=EMAIL,
        namespace=NAMESPACE,
        secret_name=SECRET_NAME,
    )

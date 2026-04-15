from k3s_client.api.applications import ApplicationManager

REGISTRY = "index.docker.io"
USERNAME = "user"
PASSWORD = "pass"
EMAIL = "user@example.com"
NAMESPACE = "default"
SECRET_NAME = "my-registry-secret"


def create_registry_secret_example(
    registry: str = REGISTRY,
    username: str = USERNAME,
    password: str = PASSWORD,
    email: str | None = EMAIL,
    namespace: str = NAMESPACE,
    secret_name: str = SECRET_NAME,
    kubeconfig_path: str | None = None,
) -> str:
    """
    Create a registry secret for pulling private images.

    Args:
        registry: Docker registry URL (e.g., "index.docker.io", "my-registry.com")
        username: Registry username
        password: Registry password
        email: Optional email address for the registry secret
        namespace: Kubernetes namespace
        secret_name: Name for the secret
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        Success message from the API
    """
    manager = ApplicationManager(kubeconfig_path=kubeconfig_path)
    result = manager.create_registry_secret(
        name=secret_name,
        registry=registry,
        username=username,
        password=password,
        email=email,
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

from k3s_client.api.applications import ApplicationManager


def create_registry_secret_example(
    registry: str = "index.docker.io",
    username: str = "user",
    password: str = "pass",
    email: str = "user@example.com",
    namespace: str = "default",
    secret_name: str = "my-registry-secret"
) -> str:
    """
    Create a registry secret for pulling private images.

    Args:
        registry: Docker registry URL (e.g., "index.docker.io", "my-registry.com")
        username: Registry username
        password: Registry password
        email: User email
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
        email=email,
        namespace=namespace,
    )
    print(f"Registry secret created: {result}")
    return result


# Example usage (can be imported and called from another script):
# result = create_registry_secret_example(
#     registry="my-registry.com",
#     username="myuser",
#     password="mypass",
#     namespace="production"
# )

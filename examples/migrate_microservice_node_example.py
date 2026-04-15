from k3s_client.api.applications import ApplicationManager

DEPLOYMENT_NAME = "my-app"
NODE_SELECTOR = {"node-type": "high-memory"}
NAMESPACE = "default"


def migrate_microservice_node_example(
    deployment_name: str = DEPLOYMENT_NAME,
    node_selector: dict = None,
    namespace: str = NAMESPACE,
    kubeconfig_path: str | None = None,
) -> str:
    """
    Migrate a microservice to nodes matching the provided selector.

    Args:
        deployment_name: Name of the Kubernetes deployment.
        node_selector: Dictionary of node selector labels.
        namespace: Kubernetes namespace.
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        The API response from the migration operation.
    """
    if node_selector is None:
        node_selector = {"node-type": "high-memory"}

    manager = ApplicationManager(kubeconfig_path=kubeconfig_path)
    result = manager.migrate_microservice_node(
        deployment_name=deployment_name,
        node_selector=node_selector,
        namespace=namespace,
    )
    print(
        f"✅ Migrated deployment {deployment_name} to nodes matching: {node_selector}"
    )
    return str(result)


if __name__ == "__main__":
    migrate_microservice_node_example(
        deployment_name=DEPLOYMENT_NAME,
        node_selector=NODE_SELECTOR,
        namespace=NAMESPACE,
    )

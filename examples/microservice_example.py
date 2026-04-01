from k3s_client.api.applications import ApplicationManager


def scale_microservice_example(
    deployment_name: str = "my-app", replicas: int = 3, namespace: str = "default"
) -> str:
    """
    Scale a microservice up or down by changing replica count.

    Args:
        deployment_name: Name of the Kubernetes deployment
        replicas: Desired number of replicas
        namespace: Kubernetes namespace

    Returns:
        Success message from scaling operation
    """
    manager = ApplicationManager()
    result = manager.scale_microservice(
        deployment_name=deployment_name, replicas=replicas, namespace=namespace
    )
    print(f"Scaled {deployment_name} to {replicas} replicas")
    return str(result)


def update_microservice_image_example(
    deployment_name: str = "my-app",
    container_name: str = "app",
    new_image: str = "nginx:1.25",
    namespace: str = "default",
) -> str:
    """
    Update the container image of a microservice (rolling update).

    Args:
        deployment_name: Name of the Kubernetes deployment
        container_name: Name of the container in the deployment
        new_image: New container image to deploy
        namespace: Kubernetes namespace

    Returns:
        Success message from image update operation
    """
    manager = ApplicationManager()
    result = manager.update_microservice_image(
        deployment_name=deployment_name,
        container_name=container_name,
        new_image=new_image,
        namespace=namespace,
    )
    print(f"Updated {deployment_name} container {container_name} to image {new_image}")
    return str(result)


def migrate_microservice_node_example(
    deployment_name: str = "my-app",
    node_selector: dict = None,
    namespace: str = "default",
) -> str:
    """
    Migrate a microservice to run on different nodes.

    Args:
        deployment_name: Name of the Kubernetes deployment
        node_selector: Dictionary of node labels to match (e.g., {"node-type": "high-memory"})
        namespace: Kubernetes namespace

    Returns:
        Success message from migration operation
    """
    if node_selector is None:
        node_selector = {"node-type": "high-memory"}

    manager = ApplicationManager()
    result = manager.migrate_microservice_node(
        deployment_name=deployment_name,
        node_selector=node_selector,
        namespace=namespace,
    )
    print(f"Migrated {deployment_name} to nodes with selector: {node_selector}")
    return str(result)


def delete_microservice_example(
    app_label: str = "my-app", namespace: str = "default"
) -> str:
    """
    Delete a complete microservice (deployment + service).

    Args:
        app_label: Label selector for the application (e.g., "app=my-app")
        namespace: Kubernetes namespace

    Returns:
        Success message from deletion operation
    """
    manager = ApplicationManager()
    result = manager.delete_microservice(app_label=app_label, namespace=namespace)
    print(f"Deleted microservice with label {app_label}")
    return str(result)


def get_pod_node_mapping_example(
    namespace: str = "default", label_selector: str = None
) -> dict:
    """
    Get mapping of pod names to node names for monitoring.

    Args:
        namespace: Kubernetes namespace
        label_selector: Optional label selector to filter pods

    Returns:
        Dictionary mapping pod names to node names
    """
    manager = ApplicationManager()
    mapping = manager.get_pod_node_mapping(
        namespace=namespace, label_selector=label_selector
    )
    print(f"Pod-node mapping: {mapping}")
    return mapping


# Example usage:
if __name__ == "__main__":
    # Scale microservice to 5 replicas
    scale_microservice_example("my-deployment", 5)

    # Update container image
    update_microservice_image_example("my-deployment", "web", "myapp:v2.0")

    # Migrate to high-memory nodes
    migrate_microservice_node_example("my-deployment", {"node-type": "high-memory"})

    # Get pod-node mapping for monitoring
    get_pod_node_mapping_example("default", "app=my-app")

    # Delete microservice
    delete_microservice_example("app=my-app")

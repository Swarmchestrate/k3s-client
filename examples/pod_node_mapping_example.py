from k3s_client.api.applications import ApplicationManager

NAMESPACE = "default"
LABEL_SELECTOR = None


def pod_node_mapping_example(
    namespace: str = NAMESPACE, label_selector: str = LABEL_SELECTOR
) -> dict:
    """
    Retrieve a mapping of pod names to node names for a namespace.

    Args:
        namespace: Kubernetes namespace.
        label_selector: Optional label selector to filter pods.

    Returns:
        Dictionary mapping pod names to node names.
    """
    manager = ApplicationManager()
    mapping = manager.get_pod_node_mapping(
        namespace=namespace, label_selector=label_selector
    )
    print(f"✅ Pod-node mapping: {mapping}")
    return mapping


if __name__ == "__main__":
    pod_node_mapping_example(namespace=NAMESPACE, label_selector=LABEL_SELECTOR)

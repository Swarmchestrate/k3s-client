from k3s_client.api.applications import ApplicationManager

NAMESPACE = "default"
LABEL_SELECTOR = None


def pod_node_mapping_example(
    namespace: str = NAMESPACE,
    label_selector: str = LABEL_SELECTOR,
    kubeconfig_path: str | None = None,
) -> dict:
    """
    Retrieve a mapping of pod names to node names for a namespace.

    Args:
        namespace: Kubernetes namespace.
        label_selector: Optional label selector to filter pods.
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        Dictionary mapping pod names to node names.
    """
    manager = ApplicationManager(kubeconfig_path=kubeconfig_path)
    mapping = manager.get_pod_node_mapping(
        namespace=namespace, label_selector=label_selector
    )
    print(f"✅ Pod-node mapping: {mapping}")
    return mapping


if __name__ == "__main__":
    pod_node_mapping_example(namespace=NAMESPACE, label_selector=LABEL_SELECTOR)

from k3s_client.api.pods import PodManager

LABEL_SELECTOR = None
KUBECONFIG_PATH = None


def list_nodes_example(
    label_selector: str | None = LABEL_SELECTOR,
    kubeconfig_path: str | None = KUBECONFIG_PATH,
) -> list[dict]:
    """List cluster nodes, optionally filtered by a Kubernetes label selector."""
    manager = PodManager(kubeconfig_path=kubeconfig_path)
    nodes = manager.list_nodes(label_selector=label_selector)

    for node in nodes:
        metadata = node.get("metadata") or {}
        print(metadata.get("name"), metadata.get("labels") or {})

    return nodes


if __name__ == "__main__":
    list_nodes_example()

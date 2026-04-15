from k3s_client.api.applications import ApplicationManager

NAMESPACE = "default"
CONFIGMAP_NAME = "example-configmap"
LITERAL_DATA = ["key1=value1", "key2=value2"]


def create_configmap_example(
    namespace: str = NAMESPACE,
    kubeconfig_path: str | None = None,
) -> str:
    """
    Create an example ConfigMap in the given namespace.

    Args:
        namespace: Kubernetes namespace to create the ConfigMap in (default: "default").
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        The name of the created ConfigMap.
    """
    app = ApplicationManager(kubeconfig_path=kubeconfig_path)
    cm_name = "example-configmap"

    output = app.create_configmap(
        name=cm_name,
        namespace=namespace,
        from_literal=LITERAL_DATA,
    )

    print("ConfigMap create output:", output)
    return cm_name


if __name__ == "__main__":
    create_configmap_example(namespace=NAMESPACE)

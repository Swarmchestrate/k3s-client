from k3s_client.api.applications import ApplicationManager


def create_configmap_example(namespace: str = "default") -> str:
    """
    Create an example ConfigMap in the given namespace.

    Args:
        namespace: Kubernetes namespace to create the ConfigMap in (default: "default").

    Returns:
        The name of the created ConfigMap.
    """
    app = ApplicationManager()
    cm_name = "example-configmap"

    output = app.create_configmap(
        name=cm_name,
        namespace=namespace,
        from_literal=["key1=value1", "key2=value2"],
        app_label="example-configmap",
    )

    print("ConfigMap create output:", output)
    return cm_name


# Example usage (can be imported and called from another script):
# cm_name = create_configmap_example(namespace="default")

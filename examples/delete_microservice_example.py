from k3s_client.api.applications import ApplicationManager

APP_LABEL = "my-app"
NAMESPACE = "default"
KUBECONFIG_PATH = "/etc/rancher/k3s/k3s.yaml"


def delete_microservice_example(
    app_label: str = APP_LABEL,
    namespace: str = NAMESPACE,
    kubeconfig_path: str | None = None,
) -> str:
    """
    Delete a complete microservice deployment and service by label selector.

    Args:
        app_label: Application label value or full label selector (e.g. "my-app" or "app=my-app").
        namespace: Kubernetes namespace.
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        The API response from the deletion operation.
    """
    manager = ApplicationManager(kubeconfig_path=kubeconfig_path)
    result = manager.delete_microservice(app_label=app_label, namespace=namespace)
    print(f"✅ Deleted microservice resources with label {app_label}")
    return str(result)


if __name__ == "__main__":
    delete_microservice_example(
        app_label=APP_LABEL,
        namespace=NAMESPACE,
        kubeconfig_path=KUBECONFIG_PATH,
    )

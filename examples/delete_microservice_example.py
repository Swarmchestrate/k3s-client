from k3s_client.api.applications import ApplicationManager

APP_LABEL = "app=my-app"
NAMESPACE = "default"


def delete_microservice_example(
    app_label: str = APP_LABEL, namespace: str = NAMESPACE
) -> str:
    """
    Delete a complete microservice deployment and service by label selector.

    Args:
        app_label: Label selector for the application.
        namespace: Kubernetes namespace.

    Returns:
        The API response from the deletion operation.
    """
    manager = ApplicationManager()
    result = manager.delete_microservice(app_label=app_label, namespace=namespace)
    print(f"✅ Deleted microservice resources with label {app_label}")
    return str(result)


if __name__ == "__main__":
    delete_microservice_example(app_label=APP_LABEL, namespace=NAMESPACE)

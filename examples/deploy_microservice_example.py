from k3s_client.api.applications import ApplicationManager

DEPLOYMENT_NAME = "my-app"
IMAGE = "nginx:1.25"
CONTAINER_NAME = "app"
REPLICAS = 2
NAMESPACE = "default"
LABELS = {"app": DEPLOYMENT_NAME}
PORTS = [{"port": 80, "targetPort": 80, "nodePort": 30080}]
ENV = {"EXAMPLE_VAR": "example-value"}
NODE_SELECTOR = None
SERVICE_TYPE = "NodePort"


def deploy_microservice_example(
    deployment_name: str = DEPLOYMENT_NAME,
    image: str = IMAGE,
    container_name: str = CONTAINER_NAME,
    replicas: int = REPLICAS,
    namespace: str = NAMESPACE,
    labels: dict = LABELS,
    env: dict = ENV,
    ports: list = PORTS,
    node_selector: dict = NODE_SELECTOR,
    service_type: str = SERVICE_TYPE,
    kubeconfig_path: str | None = None,
) -> str:
    """
    Deploy a new microservice deployment and optional service.

    Args:
        deployment_name: Deployment name.
        image: Container image.
        container_name: Container name inside the pod.
        replicas: Number of replicas.
        namespace: Kubernetes namespace.
        labels: Labels to apply to deployment and service.
        env: Environment variables for the container.
        ports: List of service/container ports.
        node_selector: Node selector labels.
        service_type: Kubernetes service type.
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        Deployment and service creation result.
    """
    manager = ApplicationManager(kubeconfig_path=kubeconfig_path)
    result = manager.create_microservice(
        deployment_name=deployment_name,
        image=image,
        container_name=container_name,
        replicas=replicas,
        namespace=namespace,
        labels=labels,
        env=env,
        ports=ports,
        node_selector=node_selector,
        service_type=service_type,
    )
    print(f"✅ Deployed microservice {deployment_name}")
    print(result)
    return str(result)


if __name__ == "__main__":
    deploy_microservice_example(
        deployment_name=DEPLOYMENT_NAME,
        image=IMAGE,
        container_name=CONTAINER_NAME,
        replicas=REPLICAS,
        namespace=NAMESPACE,
        labels=LABELS,
        env=ENV,
        ports=PORTS,
        node_selector=NODE_SELECTOR,
        service_type=SERVICE_TYPE,
    )

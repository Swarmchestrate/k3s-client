from k3s_client.api.applications import ApplicationManager

DEPLOYMENT_NAME = "my-app"
CONTAINER_NAME = "app"
NEW_IMAGE = "nginx:1.25"
NAMESPACE = "default"


def update_microservice_image_example(
    deployment_name: str = DEPLOYMENT_NAME,
    container_name: str = CONTAINER_NAME,
    new_image: str = NEW_IMAGE,
    namespace: str = NAMESPACE,
) -> str:
    """
    Update the container image of a microservice using a rolling update.

    Args:
        deployment_name: Name of the Kubernetes deployment.
        container_name: Name of the container to update.
        new_image: New container image to deploy.
        namespace: Kubernetes namespace.

    Returns:
        The API response from the image update operation.
    """
    manager = ApplicationManager()
    result = manager.update_microservice_image(
        deployment_name=deployment_name,
        container_name=container_name,
        new_image=new_image,
        namespace=namespace,
    )
    print(f"✅ Updated deployment {deployment_name}: set {container_name} image to {new_image}")
    return str(result)


if __name__ == "__main__":
    update_microservice_image_example(
        deployment_name=DEPLOYMENT_NAME,
        container_name=CONTAINER_NAME,
        new_image=NEW_IMAGE,
        namespace=NAMESPACE,
    )

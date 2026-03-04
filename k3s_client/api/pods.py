from kubernetes import client
import logging

from k3s_client.exceptions import K3sClientError
from k3s_client.config import DEFAULT_LABEL, DEFAULT_NAMESPACE
from k3s_client.utils.kubeconfig import load_kubeconfig

logger = logging.getLogger(__name__)


def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except K3sClientError:
            raise
        except Exception as e:
            logger.exception("Error in %s", func.__name__)
            raise K3sClientError(str(e))

    return wrapper


class PodManager:
    """Manage pods: launch, destroy, list, logs."""

    def __init__(self, kubeconfig_path=None):
        load_kubeconfig(kubeconfig_path)
        self.v1 = client.CoreV1Api()

    @handle_errors
    def list_pods(self, namespace=None, label_selector=None):
        namespace = namespace or DEFAULT_NAMESPACE
        pods = self.v1.list_namespaced_pod(namespace, label_selector=label_selector)
        return [p.metadata.name for p in pods.items]

    @handle_errors
    def launch_pod(
        self,
        name,
        image,
        pod_labels=None,
        node_labels=None,
        namespace=None,
        container_port=None,
    ):
        namespace = namespace or DEFAULT_NAMESPACE
        pod_labels = pod_labels or DEFAULT_LABEL

        spec = client.V1PodSpec(
            containers=[
                client.V1Container(
                    name=name,
                    image=image,
                    ports=[client.V1ContainerPort(container_port=container_port)]
                    if container_port
                    else None,
                )
            ],
            node_selector=node_labels,
        )
        metadata = client.V1ObjectMeta(name=name, labels=pod_labels)
        pod = client.V1Pod(metadata=metadata, spec=spec)
        self.v1.create_namespaced_pod(namespace=namespace, body=pod)
        return f"Pod {name} launched successfully"

    @handle_errors
    def destroy_pod(self, pod_name=None, pod_label=None, namespace=None):
        namespace = namespace or DEFAULT_NAMESPACE
        if pod_name:
            self.v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            return f"Pod {pod_name} deleted successfully"

        label_selector = pod_label or f"{DEFAULT_LABEL['managed-by']}=libarray"
        pods = self.v1.list_namespaced_pod(namespace, label_selector=label_selector)
        for pod in pods.items:
            self.v1.delete_namespaced_pod(name=pod.metadata.name, namespace=namespace)
        return f"Pods deleted with label: {label_selector}"

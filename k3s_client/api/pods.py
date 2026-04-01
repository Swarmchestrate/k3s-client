import logging
from kubernetes import client
from k3s_client.utils.kubeconfig import load_kubeconfig
from k3s_client.exceptions import K3sClientError

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
    """Manage pod lifecycle."""

    @handle_errors
    def __init__(self, kubeconfig_path=None, default_namespace=None):
        load_kubeconfig(kubeconfig_path)
        self.v1 = client.CoreV1Api()
        self.default_namespace = default_namespace or "default"
        logger.info("Initialized PodManager with namespace=%s", self.default_namespace)

    @handle_errors
    def list_pods(self, namespace=None, label_selector=None):
        namespace = namespace or self.default_namespace
        pods = self.v1.list_namespaced_pod(
            namespace=namespace, label_selector=label_selector
        )
        return [p.metadata.name for p in pods.items]

    @handle_errors
    def launch_pod(
        self,
        name,
        image,
        pod_labels=None,
        node_labels=None,
        node_name=None,
        namespace=None,
        container_port=None,
    ):
        namespace = namespace or self.default_namespace
        pod_metadata = client.V1ObjectMeta(name=name, labels=pod_labels)

        container = client.V1Container(name=name, image=image)
        if container_port:
            container.ports = [client.V1ContainerPort(container_port=container_port)]

        pod_spec = client.V1PodSpec(containers=[container])
        if node_labels:
            pod_spec.node_selector = node_labels
        if node_name:
            pod_spec.node_name = node_name

        pod = client.V1Pod(metadata=pod_metadata, spec=pod_spec)

        self.v1.create_namespaced_pod(namespace=namespace, body=pod)
        node_info = f" on node {node_name}" if node_name else ""
        return f"Pod {name} launched in {namespace}{node_info}"

    @handle_errors
    def destroy_pod(self, pod_name=None, pod_label=None, namespace=None):
        namespace = namespace or self.default_namespace
        if pod_name:
            self.v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            return f"Pod {pod_name} deleted from {namespace}"

        if pod_label:
            pods = self.v1.list_namespaced_pod(
                namespace=namespace, label_selector=pod_label
            )
            for p in pods.items:
                self.v1.delete_namespaced_pod(name=p.metadata.name, namespace=namespace)
            return f"Pods {pod_label} deleted from {namespace}"

        raise ValueError("Either pod_name or pod_label must be provided")

    @handle_errors
    def get_pod_node_mapping(self, namespace=None, label_selector=None):
        """Get mapping of pod names to node names."""
        namespace = namespace or self.default_namespace
        pods = self.v1.list_namespaced_pod(
            namespace=namespace, label_selector=label_selector
        )
        mapping = {}
        for pod in pods.items:
            pod_name = pod.metadata.name
            node_name = pod.spec.node_name if pod.spec.node_name else "Not scheduled"
            mapping[pod_name] = node_name
        return mapping

import logging

from k3s_client.api.pods import PodManager
from k3s_client.cli.kubectl import Kubectl
from k3s_client.exceptions import K3sClientError
from k3s_client.config import DEFAULT_NAMESPACE

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


class ApplicationManager:
    """Manage applications via manifests or manual pods."""

    def __init__(self, kubeconfig_path=None, use_kubectl=True):
        self.kubectl = Kubectl(kubeconfig=kubeconfig_path, use_kubectl=use_kubectl)
        self.pod_manager = PodManager(kubeconfig_path)
        self.manifest_registry = {}  # app_label -> {type, resource, namespace}

    @handle_errors
    def apply_manifest(self, manifest_file, app_label=None, namespace=None):
        namespace = namespace or DEFAULT_NAMESPACE
        key = app_label or manifest_file
        output = self.kubectl.apply(manifest_path=manifest_file)
        self.manifest_registry[key] = {
            "type": "manifest",
            "resource": manifest_file,
            "namespace": namespace,
        }
        return output

    @handle_errors
    def create_configmap(
        self, name, namespace=None, from_literal=None, from_file=None, app_label=None
    ):
        namespace = namespace or DEFAULT_NAMESPACE
        key = app_label or name
        output = self.kubectl.apply(
            configmap_name=name,
            namespace=namespace,
            from_literal=from_literal,
            from_file=from_file,
        )
        self.manifest_registry[key] = {
            "type": "configmap",
            "resource": name,
            "namespace": namespace,
        }
        return output

    @handle_errors
    def delete_application(self, app_label=None, namespace=None):
        namespace = namespace or DEFAULT_NAMESPACE
        key = app_label or namespace
        if key in self.manifest_registry:
            resource = self.manifest_registry[key]["resource"]
            output = self.kubectl.delete(resource)
            del self.manifest_registry[key]
            return output
        else:
            label_selector = f"app={app_label}" if app_label else None
            return self.pod_manager.destroy_pod(
                pod_label=label_selector, namespace=namespace
            )

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
        return self.pod_manager.launch_pod(
            name=name,
            image=image,
            pod_labels=pod_labels,
            node_labels=node_labels,
            namespace=namespace,
            container_port=container_port,
        )

    @handle_errors
    def get_pod_logs(self, pod_name, namespace=None):
        return self.pod_manager.get_pod_logs(pod_name, namespace)

import logging
from io import StringIO

from ruamel.yaml import YAML

from k3s_client.cli.kubectl import Kubectl
from k3s_client.exceptions import K3sClientError

logger = logging.getLogger(__name__)
yaml = YAML()


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
    """Manage pods directly through the Kubernetes SDK."""

    @handle_errors
    def __init__(
        self,
        kubeconfig_path=None,
    ):
        self.kubectl = Kubectl(kubeconfig=kubeconfig_path)
        logger.info("Initialized PodManager")

    @staticmethod
    def _load_yaml_documents(yaml_text: str):
        return [doc for doc in yaml.load_all(StringIO(yaml_text)) if doc is not None]

    @handle_errors
    def list_pods(self, label_selector=None):
        pod_payload = self.kubectl.get("pod", label_selector=label_selector)
        if isinstance(pod_payload, dict):
            document = pod_payload
        else:
            documents = self._load_yaml_documents(pod_payload)
            if not documents:
                return []
            document = documents[0]

        if not isinstance(document, dict):
            return []

        return [
            item for item in (document.get("items") or []) if isinstance(item, dict)
        ]

    @handle_errors
    def get_grouped_pod_node_mapping(self, label_selector=None):
        grouped = {}
        for pod in self.list_pods(label_selector=label_selector):
            metadata = pod.get("metadata") or {}
            labels = metadata.get("labels") or {}
            msid = labels.get("service") or labels.get("app") or metadata.get("name")
            pod_name = metadata.get("name")
            node_name = (pod.get("spec") or {}).get("nodeName")
            if not msid or not pod_name:
                continue
            grouped.setdefault(msid, {})[pod_name] = node_name
        return grouped

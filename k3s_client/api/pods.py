import logging
import math
from decimal import Decimal, InvalidOperation
from io import StringIO

from ruamel.yaml import YAML

from k3s_client.cli.kubectl import Kubectl
from k3s_client.exceptions import K3sClientError

logger = logging.getLogger(__name__)
yaml = YAML()


def parse_cpu_quantity(value):
    """Convert a Kubernetes CPU quantity to millicores."""
    if value is None:
        return 0
    quantity = str(value).strip()
    multiplier = Decimal(1)
    if quantity.endswith("m"):
        quantity = quantity[:-1]
        multiplier = Decimal("0.001")
    try:
        return math.ceil(Decimal(quantity) * multiplier * 1000)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid CPU quantity: {value!r}") from exc


def parse_memory_quantity(value):
    """Convert a Kubernetes memory quantity to bytes."""
    if value is None:
        return 0
    quantity = str(value).strip()
    multipliers = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
    }
    suffix = next((unit for unit in multipliers if quantity.endswith(unit)), None)
    multiplier = Decimal(multipliers[suffix]) if suffix else Decimal(1)
    if suffix:
        quantity = quantity[: -len(suffix)]
    try:
        return math.ceil(Decimal(quantity) * multiplier)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid memory quantity: {value!r}") from exc


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
    def _list_pods(self, label_selector=None):
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
    def list_nodes(self, label_selector=None):
        """Fetch all cluster nodes, optionally filtered by a label selector."""
        node_payload = self.kubectl.get("node", label_selector=label_selector)
        if isinstance(node_payload, dict):
            document = node_payload
        else:
            documents = self._load_yaml_documents(node_payload)
            if not documents:
                return []
            document = documents[0]

        if not isinstance(document, dict):
            return []

        return [
            item for item in (document.get("items") or []) if isinstance(item, dict)
        ]

    @staticmethod
    def _pod_resource_requests(pod):
        spec = pod.get("spec") or {}
        regular_requests = {"cpu": 0, "memory": 0}
        for container in spec.get("containers") or []:
            requests = ((container.get("resources") or {}).get("requests") or {})
            regular_requests["cpu"] += parse_cpu_quantity(requests.get("cpu"))
            regular_requests["memory"] += parse_memory_quantity(
                requests.get("memory")
            )

        init_requests = {"cpu": 0, "memory": 0}
        for container in spec.get("initContainers") or []:
            requests = ((container.get("resources") or {}).get("requests") or {})
            init_requests["cpu"] = max(
                init_requests["cpu"], parse_cpu_quantity(requests.get("cpu"))
            )
            init_requests["memory"] = max(
                init_requests["memory"], parse_memory_quantity(
                    requests.get("memory")
                )
            )

        overhead = spec.get("overhead") or {}
        return {
            "cpu": max(regular_requests["cpu"], init_requests["cpu"])
            + parse_cpu_quantity(overhead.get("cpu")),
            "memory": max(regular_requests["memory"], init_requests["memory"])
            + parse_memory_quantity(overhead.get("memory")),
        }

    @handle_errors
    def get_node_capacity(self, label_selector=None):
        """Return Ready-node capacity in millicores and bytes."""
        nodes = []
        for node in self.list_nodes(label_selector=label_selector):
            status = node.get("status") or {}
            ready = any(
                condition.get("type") == "Ready"
                and str(condition.get("status")).lower() == "true"
                for condition in status.get("conditions") or []
                if isinstance(condition, dict)
            )
            if not ready:
                continue

            metadata = node.get("metadata") or {}
            allocatable = status.get("allocatable") or {}
            nodes.append(
                {
                    "name": metadata.get("name"),
                    "labels": dict(metadata.get("labels") or {}),
                    "allocatable": {
                        "cpu_millicores": parse_cpu_quantity(allocatable.get("cpu")),
                        "memory_bytes": parse_memory_quantity(
                            allocatable.get("memory")
                        ),
                    },
                    "requested": {"cpu_millicores": 0, "memory_bytes": 0},
                }
            )

        nodes_by_name = {node["name"]: node for node in nodes if node["name"]}
        for pod in self._list_pods():
            phase = ((pod.get("status") or {}).get("phase") or "").lower()
            if phase not in {"running", "pending"}:
                continue
            node_name = (pod.get("spec") or {}).get("nodeName")
            node = nodes_by_name.get(node_name)
            if node is None:
                continue
            requests = self._pod_resource_requests(pod)
            node["requested"]["cpu_millicores"] += requests["cpu"]
            node["requested"]["memory_bytes"] += requests["memory"]

        for node in nodes:
            node["free"] = {
                resource: max(
                    node["allocatable"][resource] - node["requested"][resource], 0
                )
                for resource in ("cpu_millicores", "memory_bytes")
            }
        return nodes

    @handle_errors
    def find_best_fit_node(self, requests, label_selector=None, exclude=None):
        """Find the fitting Ready node with the least normalized spare capacity."""
        requested_cpu = parse_cpu_quantity(requests.get("cpu"))
        requested_memory = parse_memory_quantity(requests.get("memory"))
        excluded = {exclude} if isinstance(exclude, str) else set(exclude or [])
        candidates = []
        for node in self.get_node_capacity(label_selector=label_selector):
            if node["name"] in excluded:
                continue
            free = node["free"]
            if (
                free["cpu_millicores"] < requested_cpu
                or free["memory_bytes"] < requested_memory
            ):
                continue
            allocatable = node["allocatable"]
            waste = (
                (free["cpu_millicores"] - requested_cpu)
                / max(allocatable["cpu_millicores"], 1)
                + (free["memory_bytes"] - requested_memory)
                / max(allocatable["memory_bytes"], 1)
            )
            candidates.append((waste, node["name"] or "", node))
        return min(candidates, default=(None, None, None))[2]

    def _get_grouped_pod_node_mapping(self, label_selector=None):
        grouped = {}
        for pod in self._list_pods(label_selector=label_selector):
            metadata = pod.get("metadata") or {}
            labels = metadata.get("labels") or {}
            msid = labels.get("service") or labels.get("app") or metadata.get("name")
            pod_name = metadata.get("name")
            node_name = (pod.get("spec") or {}).get("nodeName")
            if not msid or not pod_name:
                continue
            grouped.setdefault(msid, {})[pod_name] = node_name
        return grouped

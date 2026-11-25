from __future__ import annotations

from io import StringIO
from tempfile import NamedTemporaryFile
from typing import Any

from ruamel.yaml import YAML

from k3s_client.api.pods import (
    PodManager,
    parse_cpu_quantity,
    parse_memory_quantity,
)
from k3s_client.cli.kubectl import Kubectl
from k3s_client.exceptions import K3sClientError
from k3s_client.utils.manifest import (
    NODE_RESOURCE_LABEL_KEY,
    build_pinned_deployment_name,
    build_pinned_node_affinity,
    build_pinned_pod_manifest,
    get_microservice_container_spec,
    get_microservice_deployment,
    normalize_resource_name,
)

yaml = YAML()
yaml.width = 4096  # avoid wrapping long scalar values (e.g. domains) onto a new line


class OptimizerRuntimeClient:
    """Local runtime helper for node-pinned optimizer actions.

    This client reads the live Deployment from the cluster, builds a pinned
    single-replica Deployment, and applies or removes it with a dedicated
    field manager.
    """

    def __init__(
        self,
        kubeconfig_path: str | None = None,
    ):
        self.kubectl = Kubectl(kubeconfig=kubeconfig_path)
        self.pod_manager = PodManager(kubeconfig_path=kubeconfig_path)

    def _check_node_capacity(self, nodeid: str, container_spec: dict[str, Any]):
        node = next(
            (
                candidate
                for candidate in self.pod_manager.get_node_capacity()
                if (candidate.get("labels") or {}).get(NODE_RESOURCE_LABEL_KEY)
                == nodeid
            ),
            None,
        )
        if node is None:
            raise K3sClientError(f"Target node '{nodeid}' not found or not Ready")

        labels = node.get("labels") or {}
        affinity = build_pinned_node_affinity(nodeid, container_spec.get("affinity"))
        expressions = affinity["nodeAffinity"][
            "requiredDuringSchedulingIgnoredDuringExecution"
        ]["nodeSelectorTerms"][0]["matchExpressions"][1:]
        for expression in expressions:
            key = expression.get("key")
            operator = expression.get("operator")
            values = expression.get("values") or []
            if operator == "In":
                matches = key in labels and labels[key] in values
            elif operator == "NotIn":
                matches = key not in labels or labels[key] not in values
            elif operator == "Exists":
                matches = key in labels
            elif operator == "DoesNotExist":
                matches = key not in labels
            else:
                raise K3sClientError(
                    f"Unsupported node affinity operator '{operator}' for label '{key}'"
                )
            if not matches:
                raise K3sClientError(
                    f"Target node '{nodeid}' does not match required label '{key}'"
                )

        requests = ((container_spec.get("resources") or {}).get("requests") or {})
        requested_cpu = parse_cpu_quantity(requests.get("cpu"))
        requested_memory = parse_memory_quantity(requests.get("memory"))
        free = node.get("free") or {}
        available_cpu = free.get("cpu_millicores", 0)
        available_memory = free.get("memory_bytes", 0)
        if available_cpu < requested_cpu or available_memory < requested_memory:
            raise K3sClientError(
                f"Insufficient capacity on target node '{node['name']}': "
                f"requested cpu={requested_cpu}m, memory={requested_memory}B; "
                f"available cpu={available_cpu}m, memory={available_memory}B"
            )

    @staticmethod
    def _write_manifest(manifest: dict[str, Any]) -> str:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".yaml", delete=False
        ) as tmp:
            yaml.dump(manifest, tmp)
            return tmp.name

    def _load_document(self, yaml_text: str, *, kind: str) -> dict[str, Any]:
        document = yaml.load(StringIO(yaml_text))
        if not isinstance(document, dict):
            raise TypeError(f"Expected a {kind} document from kubectl")
        return document

    @staticmethod
    def _owner_deployment_name(pod: dict[str, Any]) -> str | None:
        metadata = pod.get("metadata") or {}
        owner_refs = metadata.get("ownerReferences") or []
        for owner in owner_refs:
            if not isinstance(owner, dict):
                continue
            if str(owner.get("kind")) == "Deployment" and owner.get("name"):
                return str(owner["name"])
        return None

    def _pod_document(self, pod_name: str) -> dict[str, Any]:
        pod_yaml = self.kubectl.get("pod", name=pod_name)
        return self._load_document(pod_yaml, kind="Pod")

    def _pod_list(self) -> list[dict[str, Any]]:
        pod_yaml = self.kubectl.get("pod")
        document = self._load_document(pod_yaml, kind="PodList")
        items = document.get("items") or []
        return [item for item in items if isinstance(item, dict)]

    def _select_pod_name(self, msid: str) -> str:
        msid_token = msid.replace("_", "-").lower()
        candidates: list[str] = []
        for pod in self._pod_list():
            metadata = pod.get("metadata") or {}
            labels = metadata.get("labels") or {}
            owner_name = self._owner_deployment_name(pod) or ""
            pod_name = str(metadata.get("name") or "")
            if labels.get("app") == msid or labels.get("service") == msid:
                candidates.append(pod_name)
                continue
            if owner_name.startswith(msid_token) or msid_token in owner_name:
                candidates.append(pod_name)

        if not candidates:
            raise ValueError(f"No pods found for microservice '{msid}'")
        return candidates[0]

    def _apply_manifest(
        self,
        manifest: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        manifest_file = self._write_manifest(manifest)
        output = self.kubectl.apply_manifest(
            manifest_file,
            field_manager="swarm-optimiser",
            dry_run=dry_run,
        )
        return {
            "manifest_file": manifest_file,
            "kubectl_output": output,
        }

    def create_pod(
        self,
        msid: str,
        nodeid: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        requested_nodeid = nodeid
        nodeid = normalize_resource_name(nodeid)
        container_spec = get_microservice_container_spec(msid)
        self._check_node_capacity(nodeid, container_spec)
        manifest = build_pinned_pod_manifest(
            msid=msid,
            node_id=nodeid,
            container_spec=container_spec,
        )
        apply_result = self._apply_manifest(manifest, dry_run=dry_run)
        result = {
            "ok": True,
            "operation": "create_pod",
            "msid": msid,
            "nodeid": nodeid,
            "deployment_name": build_pinned_deployment_name(msid, nodeid),
            "result": apply_result,
        }
        if requested_nodeid != nodeid:
            result["requested_nodeid"] = requested_nodeid
        return result

    def scale_to(
        self,
        msid: str,
        count: int,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        replicas = int(count)
        if replicas < 0:
            raise ValueError("count must be >= 0")

        scale_result = self.kubectl.scale(
            "deployment",
            msid,
            replicas,
            dry_run=dry_run,
        )
        return {
            "ok": True,
            "operation": "scale_to",
            "msid": msid,
            "count": replicas,
            "result": scale_result,
        }

    def delete_pod(
        self,
        msid: str,
        podid: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if podid is None:
            deployment = get_microservice_deployment(msid)
            replicas = int((deployment.get("spec") or {}).get("replicas") or 1)
            target = max(replicas - 1, 0)
            scale_result = self.kubectl.scale(
                "deployment",
                msid,
                target,
                dry_run=dry_run,
            )
            return {
                "ok": True,
                "operation": "delete_pod",
                "msid": msid,
                "podid": None,
                "scaled_to": target,
                "result": scale_result,
            }

        pod = self._pod_document(podid)
        owner_name = self._owner_deployment_name(pod)
        if owner_name and "-pinned-" in owner_name:
            scale_result = self.kubectl.scale(
                "deployment",
                owner_name,
                0,
                dry_run=dry_run,
            )
            delete_result = self.kubectl.delete(
                owner_name,
                resource_type="deployment",
                dry_run=dry_run,
            )
            return {
                "ok": True,
                "operation": "delete_pod",
                "msid": msid,
                "podid": podid,
                "pinned_deployment": owner_name,
                "scaled_to": 0,
                "scale_result": scale_result,
                "delete_result": delete_result,
            }

        self.kubectl.annotate(
            "pod",
            podid,
            "controller.kubernetes.io/pod-deletion-cost",
            "-999",
            dry_run=dry_run,
        )
        deployment = get_microservice_deployment(msid)
        replicas = int((deployment.get("spec") or {}).get("replicas") or 1)
        target = max(replicas - 1, 0)
        scale_result = self.kubectl.scale(
            "deployment",
            msid,
            target,
            dry_run=dry_run,
        )
        delete_result = None  # no explicit delete needed; scale-down removes podid deterministically

        return {
            "ok": True,
            "operation": "delete_pod",
            "msid": msid,
            "podid": podid,
            "scaled_to": target,
            "scale_result": scale_result,
            "delete_result": delete_result,
        }

    def migrate_pod(
        self,
        msid: str,
        podid: str | None = None,
        nodeid: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if not nodeid:
            raise ValueError("nodeid is required for migrate_pod")

        requested_nodeid = nodeid
        nodeid = normalize_resource_name(nodeid)
        container_spec = get_microservice_container_spec(msid)
        self._check_node_capacity(nodeid, container_spec)
        source_pod_name = podid or self._select_pod_name(msid)
        source_pod = self._pod_document(source_pod_name)
        owner_name = self._owner_deployment_name(source_pod)

        delete_result = None
        if owner_name and "-pinned-" in owner_name:
            self.kubectl.scale(
                "deployment",
                owner_name,
                0,
                dry_run=dry_run,
            )
            delete_result = self.kubectl.delete(
                owner_name,
                resource_type="deployment",
                dry_run=dry_run,
            )
        else:
            self.kubectl.annotate(
                "pod",
                source_pod_name,
                "controller.kubernetes.io/pod-deletion-cost",
                "-999",
                dry_run=dry_run,
            )
            deployment = get_microservice_deployment(msid)
            replicas = int((deployment.get("spec") or {}).get("replicas") or 1)
            self.kubectl.scale(
                "deployment",
                msid,
                max(replicas - 1, 0),
                dry_run=dry_run,
            )
            delete_result = None

        manifest = build_pinned_pod_manifest(
            msid=msid,
            node_id=nodeid,
            container_spec=container_spec,
        )
        apply_result = self._apply_manifest(manifest, dry_run=dry_run)

        result = {
            "ok": True,
            "operation": "migrate_pod",
            "msid": msid,
            "podid": source_pod_name,
            "nodeid": nodeid,
            "source_owner": owner_name,
            "result": {
                "delete_result": delete_result,
                "apply_result": apply_result,
                "deployment_name": build_pinned_deployment_name(msid, nodeid),
            },
        }
        if requested_nodeid != nodeid:
            result["requested_nodeid"] = requested_nodeid
        return result

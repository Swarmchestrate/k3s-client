import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from ruamel.yaml import YAML

from k3s_client.api.optimizer_runtime import OptimizerRuntimeClient
from k3s_client.api.pods import PodManager
from k3s_client.cli.kubectl import Kubectl
from k3s_client.exceptions import K3sClientError
from k3s_client.utils.manifest import (
    get_kubernetes_manifest,
    get_microservice_deployment,
)

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


class ApplicationManager:
    """Manage applications directly through local Kubernetes SDK helpers."""

    @handle_errors
    def __init__(self, kubeconfig_path=None, dry_run_by_default: bool = False):
        self.kubectl = Kubectl(kubeconfig=kubeconfig_path)
        self.pod_manager = PodManager(kubeconfig_path=kubeconfig_path)
        self.optimizer_runtime = OptimizerRuntimeClient(kubeconfig_path=kubeconfig_path)
        self.manifest_registry = {}
        self.dry_run_by_default = bool(dry_run_by_default)
        logger.info(
            "Initialized ApplicationManager dry_run_by_default=%s",
            self.dry_run_by_default,
        )

    def _effective_dry_run(self, dry_run: bool | None) -> bool:
        return self.dry_run_by_default if dry_run is None else bool(dry_run)

    @staticmethod
    def _dry_run_response(operation: str, params: dict, result=None):
        response = {
            "ok": True,
            "operation": operation,
            "mode": "dry-run",
            "executed": False,
            "params": params,
        }
        if result is not None:
            response["result"] = result
        return response

    @staticmethod
    def _write_manifest_documents(manifests, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            for i, manifest in enumerate(manifests):
                if i > 0:
                    f.write("---\n")
                yaml.dump(manifest, f)
        return str(path)

    @staticmethod
    def _manifest_kind_summary(manifests):
        summary = {}
        for manifest in manifests:
            kind = str((manifest or {}).get("kind") or "Unknown")
            summary[kind] = summary.get(kind, 0) + 1
        return summary

    @handle_errors
    def apply_tosca(
        self,
        *,
        tosca_file: str | None = None,
        tosca_content: str | None = None,
        image_pull_secret: str | None = None,
        acme_email: str | None = None,
        dry_run: bool | None = None,
        output_manifest_file: str | None = None,
    ):
        """Generate manifests from TOSCA and optionally apply them."""
        effective_dry_run = self._effective_dry_run(dry_run)

        manifests = get_kubernetes_manifest(
            tosca_file=tosca_file,
            tosca_content=tosca_content,
            image_pull_secret=image_pull_secret,
            acme_email=acme_email,
        )

        if output_manifest_file:
            manifest_file = self._write_manifest_documents(
                manifests, output_manifest_file
            )
        else:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".yaml", delete=False
            ) as tmp:
                manifest_file = self._write_manifest_documents(manifests, tmp.name)

        apply_response = self.kubectl.apply_manifest(
            manifest_file,
            dry_run=effective_dry_run,
        )

        return {
            "ok": True,
            "operation": "apply_tosca",
            "mode": "dry-run" if effective_dry_run else "apply",
            "input": {
                "tosca_file": tosca_file,
                "has_tosca_content": bool(tosca_content),
                "image_pull_secret_set": bool(image_pull_secret),
                "acme_email_set": bool(acme_email),
            },
            "manifest": {
                "file": manifest_file,
                "resource_count": len(manifests),
                "kind_summary": self._manifest_kind_summary(manifests),
            },
            "applied": not effective_dry_run,
            "apply_response": apply_response,
            "result": apply_response,
            "warnings": [],
        }

    @handle_errors
    def apply_manifest(
        self,
        manifest_file: str,
        dry_run: bool | None = None,
    ):
        params = {"manifest_file": manifest_file}
        if self._effective_dry_run(dry_run):
            dry_run_result = self.kubectl.apply_manifest(manifest_file, dry_run=True)
            return self._dry_run_response(
                "apply_manifest",
                params,
                result=dry_run_result,
            )

        output = self.kubectl.apply_manifest(manifest_file, dry_run=False)
        self.manifest_registry[manifest_file] = {"type": "manifest"}
        return output

    @handle_errors
    def delete_manifest(self, manifest_file: str, dry_run: bool | None = None):
        params = {"manifest_file": manifest_file}
        if self._effective_dry_run(dry_run):
            dry_run_result = self.kubectl.delete_manifest(manifest_file, dry_run=True)
            return self._dry_run_response(
                "delete_manifest",
                params,
                result=dry_run_result,
            )

        output = self.kubectl.delete_manifest(manifest_file, dry_run=False)
        self.manifest_registry.pop(manifest_file, None)
        return output

    @handle_errors
    def create_registry_secret(
        self,
        name: str,
        registry: str,
        username: str,
        password: str,
        email: str | None = None,
        replace: bool = True,
        dry_run: bool | None = None,
    ):
        params = {
            "name": name,
            "registry": registry,
            "username": username,
            "password": password,
            "email": email,
            "replace": replace,
        }
        if self._effective_dry_run(dry_run):
            dry_run_result = self.kubectl.create_registry_secret(
                name=name,
                registry=registry,
                username=username,
                password=password,
                email=email,
                dry_run=True,
            )
            return self._dry_run_response(
                "create_registry_secret",
                params,
                result=dry_run_result,
            )

        return self.kubectl.create_registry_secret(
            name=name,
            registry=registry,
            username=username,
            password=password,
            email=email,
            dry_run=False,
        )

    @handle_errors
    def create_pod(self, msid, nodeid=None, dry_run: bool | None = None):
        params = {"msid": msid, "nodeid": nodeid}
        effective_dry_run = self._effective_dry_run(dry_run)
        if effective_dry_run:
            if nodeid is None:
                deployment = get_microservice_deployment(msid)
                current = int((deployment.get("spec") or {}).get("replicas") or 1)
                dry_run_result = self.optimizer_runtime.scale_to(
                    msid,
                    current + 1,
                    dry_run=True,
                )
            else:
                dry_run_result = self.optimizer_runtime.create_pod(
                    msid=msid,
                    nodeid=nodeid,
                    dry_run=True,
                )
            return self._dry_run_response("create_pod", params, result=dry_run_result)

        if nodeid is None:
            deployment = get_microservice_deployment(msid)
            current = int((deployment.get("spec") or {}).get("replicas") or 1)
            return self.optimizer_runtime.scale_to(msid, current + 1, dry_run=False)

        return self.optimizer_runtime.create_pod(
            msid=msid, nodeid=nodeid, dry_run=False
        )

    @handle_errors
    def scale_to(self, msid, count, dry_run: bool | None = None):
        target_replicas = int(count)
        if target_replicas < 0:
            raise ValueError("count must be >= 0")

        params = {"msid": msid, "count": target_replicas}
        if self._effective_dry_run(dry_run):
            dry_run_result = self.optimizer_runtime.scale_to(
                msid,
                target_replicas,
                dry_run=True,
            )
            return self._dry_run_response("scale_to", params, result=dry_run_result)

        return self.optimizer_runtime.scale_to(msid, target_replicas, dry_run=False)

    @handle_errors
    def delete_pod(self, msid, podid=None, dry_run: bool | None = None):
        params = {"msid": msid, "podid": podid}
        if self._effective_dry_run(dry_run):
            dry_run_result = self.optimizer_runtime.delete_pod(
                msid=msid,
                podid=podid,
                dry_run=True,
            )
            return self._dry_run_response("delete_pod", params, result=dry_run_result)

        return self.optimizer_runtime.delete_pod(msid=msid, podid=podid, dry_run=False)

    @handle_errors
    def migrate_pod(
        self,
        msid,
        podid=None,
        nodeid=None,
        dry_run: bool | None = None,
    ):
        params = {"msid": msid, "podid": podid, "nodeid": nodeid}
        if self._effective_dry_run(dry_run):
            dry_run_result = self.optimizer_runtime.migrate_pod(
                msid=msid,
                podid=podid,
                nodeid=nodeid,
                dry_run=True,
            )
            return self._dry_run_response("migrate_pod", params, result=dry_run_result)

        return self.optimizer_runtime.migrate_pod(
            msid=msid,
            podid=podid,
            nodeid=nodeid,
            dry_run=False,
        )

    @handle_errors
    def delete_microservice(
        self,
        app_label,
        dry_run: bool | None = None,
    ):
        params = {"app_label": app_label}
        if self._effective_dry_run(dry_run):
            dry_run_result = self.kubectl.delete_by_label(
                f"app={app_label}",
                resource_types=["all", "configmap", "secret", "pvc", "ingress"],
                dry_run=True,
            )
            return self._dry_run_response(
                "delete_microservice",
                params,
                result=dry_run_result,
            )

        return self.kubectl.delete_by_label(
            f"app={app_label}",
            resource_types=["all", "configmap", "secret", "pvc", "ingress"],
            dry_run=False,
        )

    @handle_errors
    def get_pod_node_mapping(
        self,
        label_selector=None,
        dry_run: bool | None = None,
    ):
        """Get pod-node mapping grouped by microservice label.

        Returns shape: {msid: {pod_name: node_name}}
        """
        params = {"label_selector": label_selector}
        if self._effective_dry_run(dry_run):
            mapping = self.pod_manager.get_grouped_pod_node_mapping(
                label_selector=label_selector
            )
            return self._dry_run_response(
                "get_pod_node_mapping",
                params,
                result=mapping,
            )

        return self.pod_manager.get_grouped_pod_node_mapping(
            label_selector=label_selector
        )

import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from ruamel.yaml import YAML

from k3s_client.exceptions import K3sClientError
from k3s_client.agent import SwarmAgentClient
from k3s_client.utils.manifest import get_kubernetes_manifest

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
    """Manage applications by delegating operations to swarm-agent."""

    @handle_errors
    def __init__(
        self,
        kubeconfig_path=None,
        use_kubectl=True,
        default_namespace=None,
        execution_mode="swarm-agent",
        swarm_agent_url=None,
        swarm_agent_token=None,
        dry_run_by_default: bool = False,
    ):
        self.execution_mode = str(execution_mode or "swarm-agent").strip().lower()
        if self.execution_mode != "swarm-agent":
            raise ValueError("execution_mode must be 'swarm-agent'")

        # Legacy init params are accepted for backward compatibility.
        _ = kubeconfig_path, use_kubectl
        base_url = swarm_agent_url or os.getenv("SWARM_AGENT_URL")
        token = swarm_agent_token or os.getenv("SWARM_AGENT_TOKEN")
        self.agent = SwarmAgentClient(base_url=base_url, token=token)

        self.manifest_registry = {}
        self.default_namespace = default_namespace or "default"
        self.dry_run_by_default = bool(dry_run_by_default)
        logger.info(
            "Initialized ApplicationManager with namespace=%s mode=%s dry_run_by_default=%s",
            self.default_namespace,
            self.execution_mode,
            self.dry_run_by_default,
        )

    def _agent_execute(self, action, params):
        return self.agent.execute(action=action, params=params)

    def _effective_dry_run(self, dry_run: bool | None) -> bool:
        return self.dry_run_by_default if dry_run is None else bool(dry_run)

    @staticmethod
    def _dry_run_response(operation: str, params: dict):
        return {
            "ok": True,
            "operation": operation,
            "mode": "dry-run",
            "executed": False,
            "params": params,
        }

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

    # --------------------
    # Deploy workflow
    # --------------------
    @handle_errors
    def apply_tosca(
        self,
        *,
        tosca_file: str = None,
        tosca_content: str = None,
        namespace: str = None,
        image_pull_secret: str = None,
        acme_email: str = None,
        dry_run: bool | None = None,
        output_manifest_file: str = None,
    ):
        """Generate manifests from TOSCA and optionally apply them.

        Returns a standardized response object with generation/apply metadata.
        """
        effective_namespace = namespace or self.default_namespace
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

        apply_response = None
        if not effective_dry_run:
            apply_response = self.apply_manifest(
                manifest_file=manifest_file,
                namespace=effective_namespace,
                dry_run=False,
            )

        return {
            "ok": True,
            "operation": "apply_tosca",
            "mode": "dry-run" if effective_dry_run else "apply",
            "namespace": effective_namespace,
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
            "agent_response": apply_response,
            "warnings": [],
        }

    # --------------------
    # Manifest management
    # --------------------
    @handle_errors
    def apply_manifest(
        self,
        manifest_file: str,
        namespace: str = None,
        dry_run: bool | None = None,
    ):
        namespace = namespace or self.default_namespace
        logger.info("Applying manifest %s to namespace %s", manifest_file, namespace)
        params = {"manifest_file": manifest_file, "namespace": namespace}
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("apply_manifest", params)

        output = self._agent_execute(
            "applications.apply_manifest",
            params,
        )
        self.manifest_registry[manifest_file] = {
            "type": "manifest",
            "namespace": namespace,
        }
        return output

    @handle_errors
    def delete_manifest(self, manifest_file: str, dry_run: bool | None = None):
        params = {"manifest_file": manifest_file}
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("delete_manifest", params)

        output = self._agent_execute(
            "applications.delete_manifest",
            params,
        )
        self.manifest_registry.pop(manifest_file, None)
        return output

    # --------------------
    # Registry secret management
    # --------------------
    @handle_errors
    def create_registry_secret(
        self,
        name: str,
        registry: str,
        username: str,
        password: str,
        email: str = None,
        namespace: str = None,
        replace: bool = True,
        dry_run: bool | None = None,
    ):
        """Create/update registry secret from credential fields."""
        namespace = namespace or self.default_namespace
        params = {
            "name": name,
            "registry": registry,
            "username": username,
            "password": password,
            "email": email,
            "namespace": namespace,
            "replace": replace,
        }
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("create_registry_secret", params)

        return self._agent_execute(
            "applications.create_registry_secret",
            params,
        )

    @handle_errors
    def create_pod(
        self, msid, nodeid=None, namespace=None, dry_run: bool | None = None
    ):
        """Create one pod instance for a microservice.

        When nodeid is omitted, this scales the deployment by +1.
        When nodeid is provided, this creates one additional pod from the
        deployment template pinned to the requested node.
        """
        namespace = namespace or self.default_namespace
        params = {"msid": msid, "nodeid": nodeid, "namespace": namespace}
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("create_pod", params)

        return self._agent_execute(
            "applications.create_pod",
            params,
        )

    @handle_errors
    def scale_to(self, msid, count, namespace=None, dry_run: bool | None = None):
        """Scale a microservice to an exact replica count."""
        namespace = namespace or self.default_namespace
        target_replicas = int(count)
        if target_replicas < 0:
            raise ValueError("count must be >= 0")

        params = {"msid": msid, "count": target_replicas, "namespace": namespace}
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("scale_to", params)

        return self._agent_execute(
            "applications.scale_to",
            params,
        )

    @handle_errors
    def delete_pod(self, msid, podid=None, namespace=None, dry_run: bool | None = None):
        """Delete one pod instance for a microservice.

        If podid is provided, the deployment must be scaled down by one replica
        BEFORE that specific pod is deleted, otherwise Kubernetes will recreate
        a replacement pod and the delete has no effect. This ordering must be
        enforced by the swarm-agent handler for applications.delete_pod.

        If podid is omitted, the microservice deployment is scaled down by one
        replica and Kubernetes selects which pod to remove.
        """
        namespace = namespace or self.default_namespace
        params = {"msid": msid, "podid": podid, "namespace": namespace}
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("delete_pod", params)

        return self._agent_execute(
            "applications.delete_pod",
            params,
        )

    @handle_errors
    def migrate_pod(
        self,
        msid,
        podid=None,
        nodeid=None,
        namespace=None,
        dry_run: bool | None = None,
    ):
        """Move a pod for a microservice to a target node.

        If podid is omitted, one matching pod is selected automatically.
        """
        namespace = namespace or self.default_namespace
        params = {
            "msid": msid,
            "podid": podid,
            "nodeid": nodeid,
            "namespace": namespace,
        }
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("migrate_pod", params)

        return self._agent_execute(
            "applications.migrate_pod",
            params,
        )

    @handle_errors
    def delete_microservice(
        self,
        app_label,
        namespace=None,
        dry_run: bool | None = None,
    ):
        namespace = namespace or self.default_namespace
        logger.info(
            "Deleting microservice with app label %s in namespace %s",
            app_label,
            namespace,
        )
        params = {"app_label": app_label, "namespace": namespace}
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("delete_microservice", params)

        return self._agent_execute(
            "applications.delete_microservice",
            params,
        )

    @handle_errors
    def get_pod_node_mapping(
        self,
        namespace=None,
        label_selector=None,
        dry_run: bool | None = None,
    ):
        """Get pod-node mapping grouped by microservice label.

        Returns shape: {msid: {pod_name: node_name}}
        """
        namespace = namespace or self.default_namespace
        params = {"namespace": namespace, "label_selector": label_selector}
        if self._effective_dry_run(dry_run):
            return self._dry_run_response("get_pod_node_mapping", params)

        return self._agent_execute(
            "applications.get_grouped_pod_node_mapping",
            params,
        )

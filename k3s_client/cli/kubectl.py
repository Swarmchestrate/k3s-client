import base64
import json
import logging
import os

from kubernetes import client, config, dynamic
from kubernetes.client.rest import ApiException
from kubernetes.config.config_exception import ConfigException
from ruamel.yaml import YAML

from k3s_client.exceptions import K3sClientError

logger = logging.getLogger(__name__)
yaml = YAML()


class Kubectl:
    """Wrapper around Kubernetes SDK for manifest, configmap, and secret operations."""

    def __init__(
        self,
        kubeconfig: str | None = None,
    ):
        self.kubeconfig = kubeconfig

        try:
            config.load_incluster_config()
            logger.debug("Loaded in-cluster Kubernetes config")
        except ConfigException:
            try:
                config.load_kube_config(self.kubeconfig)
                logger.debug(
                    "Loaded kubeconfig from %s", self.kubeconfig or "default path"
                )
            except ConfigException as exc:
                raise K3sClientError(
                    f"Failed to load Kubernetes config: {exc}"
                ) from exc

        self.api_client = client.ApiClient()
        self.dynamic_client = dynamic.DynamicClient(self.api_client)
        self.apps_v1 = client.AppsV1Api(self.api_client)

    @staticmethod
    def _default_namespace() -> str:
        return "default"

    @staticmethod
    def _dry_run_arg(dry_run: bool) -> str | None:
        return "All" if dry_run else None

    @staticmethod
    def _load_yaml_documents(path: str) -> list[dict]:
        with open(path, encoding="utf-8") as handle:
            documents = [doc for doc in yaml.load_all(handle) if doc is not None]
        return [doc for doc in documents if isinstance(doc, dict)]

    def _serialize(self, payload, output: str = "yaml") -> str:
        try:
            sanitized = self.api_client.sanitize_for_serialization(payload)
        except AttributeError:
            if isinstance(payload, (dict, list, str, int, float, bool)) or payload is None:
                sanitized = payload
            elif hasattr(payload, "to_dict"):
                sanitized = payload.to_dict()
            else:
                sanitized = payload

        if output == "json":
            return json.dumps(sanitized)

        from io import StringIO

        stream = StringIO()
        yaml.dump(sanitized, stream)
        return stream.getvalue().strip()

    def _resource_for_gvk(self, api_version: str, kind: str):
        return self.dynamic_client.resources.get(api_version=api_version, kind=kind)

    def _resource_for_type(self, resource_type: str):
        mapping = {
            "pod": ("v1", "Pod"),
            "pods": ("v1", "Pod"),
            "deployment": ("apps/v1", "Deployment"),
            "deployments": ("apps/v1", "Deployment"),
            "service": ("v1", "Service"),
            "services": ("v1", "Service"),
            "configmap": ("v1", "ConfigMap"),
            "configmaps": ("v1", "ConfigMap"),
            "secret": ("v1", "Secret"),
            "secrets": ("v1", "Secret"),
            "pvc": ("v1", "PersistentVolumeClaim"),
            "persistentvolumeclaim": ("v1", "PersistentVolumeClaim"),
            "persistentvolumeclaims": ("v1", "PersistentVolumeClaim"),
            "ingress": ("networking.k8s.io/v1", "Ingress"),
            "ingresses": ("networking.k8s.io/v1", "Ingress"),
            "job": ("batch/v1", "Job"),
            "cronjob": ("batch/v1", "CronJob"),
            "replicaset": ("apps/v1", "ReplicaSet"),
            "statefulset": ("apps/v1", "StatefulSet"),
            "daemonset": ("apps/v1", "DaemonSet"),
        }
        key = resource_type.strip().lower()
        if key not in mapping:
            raise K3sClientError(f"Unsupported resource type: {resource_type}")
        api_version, kind = mapping[key]
        return self._resource_for_gvk(api_version, kind)

    def _namespace_for(self, resource, metadata: dict | None = None) -> str | None:
        if not getattr(resource, "namespaced", False):
            return None
        namespace = (metadata or {}).get("namespace")
        return namespace or self._default_namespace()

    def _apply_document(
        self,
        document: dict,
        field_manager: str,
        dry_run: bool = False,
    ):
        api_version = str(document.get("apiVersion") or "")
        kind = str(document.get("kind") or "")
        metadata = dict(document.get("metadata") or {})
        name = metadata.get("name")
        if not api_version or not kind or not name:
            raise K3sClientError(
                "Manifest document must include apiVersion, kind, and metadata.name"
            )

        resource = self._resource_for_gvk(api_version, kind)
        namespace = self._namespace_for(resource, metadata)
        patch_args = {
            "name": name,
            "body": document,
            "content_type": "application/apply-patch+yaml",
            "field_manager": field_manager,
            "force": True,
        }
        dry_run_value = self._dry_run_arg(dry_run)
        if dry_run_value:
            patch_args["dry_run"] = dry_run_value
        if namespace:
            patch_args["namespace"] = namespace

        try:
            response = resource.patch(**patch_args)
        except ApiException as exc:
            if exc.status != 404:
                raise K3sClientError(str(exc))

            create_args = {
                "body": document,
                "field_manager": field_manager,
            }
            if dry_run_value:
                create_args["dry_run"] = dry_run_value
            if namespace:
                create_args["namespace"] = namespace
            response = resource.create(**create_args)

        if dry_run:
            return self.api_client.sanitize_for_serialization(response)
        return f"{kind}/{name} configured"

    def _delete_document(self, document: dict, dry_run: bool = False):
        api_version = str(document.get("apiVersion") or "")
        kind = str(document.get("kind") or "")
        metadata = dict(document.get("metadata") or {})
        name = metadata.get("name")
        if not api_version or not kind or not name:
            raise K3sClientError(
                "Manifest document must include apiVersion, kind, and metadata.name"
            )

        resource = self._resource_for_gvk(api_version, kind)
        namespace = self._namespace_for(resource, metadata)
        delete_args = {"name": name}
        dry_run_value = self._dry_run_arg(dry_run)
        if dry_run_value:
            delete_args["dry_run"] = dry_run_value
        if namespace:
            delete_args["namespace"] = namespace

        try:
            response = resource.delete(**delete_args)
        except ApiException as exc:
            if exc.status != 404:
                raise K3sClientError(str(exc))
            response = None

        if dry_run:
            return self.api_client.sanitize_for_serialization(response)
        return f"{kind}/{name} deleted"

    def _delete_by_selector(
        self, resource_type: str, label_selector: str, dry_run: bool = False
    ):
        resource = self._resource_for_type(resource_type)
        namespace = (
            self._default_namespace()
            if getattr(resource, "namespaced", False)
            else None
        )
        list_args = {"label_selector": label_selector}
        if namespace:
            list_args["namespace"] = namespace

        response = resource.get(**list_args)
        items = list(getattr(response, "items", []) or [])
        dry_run_value = self._dry_run_arg(dry_run)
        delete_responses = []
        for item in items:
            metadata = getattr(item, "metadata", None)
            name = getattr(metadata, "name", None)
            if not name:
                continue
            delete_args = {"name": name}
            if dry_run_value:
                delete_args["dry_run"] = dry_run_value
            if namespace:
                delete_args["namespace"] = namespace
            try:
                delete_response = resource.delete(**delete_args)
                if dry_run:
                    delete_responses.append(
                        self.api_client.sanitize_for_serialization(delete_response)
                    )
            except ApiException as exc:
                if exc.status != 404:
                    raise K3sClientError(str(exc))
        if dry_run:
            return {
                "resource_type": resource_type,
                "count": len(items),
                "responses": delete_responses,
            }
        return len(items)

    # --------------------
    # Manifest operations
    # --------------------
    def apply_manifest(
        self,
        manifest_path: str,
        field_manager: str = "tosca-controller",
        dry_run: bool = False,
    ) -> str:
        """Apply a YAML manifest file using server-side apply through the SDK."""
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        outputs = [
            self._apply_document(doc, field_manager, dry_run=dry_run)
            for doc in self._load_yaml_documents(manifest_path)
        ]
        if dry_run:
            return outputs
        return "\n".join(outputs)

    def delete_manifest(self, manifest_path: str, dry_run: bool = False) -> str:
        """Delete resources listed in a YAML manifest file."""
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        outputs = [
            self._delete_document(doc, dry_run=dry_run)
            for doc in self._load_yaml_documents(manifest_path)
        ]
        if dry_run:
            return outputs
        return "\n".join(outputs)

    def scale(
        self,
        resource_type: str,
        name: str,
        replicas: int,
        dry_run: bool = False,
    ) -> str:
        """Scale a Kubernetes workload to an exact replica count."""
        dry_run_value = self._dry_run_arg(dry_run)
        if resource_type.strip().lower() in {"deployment", "deployments"}:
            patch_args = {
                "name": name,
                "namespace": self._default_namespace(),
                "body": {"spec": {"replicas": int(replicas)}},
            }
            if dry_run_value:
                patch_args["dry_run"] = dry_run_value
            try:
                response = self.apps_v1.patch_namespaced_deployment_scale(**patch_args)
            except ApiException as exc:
                raise K3sClientError(str(exc))
            if dry_run:
                return self.api_client.sanitize_for_serialization(response)
            return f"deployment/{name} scaled"

        resource = self._resource_for_type(resource_type)
        namespace = (
            self._default_namespace()
            if getattr(resource, "namespaced", False)
            else None
        )
        patch_args = {
            "name": name,
            "body": {"spec": {"replicas": int(replicas)}},
            "content_type": "application/merge-patch+json",
        }
        if dry_run_value:
            patch_args["dry_run"] = dry_run_value
        if namespace:
            patch_args["namespace"] = namespace
        try:
            response = resource.patch(**patch_args)
        except ApiException as exc:
            raise K3sClientError(str(exc))
        if dry_run:
            return self.api_client.sanitize_for_serialization(response)
        return f"{resource_type}/{name} scaled"

    # --------------------
    # ConfigMap operations
    # --------------------
    def create_configmap(
        self,
        name: str,
        from_literal: list[str] | None = None,
        from_file: list[str] | None = None,
    ) -> str:
        """Create or update a configmap from literals or files."""
        data = {}
        for literal in from_literal or []:
            if "=" not in literal:
                raise ValueError(f"Invalid literal format: {literal}")
            key, value = literal.split("=", 1)
            data[key] = value

        for file_arg in from_file or []:
            if "=" in file_arg:
                key, file_path = file_arg.split("=", 1)
            else:
                file_path = file_arg
                key = os.path.basename(file_path)
            with open(file_path, encoding="utf-8") as handle:
                data[key] = handle.read()

        body = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": name},
            "data": data,
        }
        return self._apply_document(body, field_manager="tosca-controller")

    def delete_configmap(self, name: str) -> str:
        """Delete a configmap by name."""
        return self.delete(name, resource_type="configmap")

    def create_registry_secret(
        self,
        name: str,
        registry: str,
        username: str,
        password: str,
        email: str | None = None,
        dry_run: bool = False,
    ) -> str:
        """Create or update a Docker registry secret idempotently."""
        auth_value = base64.b64encode(f"{username}:{password}".encode()).decode("utf-8")
        auth_entry = {
            "username": username,
            "password": password,
            "auth": auth_value,
        }
        if email:
            auth_entry["email"] = email

        docker_config = {"auths": {registry: auth_entry}}
        docker_config_json = json.dumps(docker_config, separators=(",", ":"))
        docker_config_b64 = base64.b64encode(docker_config_json.encode("utf-8")).decode(
            "utf-8"
        )

        body = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name},
            "type": "kubernetes.io/dockerconfigjson",
            "data": {".dockerconfigjson": docker_config_b64},
        }
        return self._apply_document(
            body,
            field_manager="tosca-controller",
            dry_run=dry_run,
        )

    def annotate(
        self,
        resource_type: str,
        name: str,
        key: str,
        value: str,
        dry_run: bool = False,
    ) -> str:
        """Set an annotation on a resource."""
        resource = self._resource_for_type(resource_type)
        namespace = (
            self._default_namespace()
            if getattr(resource, "namespaced", False)
            else None
        )
        dry_run_value = self._dry_run_arg(dry_run)
        patch_args = {
            "name": name,
            "body": {"metadata": {"annotations": {key: value}}},
            "content_type": "application/merge-patch+json",
        }
        if dry_run_value:
            patch_args["dry_run"] = dry_run_value
        if namespace:
            patch_args["namespace"] = namespace
        try:
            response = resource.patch(**patch_args)
        except ApiException as exc:
            raise K3sClientError(str(exc))
        if dry_run:
            return self.api_client.sanitize_for_serialization(response)
        return f"{resource_type}/{name} annotated"

    # --------------------
    # Generic delete
    # --------------------
    def delete(
        self,
        name_or_manifest: str,
        resource_type: str | None = None,
        dry_run: bool = False,
    ) -> str:
        """
        Delete a resource by name/type or a manifest file.
        If resource_type is provided, it deletes a named resource, otherwise treats as manifest.
        """
        if resource_type:
            resource = self._resource_for_type(resource_type)
            namespace = (
                self._default_namespace()
                if getattr(resource, "namespaced", False)
                else None
            )
            delete_args = {"name": name_or_manifest}
            dry_run_value = self._dry_run_arg(dry_run)
            if dry_run_value:
                delete_args["dry_run"] = dry_run_value
            if namespace:
                delete_args["namespace"] = namespace
            try:
                response = resource.delete(**delete_args)
            except ApiException as exc:
                if exc.status != 404:
                    raise K3sClientError(str(exc))
                response = None
            if dry_run:
                return self.api_client.sanitize_for_serialization(response)
            return f"{resource_type}/{name_or_manifest} deleted"
        else:
            if not os.path.exists(name_or_manifest):
                raise FileNotFoundError(f"Manifest file not found: {name_or_manifest}")
            return self.delete_manifest(name_or_manifest, dry_run=dry_run)

    def delete_by_label(
        self,
        label_selector: str,
        resource_types: list[str] | None = None,
        dry_run: bool = False,
    ) -> str:
        """Delete resources matching a label selector."""
        resource_types = resource_types or [
            "all",
            "configmap",
            "secret",
            "pvc",
            "ingress",
        ]
        expanded_resource_types = []
        for resource_type in resource_types:
            if resource_type == "all":
                expanded_resource_types.extend(
                    [
                        "deployment",
                        "service",
                        "pod",
                        "replicaset",
                        "statefulset",
                        "daemonset",
                        "job",
                        "cronjob",
                    ]
                )
            else:
                expanded_resource_types.append(resource_type)

        seen = set()
        deleted = 0
        dry_run_details = []
        for resource_type in expanded_resource_types:
            if resource_type in seen:
                continue
            seen.add(resource_type)
            delete_output = self._delete_by_selector(
                resource_type,
                label_selector,
                dry_run=dry_run,
            )
            if dry_run:
                deleted += int(delete_output["count"])
                dry_run_details.append(delete_output)
            else:
                deleted += delete_output
        if dry_run:
            return {
                "deleted": deleted,
                "label_selector": label_selector,
                "details": dry_run_details,
            }
        return f"Deleted {deleted} resources matching label selector {label_selector}"

    # --------------------
    # Get resources
    # --------------------
    def get(
        self,
        resource_type: str,
        name: str | None = None,
        label_selector: str | None = None,
        output: str = "yaml",
    ) -> str:
        """Get Kubernetes resources in YAML/JSON."""
        resource = self._resource_for_type(resource_type)
        namespace = (
            self._default_namespace()
            if getattr(resource, "namespaced", False)
            else None
        )
        get_args = {}
        if namespace:
            get_args["namespace"] = namespace
        if label_selector:
            get_args["label_selector"] = label_selector

        if name:
            get_args["name"] = name

        response = resource.get(**get_args)
        return self._serialize(response, output=output)

import subprocess
import logging
import os
from typing import Optional, List

from k3s_client.exceptions import K3sClientError

logger = logging.getLogger(__name__)


class Kubectl:
    """Wrapper around kubectl CLI for manifest, configmap, and secret operations."""

    def __init__(self, kubeconfig: Optional[str] = None, default_namespace: str = "default", use_kubectl: bool = True):
        self.kubeconfig = kubeconfig
        self.default_namespace = default_namespace
        self.use_kubectl = use_kubectl

    def _base_cmd(self) -> List[str]:
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd += ["--kubeconfig", self.kubeconfig]
        return cmd

    def _run(self, cmd: List[str], input_text: Optional[str] = None) -> str:
        logger.debug("Running command: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, input=input_text
            )
            if result.returncode != 0:
                msg = f"kubectl command failed: {result.stderr.strip()}\nstdout: {result.stdout.strip()}"
                logger.error(msg)
                raise K3sClientError(msg)
            return result.stdout.strip()
        except FileNotFoundError:
            raise K3sClientError("kubectl not installed or not in PATH")
        except Exception as e:
            raise K3sClientError(str(e))

    # --------------------
    # Manifest operations
    # --------------------
    def apply_manifest(self, manifest_path: str) -> str:
        """Apply a YAML manifest file."""
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        return self._run(self._base_cmd() + ["apply", "-f", manifest_path])

    def delete_manifest(self, manifest_path: str) -> str:
        """Delete a YAML manifest file."""
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        return self._run(self._base_cmd() + ["delete", "-f", manifest_path])

    # --------------------
    # ConfigMap operations
    # --------------------
    def create_configmap(
        self,
        name: str,
        namespace: Optional[str] = None,
        from_literal: Optional[List[str]] = None,
        from_file: Optional[List[str]] = None,
    ) -> str:
        """Create a configmap from literals or files."""
        namespace = namespace or self.default_namespace
        cmd = self._base_cmd() + ["create", "configmap", name, "-n", namespace, "--dry-run=client", "-o", "yaml"]

        for lit in from_literal or []:
            cmd += ["--from-literal", lit]
        for f in from_file or []:
            cmd += ["--from-file", f]

        # Generate YAML and apply
        yaml_output = self._run(cmd)
        return self._run(self._base_cmd() + ["apply", "-f", "-"], input_text=yaml_output)

    def delete_configmap(self, name: str, namespace: Optional[str] = None) -> str:
        """Delete a configmap by name."""
        namespace = namespace or self.default_namespace
        cmd = self._base_cmd() + ["delete", "configmap", name, "-n", namespace]
        return self._run(cmd)

    # --------------------
    # Generic delete
    # --------------------
    def delete(
        self,
        name_or_manifest: str,
        namespace: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> str:
        """
        Delete a resource by name/type or a manifest file.
        If resource_type is provided, it deletes a named resource, otherwise treats as manifest.
        """
        namespace = namespace or self.default_namespace
        cmd = self._base_cmd()
        if resource_type:
            cmd += ["delete", resource_type, name_or_manifest, "-n", namespace]
        else:
            if not os.path.exists(name_or_manifest):
                raise FileNotFoundError(f"Manifest file not found: {name_or_manifest}")
            cmd += ["delete", "-f", name_or_manifest]
        return self._run(cmd)

    # --------------------
    # Get resources
    # --------------------
    def get(
        self,
        resource_type: str,
        name: Optional[str] = None,
        namespace: Optional[str] = None,
        output: str = "yaml",
    ) -> str:
        """Get Kubernetes resources in YAML/JSON."""
        namespace = namespace or self.default_namespace
        cmd = self._base_cmd() + ["get", resource_type]
        if name:
            cmd += [name]
        cmd += ["-n", namespace, "-o", output]
        return self._run(cmd)

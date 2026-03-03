import subprocess
import logging
from ..exceptions import K3sClientError

logger = logging.getLogger(__name__)


class Kubectl:
    """wrapper around kubectl CLI for manifest operations."""

    def __init__(self, kubeconfig=None, use_kubectl=True):
        self.kubeconfig = kubeconfig
        self.use_kubectl = use_kubectl

    def _base_cmd(self):
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd += ["--kubeconfig", self.kubeconfig]
        return cmd

    def _run(self, cmd, input_text=None):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, input=input_text
            )
            if result.returncode != 0:
                logger.error("Command failed: %s", result.stderr.strip())
                raise K3sClientError(result.stderr.strip())
            return result.stdout
        except FileNotFoundError:
            raise K3sClientError("kubectl not installed or not in PATH")
        except Exception as e:
            raise K3sClientError(str(e))

    def apply(
        self,
        manifest_path=None,
        configmap_name=None,
        namespace=None,
        from_literal=None,
        from_file=None,
    ):
        if not self.use_kubectl:
            raise K3sClientError("kubectl CLI usage disabled")

        if configmap_name:
            # Build YAML from configmap creation
            create_cmd = self._base_cmd() + ["create", "configmap", configmap_name]
            if namespace:
                create_cmd += ["-n", namespace]
            for lit in from_literal or []:
                create_cmd += ["--from-literal", lit]
            for f in from_file or []:
                create_cmd += ["--from-file", f]
            create_cmd += ["--dry-run=client", "-o", "yaml"]

            yaml_output = self._run(create_cmd)
            apply_cmd = self._base_cmd() + ["apply", "-f", "-"]
            return self._run(apply_cmd, input_text=yaml_output)

        if not manifest_path:
            raise ValueError("manifest_path is required when not creating a configmap")
        return self._run(self._base_cmd() + ["apply", "-f", manifest_path])

    def delete(self, manifest_path):
        return self._run(self._base_cmd() + ["delete", "-f", manifest_path])

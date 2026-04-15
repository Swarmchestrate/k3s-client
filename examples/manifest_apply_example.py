from k3s_client.api.applications import ApplicationManager

MANIFEST_FILE = "generated-manifests.yaml"
KUBECONFIG_PATH = "/etc/rancher/k3s/k3s.yaml"


def apply_manifest_example(
    manifest_file: str = MANIFEST_FILE,
    kubeconfig_path: str | None = None,
) -> str:
    """
    Apply an existing Kubernetes manifest file using the ApplicationManager.

    Args:
        manifest_file: Path to a YAML manifest file containing Kubernetes resources.
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        The kubectl output from applying the manifest.
    """
    manager = ApplicationManager(kubeconfig_path=kubeconfig_path)
    result = manager.apply_manifest(manifest_file=manifest_file)
    print(f"✅ Applied manifest: {manifest_file}")
    return str(result)


if __name__ == "__main__":
    apply_manifest_example(
        manifest_file=MANIFEST_FILE,
        kubeconfig_path=KUBECONFIG_PATH,
    )

from k3s_client.api.applications import ApplicationManager

MANIFEST_FILE = "generated-manifests.yaml"
KUBECONFIG_PATH = "/etc/rancher/k3s/k3s.yaml"


def delete_manifest_example(
    manifest_file: str = MANIFEST_FILE,
    kubeconfig_path: str | None = None,
) -> str:
    """
    Delete resources defined in a previously applied Kubernetes manifest file.

    Args:
        manifest_file: Path to a YAML manifest file that was applied previously.
        kubeconfig_path: Optional path to a kubeconfig file.

    Returns:
        The kubectl output from deleting the manifest resources.
    """
    manager = ApplicationManager(kubeconfig_path=kubeconfig_path)
    result = manager.delete_manifest(manifest_file=manifest_file)
    print(f"✅ Deleted resources from manifest: {manifest_file}")
    return str(result)


if __name__ == "__main__":
    delete_manifest_example(
        manifest_file=MANIFEST_FILE,
        kubeconfig_path=KUBECONFIG_PATH,
    )

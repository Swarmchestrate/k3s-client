from k3s_client.api.applications import ApplicationManager

TOSCA_FILE = "examples/Bookinfo.yaml"
OUTPUT_FILE = "generated-manifests.yaml"
NAMESPACE = "default"


def apply_tosca_example(
    tosca_file: str = TOSCA_FILE,
    output_manifest_file: str = OUTPUT_FILE,
    namespace: str = NAMESPACE,
    dry_run_by_default: bool = True,
):
    """Demonstrate one-call TOSCA workflow with dry-run and apply override."""
    manager = ApplicationManager(dry_run_by_default=dry_run_by_default)

    preview = manager.apply_tosca(
        tosca_file=tosca_file,
        namespace=namespace,
        output_manifest_file=output_manifest_file,
    )
    print("Dry-run result:")
    print(preview)

    apply_result = manager.apply_tosca(
        tosca_file=tosca_file,
        namespace=namespace,
        output_manifest_file=output_manifest_file,
        dry_run=False,
    )
    print("Apply result:")
    print(apply_result)


if __name__ == "__main__":
    apply_tosca_example()

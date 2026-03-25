from k3s_client.utils.manifest import get_kubernetes_manifest
from k3s_client.api.applications import ApplicationManager
from pathlib import Path
from ruamel.yaml import YAML
from io import StringIO


def generate_and_apply_manifest_example(
    tosca_content: str,
    output_file: str = "generated-manifests.yaml",
    image_pull_secret: str = None,
    namespace: str = "default"
) -> str:
    """
    Generate Kubernetes manifests from TOSCA content and apply them.

    Args:
        tosca_content: YAML content in TOSCA format
        output_file: Path to save the generated YAML file
        image_pull_secret: Optional Kubernetes imagePullSecret name
        namespace: Kubernetes namespace to apply manifests to

    Returns:
        Success message from manifest application
    """
    # Generate manifests
    manifests = get_kubernetes_manifest(
        tosca_content=tosca_content,
        image_pull_secret=image_pull_secret,
    )
    print(f"Generated {len(manifests)} manifests")

    # Save to file
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.explicit_start = True

    buf = StringIO()
    for manifest in manifests:
        yaml.dump(manifest, buf)
        buf.write("\n---\n")  # separate resources

    Path(output_file).write_text(buf.getvalue(), encoding="utf-8")
    print(f"Saved manifests to {output_file}")

    # Apply to cluster
    manager = ApplicationManager()
    result = manager.apply_manifest(manifest_file=output_file, namespace=namespace)
    print(f"Applied manifests: {result}")

    return result


# Example TOSCA content
TOSCA_EXAMPLE = """
service_template:
  node_templates:
    app_server:
      type: SomeMicroservice
      properties:
        image: nginx:1.26
        replicas: 2
        ports:
          - port: 80
            targetPort: 80
        env:
          - name: ENV
            value: production
"""

# Example usage (can be imported and called from another script):
# result = generate_and_apply_manifest_example(
#     tosca_content=TOSCA_EXAMPLE,
#     output_file="my-app.yaml",
#     image_pull_secret="my-registry-secret",
#     namespace="production"
# )
from k3s_client.utils.manifest import get_kubernetes_manifest
from ruamel.yaml import YAML
from io import StringIO
from pathlib import Path

TOSCA_FILE = "examples/bookinfo.yaml"  # path relative to example folder
OUTPUT_FILE = "generated-manifests.yaml"
IMAGE_PULL_SECRET = "my-registry-secret"

# Generate manifests from TOSCA
manifests = get_kubernetes_manifest(
    tosca_file=TOSCA_FILE, image_pull_secret=IMAGE_PULL_SECRET
)

# Dump to YAML file
yaml = YAML()
yaml.indent(mapping=2, sequence=4, offset=2)
buf = StringIO()
for i, m in enumerate(manifests):
    if i > 0:
        buf.write("---\n")
    yaml.dump(m, buf)

Path(OUTPUT_FILE).write_text(buf.getvalue(), encoding="utf-8")
print(f"✅ Manifests generated: {OUTPUT_FILE}")

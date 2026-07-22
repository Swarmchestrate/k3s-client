# k3s-client

A lightweight Python client for managing microservices on Kubernetes k3s clusters through swarm-agent. It provides a clean API layer for registry/configmap operations, manifest orchestration, pod operations, and TOSCA-based manifest generation.

Quick start:

```bash
pip install k3s-client
```

```python
from k3s_client.api.applications import ApplicationManager

manager = ApplicationManager(dry_run_by_default=True)

# Generate manifests only (dry run)
preview = manager.apply_tosca(
    tosca_file="examples/Bookinfo.yaml",
    output_manifest_file="generated-manifests.yaml",
)

# Apply to cluster
result = manager.apply_tosca(
    tosca_file="examples/Bookinfo.yaml",
    output_manifest_file="generated-manifests.yaml",
    dry_run=False,
)
```

---

## Features

- **Registry Secret Management** — Create and rotate Docker registry secrets for private image pulls
- **Microservice Scaling** — Scale deployments and manipulate pods for optimizer workflows
- **Manifest Generation** — Generate Kubernetes manifests from TOSCA definitions
- **Pod Mapping** — Query pod-to-node mapping for placement decisions
---

## Prerequisites

- Python **3.12** or higher

---

## Installation

```bash
git clone https://github.com/Swarmchestrate/k3s-client.git
cd k3s-client
make install
```

This will install all dependencies and the Puccini TOSCA parser required for manifest generation.


## Methods

### `ApplicationManager`

| Method | Parameters | Description |
|--------|------------|-------------|
| `create_registry_secret` | `name`, `registry`, `username`, `password`, `email=None`, `namespace=None`, `replace=True` | Create a Docker registry pull secret |
| `apply_manifest` | `manifest_file`, `namespace=None` | Apply a Kubernetes manifest |
| `delete_manifest` | `manifest_file` | Delete resources defined in a manifest |
| `apply_tosca` | `tosca_file=None`, `tosca_content=None`, `namespace=None`, `image_pull_secret=None`, `acme_email=None`, `dry_run=False`, `output_manifest_file=None` | One-call flow: generate manifests from TOSCA and optionally apply with standardized output |
| `create_pod` | `msid`, `nodeid=None`, `namespace=None` | Create one pod for a microservice |
| `delete_pod` | `msid`, `podid=None`, `namespace=None` | Delete one pod for a microservice |
| `scale_to` | `msid`, `count`, `namespace=None` | Scale a microservice to exact replica count |
| `migrate_pod` | `msid`, `podid=None`, `nodeid=None`, `namespace=None` | Move a pod to another node |
| `delete_microservice` | `app_label`, `namespace=None` | Delete all resources for a given app label |
| `get_pod_node_mapping` | `namespace=None`, `label_selector=None` | Return pod-to-node mapping by microservice |

Deployment model:
1. Deploy applications using `apply_manifest`.
2. Perform runtime pod operations (`create_pod`, `delete_pod`, `scale_to`, `migrate_pod`) on workloads created by that manifest.
3. Remove applications using `delete_manifest`.

For pod-level methods, `msid` should match the deployed microservice/deployment name from the applied manifest.

For one-call TOSCA generate/apply workflow, see [examples/apply_tosca_example.py](examples/apply_tosca_example.py).

For pod-to-node mapping usage, see [examples/pod_node_mapping_example.py](examples/pod_node_mapping_example.py).

### Dry Run (`apply_tosca`)

`apply_tosca` supports dry-run mode to generate manifests and return a standardized summary without applying resources.

Dry-run options:

1. Dry run by default at initialization

```python
from k3s_client.api.applications import ApplicationManager

manager = ApplicationManager(dry_run_by_default=True)
preview = manager.apply_tosca(tosca_file="examples/Bookinfo.yaml")
```

2. Per-method dry run control

```python
from k3s_client.api.applications import ApplicationManager

manager = ApplicationManager(dry_run_by_default=True)

# Override default for this call
apply_result = manager.apply_tosca(
    tosca_file="examples/Bookinfo.yaml",
    dry_run=False,
)
```

Standardized response fields include:

- `ok`: operation success flag
- `mode`: `"dry-run"` or `"apply"`
- `manifest.file`: generated manifest file path
- `manifest.resource_count`: number of rendered resources
- `manifest.kind_summary`: resource count by Kubernetes kind
- `applied`: whether apply was executed
- `agent_response`: swarm-agent response when apply runs

---

### `PodManager`

| Method | Parameters | Description |
|--------|------------|-------------|
| `list_pods` | `namespace=None`, `label_selector=None` | List pods, optionally filtered by label |

---

### `get_kubernetes_manifest`

| Function | Parameters | Description |
|----------|------------|-------------|
| `get_kubernetes_manifest` | `tosca_file=None`, `tosca_content=None`, `image_pull_secret=None`, `acme_email=None` | Generate Kubernetes manifests from a TOSCA definition |

Provide exactly one input source: `tosca_file` or `tosca_content`.

HTTP routing is optional. Add a `routes` list under a microservice properties block to generate Kubernetes `Ingress` resources.

Defaults are applied for unspecified route/ingress fields (for example class, entry point, TLS, and cert resolver).

---

## Examples

The `examples/` directory contains complete runnable scripts:

| File | Description |
|------|-------------|
| `registry_secret_example.py` | Managing Docker registry secrets |
| `apply_tosca_example.py` | One-call TOSCA workflow (dry-run and apply) |
| `manifest_generator_example.py` | Generating Kubernetes manifests from TOSCA definitions |
| `manifest_apply_example.py` | Applying a generated manifest to the cluster |
| `manifest_delete_example.py` | Deleting resources defined in a manifest |
| `scale_microservice_example.py` | Scale a deployment to an exact replica count |
| `delete_microservice_example.py` | Delete a microservice deployment and service |
| `pod_node_mapping_example.py` | Show pod-to-node mapping for a namespace |

Run any example:

```bash
.venv/bin/python examples/scale_microservice_example.py
```

Examples use swarm-agent mode and default to local in-agent endpoint behavior.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes and add tests where applicable
4. Run the test suite (`pytest`)
5. Open a pull request

---

## License

Licensed under the [Apache License 2.0](LICENSE).

---

## Contact

For questions or feedback, reach out to [G.Kotak@westminster.ac.uk](mailto:G.Kotak@westminster.ac.uk)

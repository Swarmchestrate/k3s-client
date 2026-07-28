# k3s-client

A lightweight Python library for managing microservices on Kubernetes k3s clusters. It provides direct helpers for manifest orchestration, registry/configmap operations, pod operations, and TOSCA-based manifest generation.

## Python Library Package

This project is published as `k3s-client` and imported as `k3s_client`.

- Main classes:
    - `k3s_client.api.applications.ApplicationManager`
    - `k3s_client.api.pods.PodManager`

Quick start (PyPI):

```bash
pip install k3s-client
```

Basic usage:

```python
from k3s_client.api.applications import ApplicationManager

manager = ApplicationManager(dry_run_by_default=True)

# Preview a runtime change without executing it
preview = manager.scale_to(msid="productpage", count=3)

# Execute for real
result = manager.scale_to(msid="productpage", count=3, dry_run=False)
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
- Kubernetes Python SDK (`kubernetes` package)

---

## Methods

All microservices are managed in the `default` namespace; there is no namespace parameter.

Class guide:
- Use `ApplicationManager` as the main entry point.

### `ApplicationManager`

| Method | Parameters | Description |
|--------|------------|-------------|
| `create_registry_secret` | `name`, `registry`, `username`, `password`, `email=None`, `replace=True`, `dry_run=None` | Create a Docker registry pull secret |
| `apply_manifest` | `manifest_file`, `dry_run=None` | Apply a Kubernetes manifest |
| `delete_manifest` | `manifest_file`, `dry_run=None` | Delete resources defined in a manifest |
| `apply_tosca` | `tosca_file=None`, `tosca_content=None`, `image_pull_secret=None`, `acme_email=None`, `dry_run=False`, `output_manifest_file=None` | One-call flow: generate manifests from TOSCA and optionally apply with standardized output |
| `create_pod` | `msid`, `nodeid=None`, `dry_run=None` | Create a runtime pod through the runtime client  |
| `delete_pod` | `msid`, `podid=None`, `dry_run=None` | Delete a runtime pod through the runtime client |
| `scale_to` | `msid`, `count`, `dry_run=None` | Scale a deployment through the runtime client |
| `migrate_pod` | `msid`, `podid=None`, `nodeid=None`, `dry_run=None` | Migrate pod placement through the runtime client |
| `delete_microservice` | `app_label`, `dry_run=None` | Delete all resources for a given app label |
| `get_pod_node_mapping` | `label_selector=None`, `dry_run=None` | Return pod-to-node mapping by microservice |

Deployment model: apply workloads with `apply_manifest`, manage runtime scaling/placement with the runtime methods, and clean up with `delete_manifest`.

Runtime model: runtime operations update live cluster state and do not rewrite source YAML on disk. For Deployment-managed workloads, `create_pod(msid)` and `delete_pod(msid)` map to `+1` / `-1` scaling, `scale_to(msid, count)` sets exact replicas, and `migrate_pod(msid, podid, nodeid)` uses delete/recreate placement.

Field managers are intentionally separated: `tosca-controller` for generated manifest apply and `swarm-optimiser` for runtime pinned deployment apply. This avoids runtime placement changes being overwritten by later manifest re-apply operations.

### Dry Run (All `ApplicationManager` Methods)

All `ApplicationManager` methods support dry-run behavior.
If `dry_run` is omitted, the manager uses `dry_run_by_default`.
If `dry_run=True`, the call executes Kubernetes server-side dry-run (`dry_run="All"`) for write operations and does not persist changes.
If `dry_run=False`, the call executes normally.

Dry-run responses keep compatibility metadata (`mode`, `executed`, and `params`) and include `result` with the real API dry-run response payload.
`apply_tosca` additionally includes manifest summary fields (`manifest.file`, resource count, kind summary) and runs the apply step in server-side dry-run so `apply_response` and `result` are populated without persisting resources.

Return-shape note: non-dry-run write calls keep human-readable status strings in many paths, while dry-run returns structured API payloads in `result` (objects/lists, and aggregated details for multi-resource operations).

---

### `PodManager`

| Method | Parameters | Description |
|--------|------------|-------------|
| `list_pods` | `label_selector=None` | List pods, optionally filtered by label |

---

### `get_kubernetes_manifest`

| Function | Parameters | Description |
|----------|------------|-------------|
| `get_kubernetes_manifest` | `tosca_file=None`, `tosca_content=None`, `image_pull_secret=None`, `acme_email=None` | Generate Kubernetes manifests from a TOSCA definition |

Provide exactly one input source: `tosca_file` or `tosca_content`.
.

---

## Examples

Use these scripts from the `examples/` folder for end-to-end usage:

| Example script | Description |
|----------------|----------------------|
| `manifest_generator_example.py` | Generate Kubernetes manifests from a TOSCA input |
| `manifest_apply_example.py` | Apply an existing manifest file |
| `manifest_delete_example.py` | Delete resources from a manifest file |
| `apply_tosca_example.py` | Generate and apply from TOSCA in one flow |
| `scale_microservice_example.py` | Scale a microservice deployment |
| `pod_runtime_operations_example.py` | Create, delete, and migrate runtime pods |
| `registry_secret_example.py` | Create/update registry pull secrets |

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

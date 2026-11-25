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
preview = manager.scale_to(msid="web", count=3)

# Execute for real
result = manager.scale_to(msid="web", count=3, dry_run=False)
```

---

## Features

- **Registry Secret Management**: Create and rotate Docker registry secrets for private image pulls
- **Microservice Scaling**: Scale deployments and manipulate pods for optimizer workflows
- **Manifest Generation**: Generate Kubernetes manifests from TOSCA definitions
- **Pod Mapping**: Query pod-to-node mapping for placement decisions

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

| Method | Parameters | Description | Output |
|--------|------------|-------------|--------|
| `create_registry_secret` | `name`, `registry`, `username`, `password`, `email=None`, `replace=True`, `dry_run=None` | Create a Docker registry pull secret | `"Secret/my-secret configured"` |
| `apply_manifest` | `manifest_file`, `dry_run=None` | Apply a Kubernetes manifest | `"Deployment/web configured"` |
| `delete_manifest` | `manifest_file`, `dry_run=None` | Delete resources defined in a manifest | `"Deployment/web deleted"` |
| `apply_tosca` | `tosca_file=None`, `tosca_content=None`, `image_pull_secret=None`, `acme_email=None`, `dry_run=None`, `output_manifest_file=None` | Generate and apply manifests from TOSCA | `{"ok": True, "operation": "apply_tosca", "applied": True, "manifest": {"file": "/tmp/tmpabc.yaml", "resource_count": 1, "kind_summary": {"Deployment": 1}}, ...}` |
| `create_pod` | `msid`, `nodeid=None`, `dry_run=None` | Create a runtime pod or scale the Deployment | `{"ok": True, "operation": "create_pod", "nodeid": "edge-node-3", "deployment_name": "web-pinned-edge-node-3", ...}` (with `nodeid`) |
| `delete_pod` | `msid`, `podid=None`, `dry_run=None` | Delete a runtime pod or scale the Deployment | `{"ok": True, "operation": "delete_pod", "podid": None, "scaled_to": 1, ...}` |
| `scale_to` | `msid`, `count`, `dry_run=None` | Scale a deployment | `{"ok": True, "operation": "scale_to", "msid": "web", "count": 2, "result": "deployment/web scaled"}` |
| `migrate_pod` | `msid`, `podid=None`, `nodeid`, `dry_run=None` | Migrate pod placement; `nodeid` is required | `{"ok": True, "operation": "migrate_pod", "podid": "web-abc12", "nodeid": "edge-node-3", "result": {"deployment_name": "web-pinned-edge-node-3", ...}, ...}` |
| `get_pod_node_mapping` | `label_selector=None`, `dry_run=None` | Return pod-to-node mapping by microservice | `{"web": {"web-abc12": "edge-node-1", "web-def34": "edge-node-2", "web-ghi56": None}}` |

Pinned placement: for `create_pod()` and `migrate_pod()`, `nodeid` is the target node's `labels.swarmchestrate.eu/resource_name` value (underscores become hyphens). Before any change, the client checks that the node is Ready and matches the SAT labels, and raises `K3sClientError` otherwise.

Outputs shown are examples of non-dry-run calls; `...` indicates omitted fields. In the mapping, values are Kubernetes node names and `None` means the pod is unassigned. See [Dry Run](#dry-run-all-applicationmanager-methods) for dry-run response shapes.

When normalization changes the supplied node ID, pinned placement responses include the original as `requested_nodeid`. A successful apply does not guarantee that the new pod has been scheduled.

Deployment model: apply workloads with `apply_manifest`, manage runtime scaling/placement with the runtime methods, and clean up with `delete_manifest`.

Runtime model: runtime operations update live cluster state and do not rewrite source YAML on disk. For Deployment-managed workloads, `create_pod(msid)` and `delete_pod(msid)` map to `+1` / `-1` scaling, `scale_to(msid, count)` sets exact replicas, and `migrate_pod(msid, podid, nodeid)` uses delete/recreate placement.

Field managers are intentionally separated: `tosca-controller` for generated manifest apply and `swarm-optimiser` for runtime pinned deployment apply. This avoids runtime placement changes being overwritten by later manifest re-apply operations.

### Dry Run (All `ApplicationManager` Methods)

If `dry_run` is omitted, the manager uses `dry_run_by_default`.
With `dry_run=True`, write operations use Kubernetes server-side dry-run and save nothing.
Dry-run responses return their results in `result`.

---

### `PodManager`

| Method | Parameters | Description | Output |
|--------|------------|-------------|--------|
| `list_nodes` | `label_selector=None` | List cluster nodes, optionally filtered by label | `[{"metadata": {"name": "edge-node-1", ...}, ...}]` |

---

### `get_kubernetes_manifest`

| Function | Parameters | Description | Output |
|----------|------------|-------------|--------|
| `get_kubernetes_manifest` | `tosca_file=None`, `tosca_content=None`, `image_pull_secret=None`, `acme_email=None` | Generate Kubernetes manifests from a TOSCA definition | `[{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "web-v1"}, ...}]` |

Provide exactly one input source: `tosca_file` or `tosca_content`.

---

## Examples

Use these scripts from the `examples/` folder for end-to-end usage:

Most examples assume in-cluster execution by default so they can run unchanged inside the Swarm Agent pod. For local development, pass `kubeconfig_path` explicitly.

| Example script | Description |
|----------------|----------------------|
| `manifest_generator_example.py` | Generate Kubernetes manifests from a TOSCA input |
| `manifest_apply_example.py` | Apply an existing manifest file |
| `manifest_delete_example.py` | Delete resources from a manifest file |
| `apply_tosca_example.py` | Generate and apply from TOSCA in one flow |
| `list_nodes_example.py` | List cluster nodes, optionally filtered by label |
| `pod_node_mapping_example.py` | Retrieve pod-to-node mappings grouped by microservice |
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

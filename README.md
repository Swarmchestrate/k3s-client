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
| `create_registry_secret` | `name`, `registry`, `username`, `password`, `email=None`, `namespace=None`, `replace=True`, `dry_run=None` | Create a Docker registry pull secret |
| `apply_manifest` | `manifest_file`, `namespace=None`, `dry_run=None` | Apply a Kubernetes manifest |
| `delete_manifest` | `manifest_file`, `dry_run=None` | Delete resources defined in a manifest |
| `apply_tosca` | `tosca_file=None`, `tosca_content=None`, `namespace=None`, `image_pull_secret=None`, `acme_email=None`, `dry_run=False`, `output_manifest_file=None` | One-call flow: generate manifests from TOSCA and optionally apply with standardized output |
| `create_pod` | `msid`, `nodeid=None`, `namespace=None`, `dry_run=None` | Create one pod for a microservice |
| `delete_pod` | `msid`, `podid=None`, `namespace=None`, `dry_run=None` | Delete one pod for a microservice |
| `scale_to` | `msid`, `count`, `namespace=None`, `dry_run=None` | Scale a microservice to exact replica count |
| `migrate_pod` | `msid`, `podid=None`, `nodeid=None`, `namespace=None`, `dry_run=None` | Move a pod to another node |
| `delete_microservice` | `app_label`, `namespace=None`, `dry_run=None` | Delete all resources for a given app label |
| `get_pod_node_mapping` | `namespace=None`, `label_selector=None`, `dry_run=None` | Return pod-to-node mapping by microservice |

Deployment model:
1. Deploy applications using `apply_manifest`.
2. Perform runtime pod operations (`create_pod`, `delete_pod`, `scale_to`, `migrate_pod`) on workloads created by that manifest.
3. Remove applications using `delete_manifest`.

Runtime behavior and limitations:
1. Pod operations update live cluster state, not the original YAML file on disk.
2. Manifest re-apply uses server-side apply with a field manager, so runtime-managed fields are less likely to be clobbered by a later reapply.
3. For Deployment-managed microservices, `create_pod(msid)` and `delete_pod(msid)` should be read as scale `+1` and scale `-1`; `scale_to(msid, count)` is the most direct exact-replica operation.
4. Deleting a specific pod from a Deployment without also adjusting desired replicas will cause Kubernetes to create a replacement pod.
5. Creating a pod on a specific node or migrating a pod to another node is not a native in-place Deployment action in Kubernetes. Those operations depend on the swarm-agent implementation recreating or cloning workload instances with the requested placement.
6. `migrate_pod` should be treated as an ordered recreate flow on the target node, not as moving a running pod between nodes.
7. Runtime changes affect the live workload in the cluster, but they do not rewrite the source manifest file that was originally applied.

Notes:
1. For pod-level methods, `msid` should match the deployed microservice/deployment name from the applied manifest.
2. For one-call TOSCA generate/apply workflow, see [examples/apply_tosca_example.py](examples/apply_tosca_example.py).
3. For pod-to-node mapping usage, see [examples/pod_node_mapping_example.py](examples/pod_node_mapping_example.py).

### Dry Run (All `ApplicationManager` Methods)

All `ApplicationManager` methods support dry-run behavior.

Dry-run rules:
1. If `dry_run` is omitted on a method call, `dry_run_by_default` from initialization is used.
2. If `dry_run=True`, the method returns a preview response and does not execute the swarm-agent action.
3. If `dry_run=False`, the method executes normally.

1. Dry run by default at initialization

```python
from k3s_client.api.applications import ApplicationManager

manager = ApplicationManager(dry_run_by_default=True)

# Dry-run by default for any method
preview = manager.create_pod(msid="productpage", namespace="default")
```

2. Per-method override

```python
from k3s_client.api.applications import ApplicationManager

manager = ApplicationManager(dry_run_by_default=True)

# Force execution for this call only
result = manager.create_pod(
    msid="productpage",
    namespace="default",
    dry_run=False,
)
```

`apply_tosca` dry-run response includes generation details such as:

- `ok`: operation success flag
- `mode`: `"dry-run"` or `"apply"`
- `manifest.file`: generated manifest file path
- `manifest.resource_count`: number of rendered resources
- `manifest.kind_summary`: resource count by Kubernetes kind
- `applied`: whether apply was executed
- `agent_response`: swarm-agent response when apply runs

For other methods, dry-run responses include:

- `ok`: operation success flag
- `operation`: method operation name
- `mode`: `"dry-run"`
- `executed`: `False`
- `params`: the request payload that would be sent

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
| `pod_runtime_operations_example.py` | Apply manifest first, then run `create_pod` / `delete_pod` / `scale_to` runtime operations |
| `optimizer_actions_example.py` | Execute an ordered optimizer action list (`create_pod`, `delete_pod`, `scale_to`) |
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

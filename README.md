# k3s-client

A lightweight Python client for managing microservices on Kubernetes k3s clusters. Provides a clean API layer for deploying applications, managing secrets and ConfigMaps, generating Kubernetes manifests from TOSCA definitions, and performing node-aware scheduling operations.

---

## Features

- **Registry Secret Management** — Create and rotate Docker registry secrets for private image pulls
- **ConfigMap Management** — Create ConfigMaps from literals or files
- **Microservice Lifecycle** — Scale, update images, migrate nodes, and delete microservices
- **Manifest Generation** — Generate Kubernetes manifests from TOSCA definitions
- **Node-Aware Scheduling** — Migrate microservices across nodes using label-based selectors
- **Pod Management** — List and launch pods with node affinity support
- **Kubectl Wrapper** — Declarative apply and delete via kubectl

---

## Prerequisites

- Python **3.12** or higher
- A running **k3s** cluster with a valid kubeconfig (default: `~/.kube/config`)
- `kubectl` installed and accessible on `$PATH`

---

## Installation

```bash
git clone https://github.com/Swarmchestrate/k3s-client.git
cd k3s-client
make install
```

This will install all dependencies and the Puccini TOSCA parser required for manifest generation.


## Methods

### `ApplicationManager` — `k3s_client.api.applications`

| Method | Parameters | Description |
|--------|------------|-------------|
| `create_registry_secret` | `name`, `registry`, `username`, `password`, `namespace=None`, `replace=True` | Create a Docker registry pull secret |
| `create_configmap` | `name`, `namespace=None`, `from_literal=None`, `from_file=None` | Create a ConfigMap from literals or files |
| `apply_manifest` | `manifest_file`, `namespace=None` | Apply a Kubernetes manifest via kubectl |
| `delete_manifest` | `manifest_file` | Delete resources defined in a manifest |
| `scale_microservice` | `deployment_name`, `replicas`, `namespace=None` | Scale a deployment |
| `update_microservice_image` | `deployment_name`, `container_name`, `new_image`, `namespace=None` | Update a container image in-place |
| `migrate_microservice_node` | `deployment_name`, `node_selector`, `namespace=None` | Migrate a deployment to a different node |
| `delete_microservice` | `app_label`, `namespace=None` | Delete all resources for a given app label |
| `get_pod_node_mapping` | `namespace=None`, `label_selector=None` | Return a mapping of pod names to node names |

---

### `PodManager` — `k3s_client.api.pods`

| Method | Parameters | Description |
|--------|------------|-------------|
| `list_pods` | `namespace=None`, `label_selector=None` | List pods, optionally filtered by label |
| `launch_pod` | `name`, `image`, `pod_labels=None`, `node_labels=None`, `node_name=None`, `namespace=None`, `container_port=None` | Launch a pod with optional node affinity |

---

### `get_kubernetes_manifest` — `k3s_client.utils.manifest`

| Function | Parameters | Description |
|----------|------------|-------------|
| `get_kubernetes_manifest` | `tosca_yaml`, `image_pull_secret=None` | Generate Kubernetes manifests from a TOSCA definition |

---

### `Kubectl` — `k3s_client.cli.kubectl`

| Method | Parameters | Description |
|--------|------------|-------------|
| `apply` | `manifest_path=None`, `configmap_name=None`, `namespace=None`, `from_literal=None`, `from_file=None` | Apply resources declaratively |
| `delete` | `manifest_path` | Delete resources from a manifest |

---

## Examples

The `examples/` directory contains complete runnable scripts:

| File | Description |
|------|-------------|
| `registry_secret_example.py` | Managing Docker registry secrets |
| `configmap_example.py` | Creating ConfigMaps from literals and files |
| `manifest_example.py` | Generating and applying manifests |
| `microservice_example.py` | Scaling, migrating, and updating microservices |

Run any example:

```bash
python examples/microservice_example.py
```

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

For questions or feedback: [G.Kotak@westminster.ac.uk](mailto:G.Kotak@westminster.ac.uk)
import base64
import logging
import json
from kubernetes import client
from kubernetes.client.rest import ApiException
from k3s_client.exceptions import K3sClientError
from k3s_client.utils.kubeconfig import load_kubeconfig
from k3s_client.cli.kubectl import Kubectl

logger = logging.getLogger(__name__)

def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except K3sClientError:
            raise
        except Exception as e:
            logger.exception("Error in %s", func.__name__)
            raise K3sClientError(str(e))
    return wrapper


class ApplicationManager:
    """Manage applications (Deployments, Services, ConfigMaps) via manifests and registry secrets."""

    @handle_errors
    def __init__(self, kubeconfig_path=None, use_kubectl=True, default_namespace=None):
        load_kubeconfig(kubeconfig_path)
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.kubectl = Kubectl(kubeconfig=kubeconfig_path, use_kubectl=use_kubectl)
        self.manifest_registry = {} 
        self.default_namespace = default_namespace or "default"
        logger.info("Initialized ApplicationManager with namespace=%s", self.default_namespace)

    # --------------------
    # Manifest management
    # --------------------
    @handle_errors
    def apply_manifest(self, manifest_file: str, namespace: str = None):
        namespace = namespace or self.default_namespace
        logger.info("Applying manifest %s to namespace %s", manifest_file, namespace)
        output = self.kubectl.apply_manifest(manifest_path=manifest_file)
        self.manifest_registry[manifest_file] = {"type": "manifest", "namespace": namespace}
        return output

    @handle_errors
    def delete_manifest(self, manifest_file: str):
        if manifest_file in self.manifest_registry:
            logger.info("Deleting manifest %s", manifest_file)
            output = self.kubectl.delete(manifest_file)
            del self.manifest_registry[manifest_file]
            return output
        raise K3sClientError(f"Manifest {manifest_file} not found in registry")

    # --------------------
    # ConfigMap management
    # --------------------
    @handle_errors
    def create_configmap(self, name, namespace=None, from_literal=None, from_file=None):
        namespace = namespace or self.default_namespace
        logger.info("Creating ConfigMap %s in namespace %s", name, namespace)
        output = self.kubectl.create_configmap(
            name=name,
            namespace=namespace,
            from_literal=from_literal,
            from_file=from_file,
        )
        return output

    @handle_errors
    def delete_configmap(self, name, namespace=None):
        namespace = namespace or self.default_namespace
        logger.info("Deleting ConfigMap %s in namespace %s", name, namespace)
        return self.kubectl.delete(name, namespace=namespace, resource_type="configmap")

    # --------------------
    # Registry secret management
    # --------------------
    @handle_errors
    def create_registry_secret(
        self,
        name: str,
        registry: str,
        username: str,
        password: str,
        email: str = None,
        namespace: str = None,
        replace: bool = True,
    ):
        """Create/update registry secret from credential fields."""
        namespace = namespace or self.default_namespace
        if not registry or not username or not password:
            raise ValueError("registry, username and password are required")

        auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
        dockerconfig = {
            "auths": {
                registry: {
                    "username": username,
                    "password": password,
                    "email": email,
                    "auth": auth,
                }
            }
        }

        dockerconfig_payload = json.dumps(dockerconfig)
        secret_data = {
            ".dockerconfigjson": base64.b64encode(dockerconfig_payload.encode("utf-8")).decode("utf-8")
        }

        secret_body = client.V1Secret(
            metadata=client.V1ObjectMeta(name=name),
            type="kubernetes.io/dockerconfigjson",
            data=secret_data,
        )

        try:
            self.v1.create_namespaced_secret(namespace=namespace, body=secret_body)
            logger.info("Registry secret %s created in %s", name, namespace)
            return f"Registry secret {name} created in {namespace}"
        except ApiException as e:
            if e.status == 409 and replace:
                self.v1.replace_namespaced_secret(name=name, namespace=namespace, body=secret_body)
                logger.info("Registry secret %s updated in %s", name, namespace)
                return f"Registry secret {name} updated in {namespace}"
            raise

    @handle_errors
    def scale_microservice(self, deployment_name, replicas, namespace=None):
        """Scale a microservice up or down."""
        namespace = namespace or "default"
        logger.info("Scaling microservice %s to %d replicas in namespace %s", deployment_name, replicas, namespace)
        patch = {"spec": {"replicas": replicas}}
        return self.apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch)

    @handle_errors
    def delete_microservice(self, app_label, namespace=None):
        namespace = namespace or self.default_namespace
        logger.info("Deleting microservice with app label %s in namespace %s", app_label, namespace)

        # Delete deployments
        deployments = self.apps_v1.list_namespaced_deployment(namespace, label_selector=f"app={app_label}")
        for dep in deployments.items:
            logger.info("Deleting deployment %s", dep.metadata.name)
            self.apps_v1.delete_namespaced_deployment(dep.metadata.name, namespace)

        # Delete services
        services = self.v1.list_namespaced_service(namespace, label_selector=f"app={app_label}")
        for svc in services.items:
            logger.info("Deleting service %s", svc.metadata.name)
            self.v1.delete_namespaced_service(svc.metadata.name, namespace)

        return f"Deleted deployments and services for app={app_label}"

    @handle_errors
    def update_microservice_image(self, deployment_name, container_name, new_image, namespace=None):
        """Update the image of a container in a deployment."""
        namespace = namespace or self.default_namespace
        logger.info("Updating image of container %s in deployment %s to %s", container_name, deployment_name, new_image)
        
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {"name": container_name, "image": new_image}
                        ]
                    }
                }
            }
        }
        return self.apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch)

    @handle_errors
    def migrate_microservice_node(self, deployment_name, node_selector, namespace=None):
        """Migrate microservice to nodes matching a new nodeSelector."""
        namespace = namespace or self.default_namespace
        logger.info("Migrating microservice %s to nodeSelector %s", deployment_name, node_selector)
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "nodeSelector": node_selector
                    }
                }
            }
        }
        return self.apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch)

    @handle_errors
    def get_pod_node_mapping(self, namespace=None, label_selector=None):
        """Get mapping of pod names to node names for monitoring deployed microservices."""
        namespace = namespace or self.default_namespace
        pods = self.v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        mapping = {}
        for pod in pods.items:
            pod_name = pod.metadata.name
            node_name = pod.spec.node_name if pod.spec.node_name else "Not scheduled"
            mapping[pod_name] = node_name
        logger.info("Retrieved pod-node mapping for %d pods in namespace %s", len(mapping), namespace)
        return mapping
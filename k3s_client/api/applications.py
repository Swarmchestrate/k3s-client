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
        logger.info(
            "Initialized ApplicationManager with namespace=%s", self.default_namespace
        )

    # --------------------
    # Manifest management
    # --------------------
    @handle_errors
    def apply_manifest(self, manifest_file: str, namespace: str = None):
        namespace = namespace or self.default_namespace
        logger.info("Applying manifest %s to namespace %s", manifest_file, namespace)
        output = self.kubectl.apply_manifest(manifest_path=manifest_file)
        self.manifest_registry[manifest_file] = {
            "type": "manifest",
            "namespace": namespace,
        }
        return output

    @handle_errors
    def delete_manifest(self, manifest_file: str):
        if manifest_file in self.manifest_registry:
            logger.info("Deleting manifest %s", manifest_file)
            output = self.kubectl.delete(manifest_file)
            del self.manifest_registry[manifest_file]
            return output

        logger.warning(
            "Manifest %s not found in registry; deleting directly from manifest file",
            manifest_file,
        )
        return self.kubectl.delete(manifest_file)

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

        auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode(
            "utf-8"
        )
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
            ".dockerconfigjson": base64.b64encode(
                dockerconfig_payload.encode("utf-8")
            ).decode("utf-8")
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
                self.v1.replace_namespaced_secret(
                    name=name, namespace=namespace, body=secret_body
                )
                logger.info("Registry secret %s updated in %s", name, namespace)
                return f"Registry secret {name} updated in {namespace}"
            raise

    @handle_errors
    def scale_microservice(self, deployment_name, replicas, namespace=None):
        """Scale a microservice up or down."""
        namespace = namespace or "default"
        logger.info(
            "Scaling microservice %s to %d replicas in namespace %s",
            deployment_name,
            replicas,
            namespace,
        )
        patch = {"spec": {"replicas": replicas}}
        return self.apps_v1.patch_namespaced_deployment(
            name=deployment_name, namespace=namespace, body=patch
        )

    @handle_errors
    def create_microservice(
        self,
        deployment_name,
        image,
        container_name="app",
        replicas=1,
        namespace=None,
        labels=None,
        env=None,
        ports=None,
        node_selector=None,
        service_type="ClusterIP",
    ):
        """Create a new microservice deployment and optional service."""
        namespace = namespace or self.default_namespace
        labels = labels or {"app": deployment_name}
        logger.info(
            "Creating microservice %s in namespace %s",
            deployment_name,
            namespace,
        )

        env_vars = [
            client.V1EnvVar(name=name, value=str(value))
            for name, value in (env or {}).items()
        ]

        container_ports = []
        service_ports = []
        for port in ports or []:
            if isinstance(port, int):
                port_context = {"port": port, "targetPort": port}
            else:
                port_context = port

            service_port = int(port_context.get("port", 0))
            target_port = int(port_context.get("targetPort", service_port))
            protocol = str(port_context.get("protocol", "TCP")).upper()
            node_port = port_context.get("nodePort")

            container_ports.append(
                client.V1ContainerPort(
                    container_port=target_port,
                    protocol=protocol,
                )
            )

            service_port_obj = client.V1ServicePort(
                name=f"port-{service_port}",
                port=service_port,
                target_port=target_port,
                protocol=protocol,
            )
            if node_port is not None:
                service_port_obj.node_port = int(node_port)
            service_ports.append(service_port_obj)

        container = client.V1Container(
            name=container_name,
            image=image,
            ports=container_ports or None,
            env=env_vars or None,
        )

        pod_spec = client.V1PodSpec(
            containers=[container],
            node_selector=node_selector or None,
        )

        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=pod_spec,
        )

        deployment_spec = client.V1DeploymentSpec(
            replicas=replicas,
            selector=client.V1LabelSelector(match_labels=labels),
            template=template,
        )

        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(name=deployment_name, labels=labels),
            spec=deployment_spec,
        )

        self.apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment)
        logger.info("Deployment %s created in %s", deployment_name, namespace)

        result = [f"Deployment {deployment_name} created in {namespace}"]

        if service_ports:
            service_spec = client.V1ServiceSpec(
                type=service_type,
                selector=labels,
                ports=service_ports,
            )
            service = client.V1Service(
                metadata=client.V1ObjectMeta(name=deployment_name, labels=labels),
                spec=service_spec,
            )
            self.v1.create_namespaced_service(namespace=namespace, body=service)
            logger.info("Service %s created in %s", deployment_name, namespace)
            result.append(f"Service {deployment_name} created in {namespace}")

        return "\n".join(result)

    @handle_errors
    def delete_microservice(self, app_label, namespace=None):
        namespace = namespace or self.default_namespace
        logger.info(
            "Deleting microservice with app label %s in namespace %s",
            app_label,
            namespace,
        )

        if isinstance(app_label, str) and "=" in app_label:
            label_selector = app_label
        else:
            label_selector = f"app={app_label}"

        deleted_deployments = 0
        deleted_services = 0

        # Delete deployments by label selector
        deployments = self.apps_v1.list_namespaced_deployment(
            namespace, label_selector=label_selector
        )
        for dep in deployments.items:
            logger.info("Deleting deployment %s", dep.metadata.name)
            self.apps_v1.delete_namespaced_deployment(dep.metadata.name, namespace)
            deleted_deployments += 1

        # If no deployment matched and app_label looks like a deployment name, try deleting by name
        if deleted_deployments == 0 and "=" not in app_label:
            try:
                self.apps_v1.delete_namespaced_deployment(app_label, namespace)
                logger.info("Deleting deployment by name %s", app_label)
                deleted_deployments += 1
            except ApiException as exc:
                if exc.status != 404:
                    raise

        # Delete services by label selector
        services = self.v1.list_namespaced_service(
            namespace, label_selector=label_selector
        )
        for svc in services.items:
            logger.info("Deleting service %s", svc.metadata.name)
            self.v1.delete_namespaced_service(svc.metadata.name, namespace)
            deleted_services += 1

        # If no service matched and app_label looks like a service name, try deleting by name
        if deleted_services == 0 and "=" not in app_label:
            try:
                self.v1.delete_namespaced_service(app_label, namespace)
                logger.info("Deleting service by name %s", app_label)
                deleted_services += 1
            except ApiException as exc:
                if exc.status != 404:
                    raise

        return f"Deleted {deleted_deployments} deployments and {deleted_services} services for {app_label}"

    @handle_errors
    def update_microservice_image(
        self, deployment_name, container_name, new_image, namespace=None
    ):
        """Update the image of a container in a deployment."""
        namespace = namespace or self.default_namespace
        logger.info(
            "Updating image of container %s in deployment %s to %s",
            container_name,
            deployment_name,
            new_image,
        )

        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{"name": container_name, "image": new_image}]
                    }
                }
            }
        }
        return self.apps_v1.patch_namespaced_deployment(
            name=deployment_name, namespace=namespace, body=patch
        )

    @handle_errors
    def migrate_microservice_node(self, deployment_name, node_selector, namespace=None):
        """Migrate microservice to nodes matching a new nodeSelector."""
        namespace = namespace or self.default_namespace
        logger.info(
            "Migrating microservice %s to nodeSelector %s",
            deployment_name,
            node_selector,
        )
        patch = {"spec": {"template": {"spec": {"nodeSelector": node_selector}}}}
        return self.apps_v1.patch_namespaced_deployment(
            name=deployment_name, namespace=namespace, body=patch
        )

    @handle_errors
    def get_pod_node_mapping(self, namespace=None, label_selector=None):
        """Get mapping of pod names to node names for monitoring deployed microservices."""
        namespace = namespace or self.default_namespace
        pods = self.v1.list_namespaced_pod(
            namespace=namespace, label_selector=label_selector
        )
        mapping = {}
        for pod in pods.items:
            pod_name = pod.metadata.name
            node_name = pod.spec.node_name if pod.spec.node_name else "Not scheduled"
            mapping[pod_name] = node_name
        logger.info(
            "Retrieved pod-node mapping for %d pods in namespace %s",
            len(mapping),
            namespace,
        )
        return mapping

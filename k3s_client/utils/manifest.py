import json
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from ruamel.yaml import YAML
from sardou import Sardou

yaml = YAML()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
jinja_env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)

def _load_tosca(
    *,
    tosca_file: Optional[str] = None,
    tosca_content: Optional[str] = None,
) -> str:
    if tosca_file:
        path = Path(tosca_file)
        if not path.is_file():
            raise FileNotFoundError(f"TOSCA file not found: {tosca_file}")
        return path.read_text(encoding="utf-8")

    if tosca_content:
        return tosca_content

    raise ValueError("Provide either tosca_file or tosca_content")

def _render_yaml(template_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
    template = jinja_env.get_template(template_name)
    rendered = template.render(**context)
    return yaml.load(StringIO(rendered))


def get_kubernetes_manifest(
    *,
    tosca_file: Optional[str] = None,
    tosca_content: Optional[str] = None,
    image_pull_secret: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Generate Kubernetes manifests from TOSCA (file or content)."""
    tosca_str = _load_tosca(tosca_file=tosca_file, tosca_content=tosca_content)
    tosca = Sardou(tosca_str)

    node_templates = (
        tosca.raw._to_dict().get("service_template", {}).get("node_templates", {}) or {}
    )
    if not node_templates:
        raise ValueError("No node_templates found in TOSCA YAML")

    manifests: List[Dict[str, Any]] = []
    service_groups: Dict[str, Dict[str, Any]] = {}

    for name, node in node_templates.items():
        try:
            k3s_name = name.replace("_", "-")
            node_type = node.get("type", "")
            if not node_type.endswith("Microservice"):
                continue

            props = node.get("properties", {}) or {}
            # requirements = node.get("requirements", []) or []

            image = props.get("image")
            if not image:
                raise ValueError(f"{name}: missing image")

            env_list = [
                {"name": str(e["name"]), "value": str(e.get("value", ""))}
                for e in (props.get("env", []) or [])
                if isinstance(e, dict) and "name" in e
            ]

            # container ports
            container_ports = []
            service_ports = []
            for p in (props.get("ports", []) or []):
                container_port = int(p.get("containerPort") or p.get("targetPort") or p.get("port"))
                target_port = int(p.get("targetPort") or container_port)
                service_port = int(p.get("port") or target_port)
                protocol = str(p.get("protocol", "TCP")).upper()
                node_port = p.get("nodePort")

                container_ports.append({"containerPort": container_port, "protocol": protocol})
                sp = {"name": f"port-{service_port}", "port": service_port, "targetPort": target_port, "protocol": protocol}
                if node_port:
                    sp["nodePort"] = int(node_port)
                service_ports.append(sp)

            # volumes
            volumes = props.get("volumes", []) or []
            volume_mounts = props.get("volume_mounts", []) or []

            # labels
            labels = props.get("labels", {}) or {}
            app_name = labels.get("app")
            if not app_name:
                raise ValueError(f"{name}: 'app' label is required")

            # deployment context
            deployment_context = {
                "name": k3s_name,
                "replicas": int(props.get("replicas", 1)),
                "image": image,
                "args": props.get("args", []),
                "env_list": env_list,
                "container_ports": container_ports,
                "volume_mounts": volume_mounts,
                "volumes": volumes,
                "labels": labels,
                "pod_labels": props.get("pod_labels", {}),
                "pod_annotations": props.get("pod_annotations", {}),
                "image_pull_secret": image_pull_secret,
                "security_context": props.get("security_context", {}),
                "container_security_context": props.get("container_security_context", {}),
                "liveness_probe": props.get("liveness_probe", {}),
                "readiness_probe": props.get("readiness_probe", {}),
                "startup_probe": props.get("startup_probe", {}),
                "lifecycle": props.get("lifecycle", {}),
                "termination_grace_period_seconds": props.get("termination_grace_period_seconds"),
                "affinity": props.get("affinity", {}),
                "tolerations": props.get("tolerations", []),
                "topology_spread_constraints": props.get("topology_spread_constraints", []),
                "priority_class_name": props.get("priority_class_name"),
                "dns_policy": props.get("dns_policy"),
                "dns_config": props.get("dns_config", {}),
                "resources": props.get("resources", {}),
            }

            manifests.append(_render_yaml("deployment.yaml.j2", deployment_context))

            # group services by app
            group = service_groups.setdefault(app_name, {"ports": [], "selector": {"app": app_name}, "type": "ClusterIP"})
            for sp in service_ports:
                if sp not in group["ports"]:
                    group["ports"].append(sp)
            if any("nodePort" in p for p in group["ports"]):
                group["type"] = "NodePort"

        except Exception as e:
            print(f"Skipping node '{name}' due to error: {e}")
            continue

    # generate service manifests
    for app_name, svc in service_groups.items():
        svc_context = {
            "name": app_name,
            "type": svc["type"],
            "ports": svc["ports"],
            "selector_app": svc["selector"]["app"],
        }
        manifests.append(_render_yaml("service.yaml.j2", svc_context))

    return manifests
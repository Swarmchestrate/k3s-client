import json
import re
from pathlib import Path
from io import StringIO
from typing import Any, Dict, Optional, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from ruamel.yaml import YAML
from sardou import Sardou

yaml = YAML()
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
jinja_env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)


def _render_yaml(template_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
    template = jinja_env.get_template(template_name)
    rendered = template.render(**context)
    return yaml.load(StringIO(rendered))


def get_kubernetes_manifest(
    *,
    tosca_file: Optional[str] = None,
    tosca_content: Optional[str] = None,
    image_pull_secret: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if tosca_file:
        tosca_content = Path(tosca_file).read_text(encoding="utf-8")
    elif not tosca_content:
        raise ValueError("Provide either tosca_file or tosca_content")

    tosca = Sardou(content=tosca_content)
    node_templates = (
        tosca.raw._to_dict().get("service_template", {}).get("node_templates", {})
    )

    if not node_templates:
        raise ValueError("No node_templates found in TOSCA YAML")

    manifests: List[Dict[str, Any]] = []
    pending_services: Dict[str, Dict[str, Any]] = {}

    for name, node in node_templates.items():
        node_type = node.get("type", "")
        if not node_type.endswith("Microservice"):
            continue

        props = node.get("properties", {}) or {}
        image = props.get("image")
        if not image:
            continue

        # Version from labels is the source of truth
        labels = props.get("labels", {}) or {}
        version = labels.get("version") or props.get("version", "v1")
        app_name = labels.get("app") or name.replace("_", "-")

        # Strip trailing "-<version>" from node name to avoid duplication
        # e.g. node "details_v1" → k3s_name "details-v1" → base "details"
        k3s_name = name.replace("_", "-")
        k3s_name_base = re.sub(rf"-{re.escape(version)}$", "", k3s_name)

        replicas = int(props.get("replicas", 1))
        command = props.get("command", []) or []
        if isinstance(command, str):
            command = [command]
        args = props.get("args", []) or []
        env_list = [
            {"name": e["name"], "value": str(e.get("value", ""))}
            for e in (props.get("env") or [])
            if "name" in e
        ]

        # Ports — honour explicit containerPort field
        container_ports = []
        service_ports = []
        for p in props.get("ports", []) or []:
            port = int(p.get("port", 0))
            target = int(p.get("targetPort", port))
            container = int(p.get("containerPort", target))
            protocol = str(p.get("protocol", "TCP")).upper()
            node_port = p.get("nodePort")

            container_ports.append({"containerPort": container, "protocol": protocol})
            sp = {
                "name": f"port-{port}",
                "port": port,
                "targetPort": target,
                "protocol": protocol,
            }
            if node_port:
                sp["nodePort"] = int(node_port)
            service_ports.append(sp)

        # Volumes — normalise mount_path → mountPath, auto-fill emptyDir
        volume_mounts = [
            {
                "name": vm["name"],
                "mountPath": vm.get("mountPath") or vm.get("mount_path", ""),
            }
            for vm in (props.get("volume_mounts") or [])
        ]
        volumes = list(props.get("volumes") or [])
        declared_vol_names = {v["name"] for v in volumes}
        for vm in volume_mounts:
            if vm["name"] not in declared_vol_names:
                volumes.append({"name": vm["name"], "emptyDir": {}})

        deployment_context = {
            "name": k3s_name_base,
            "version": version,
            "replicas": replicas,
            "image": image,
            "command": command,
            "args": args,
            "env_list": env_list,
            "container_ports": container_ports,
            "volume_mounts": volume_mounts,
            "volumes": volumes,
            "labels": labels,
            "annotations": props.get("annotations", {}),
            "node_selector": props.get("node_selector", {}),
            "service_account": props.get("service_account"),
            "image_pull_secret": image_pull_secret,
        }
        manifests.append(_render_yaml("deployment.yaml.j2", deployment_context))

        # One service per unique app_name — covers multi-version deployments
        if service_ports and app_name not in pending_services:
            svc_type = (
                "NodePort"
                if any("nodePort" in sp for sp in service_ports)
                else "ClusterIP"
            )
            pending_services[app_name] = {
                "name": app_name,
                "service_type": svc_type,
                "service_ports": service_ports,
                "selector": {"app": app_name},
            }
            # Emit all services after all deployments
    for svc_context in pending_services.values():
        manifests.append(_render_yaml("service.yaml.j2", svc_context))

    return manifests

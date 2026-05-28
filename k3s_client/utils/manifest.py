import json
import logging
import re
from pathlib import Path
from io import StringIO
from typing import Any, Dict, Optional, List

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    StrictUndefined,
    TemplateNotFound,
)
from ruamel.yaml import YAML
from sardou import Sardou

yaml = YAML()
logger = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_template_loaders = [FileSystemLoader(str(TEMPLATE_DIR))]
try:
    _template_loaders.append(PackageLoader("k3s_client", "templates"))
except Exception:
    # PackageLoader may fail in some source layouts; filesystem loader remains available.
    pass

jinja_env = Environment(
    loader=ChoiceLoader(_template_loaders),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
jinja_env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)


def _volume_name_from_path(path: str, index: int) -> str:
    base = re.sub(r"[^a-z0-9-]", "-", path.lower()).strip("-")
    base = re.sub(r"-+", "-", base)
    if not base:
        base = f"vol-{index}"
    if not base.startswith("vol-"):
        base = f"vol-{base}"
    return base[:63].rstrip("-")


def _name_token(value: Any, fallback: str = "v1") -> str:
    token = re.sub(r"[^a-z0-9-]", "-", str(value).lower()).strip("-")
    token = re.sub(r"-+", "-", token)
    return (token or fallback)[:63].rstrip("-")


def _label_by_semantic_key(labels: Dict[str, Any], semantic_key: str) -> Optional[str]:
    """Return a label value by semantic key, allowing namespaced keys.

    Examples for semantic_key="version":
    - version
    - com.swarmchestrate.version
    - swarmchestrate.eu/version
    """
    if semantic_key in labels and labels.get(semantic_key) is not None:
        return str(labels.get(semantic_key))

    pattern = re.compile(rf"(^|[./_-]){re.escape(semantic_key)}$")
    for key, value in labels.items():
        if value is None:
            continue
        if pattern.search(str(key)):
            return str(value)
    return None


def _render_yaml(template_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
    try:
        template = jinja_env.get_template(template_name)
    except TemplateNotFound as exc:
        logger.error(
            "Template '%s' not found. Filesystem template dir: %s",
            template_name,
            TEMPLATE_DIR.resolve(),
        )
        raise FileNotFoundError(
            f"Template '{template_name}' not found. Expected under {TEMPLATE_DIR.resolve()}"
        ) from exc
    rendered = template.render(**context)
    return yaml.load(StringIO(rendered))


def _read_tosca_file_content(tosca_file: str) -> str:
    input_path = Path(tosca_file).expanduser()
    logger.debug(
        "Reading TOSCA file",
        extra={
            "tosca_file": tosca_file,
            "expanded_path": str(input_path),
            "cwd": str(Path.cwd()),
        },
    )

    candidates = [input_path]
    if not input_path.is_absolute():
        candidates.append(Path.cwd() / input_path)
        candidates.append(Path(__file__).resolve().parents[2] / input_path)
    logger.debug("TOSCA file candidates: %s", [str(c) for c in candidates])

    resolved_path: Optional[Path] = None
    for candidate in candidates:
        if candidate.exists():
            resolved_path = candidate
            break

    if resolved_path is None:
        logger.error("TOSCA file not found: %s", tosca_file)
        raise FileNotFoundError(f"TOSCA file not found: {tosca_file}")
    if resolved_path.is_dir():
        logger.error("TOSCA path points to directory: %s", resolved_path)
        raise ValueError(f"Expected a TOSCA file path, got directory: {resolved_path}")

    try:
        logger.debug("Resolved TOSCA file path: %s", resolved_path)
        return resolved_path.read_text(encoding="utf-8")
    except PermissionError as exc:
        logger.error("Permission denied while reading TOSCA file: %s", resolved_path)
        raise PermissionError(
            f"Permission denied while reading TOSCA file: {resolved_path}"
        ) from exc


def get_kubernetes_manifest(
    *,
    tosca_file: Optional[str] = None,
    tosca_content: Optional[str] = None,
    image_pull_secret: Optional[str] = None,
) -> List[Dict[str, Any]]:
    logger.debug(
        "Generating Kubernetes manifest",
        extra={
            "has_tosca_file": bool(tosca_file),
            "has_tosca_content": bool(tosca_content),
            "image_pull_secret_set": bool(image_pull_secret),
        },
    )
    if tosca_file:
        tosca_content = _read_tosca_file_content(tosca_file)
    elif not tosca_content:
        raise ValueError("Provide either tosca_file or tosca_content")

    try:
        tosca_dict = yaml.load(StringIO(tosca_content))
        if not isinstance(tosca_dict, dict):
            raise ValueError("TOSCA content must parse into a mapping")
    except Exception as exc:
        logger.exception("Failed to parse TOSCA YAML content")
        raise ValueError(f"Invalid TOSCA content: {exc}") from exc

    logger.debug("YAML parse complete")
    logger.debug("Parsed TOSCA top-level keys: %s", sorted(tosca_dict.keys()))
    service_template = tosca_dict.get("service_template", {})
    if not service_template and "node_templates" in tosca_dict:
        service_template = tosca_dict
    logger.debug(
        "Parsed service_template keys: %s",
        sorted(service_template.keys()) if isinstance(service_template, dict) else [],
    )
    node_templates = service_template.get("node_templates", {})
    affinity_map = Sardou(content=tosca_content).get_affinity()
    logger.debug(
        "Parsed TOSCA service template",
        extra={"node_template_count": len(node_templates)},
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

        logger.debug("Rendering manifests for microservice node: %s", name)

        # Version/app/service precedence supports generic or namespaced labels.
        labels = props.get("labels", {}) or {}
        version = _label_by_semantic_key(labels, "version") or props.get(
            "version", "v1"
        )
        version = str(version)
        version_name = _name_token(version)

        app_name = (
            _label_by_semantic_key(labels, "app")
            or _label_by_semantic_key(labels, "service")
            or name.replace("_", "-")
        )
        service_name = _label_by_semantic_key(labels, "service") or app_name

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

        # Volumes — support both explicit k8s-style volume definitions and
        # TOSCA source/target entries.
        volume_mounts = []
        for vm in props.get("volume_mounts") or []:
            if not isinstance(vm, dict):
                continue
            mount_name = vm.get("name")
            if not mount_name:
                continue
            volume_mounts.append(
                {
                    "name": mount_name,
                    "mountPath": vm.get("mountPath") or vm.get("mount_path", ""),
                }
            )

        tosca_volumes = []
        for idx, v in enumerate((props.get("volumes") or []), start=1):
            if not isinstance(v, dict):
                continue
            source = v.get("source")
            target = v.get("target")
            if not source or not target:
                continue

            vol_name = _volume_name_from_path(str(source), idx)
            tosca_volumes.append(
                {
                    "name": vol_name,
                    "hostPath": {"path": str(source), "type": "DirectoryOrCreate"},
                }
            )
            read_only = str(v.get("read_only", "")).lower() == "true"
            mount = {"name": vol_name, "mountPath": str(target)}
            if read_only:
                mount["readOnly"] = True
            volume_mounts.append(mount)

        volumes = [
            v
            for v in (props.get("volumes") or [])
            if isinstance(v, dict) and v.get("name")
        ]
        volumes.extend(tosca_volumes)
        declared_vol_names = {v["name"] for v in volumes}
        for vm in volume_mounts:
            if vm["name"] not in declared_vol_names:
                volumes.append({"name": vm["name"], "emptyDir": {}})

        deployment_context = {
            "name": k3s_name_base,
            "version": version,
            "version_name": version_name,
            "replicas": replicas,
            "image": image,
            "command": command,
            "args": args,
            "env_list": env_list,
            "container_ports": container_ports,
            "volume_mounts": volume_mounts,
            "volumes": volumes,
            "labels": labels,
            "app_label": app_name,
            "service_label": service_name,
            "annotations": props.get("annotations", {}),
            "node_selector": props.get("node_selector", {}),
            "affinity": (
                {"nodeAffinity": affinity_map[name]} if name in affinity_map else None
            ),
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

    logger.info("Generated %d Kubernetes manifest objects", len(manifests))

    return manifests

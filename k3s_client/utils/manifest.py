import json
import logging
import re
from io import StringIO
from pathlib import Path, PurePosixPath
from typing import Any

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

from k3s_client.cli.kubectl import Kubectl

yaml = YAML()
logger = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
NODE_AFFINITY_LABEL_KEY = "labels.swarmchestrate.eu/ms_id"
DEFAULT_ACME_EMAIL = "admin@example.com"
TRAEFIK_ACME_RESOLVER_NAME = "le"
TRAEFIK_ACME_STORAGE_PATH = "/persistentdata/acme.json"
TRAEFIK_ACME_VOLUME_NAME = "traefik-data"
TRAEFIK_ACME_VOLUME_MOUNT_PATH = "/persistentdata"
TRAEFIK_ACME_PVC_NAMESPACE = "kube-system"
TRAEFIK_ACME_PVC_SIZE = "64Mi"
TRAEFIK_DEFAULT_INGRESS_CLASS = "traefik"
TRAEFIK_DEFAULT_HTTP_PATH = "/"
TRAEFIK_DEFAULT_PATH_TYPE = "Prefix"
TRAEFIK_DEFAULT_HTTP_ENTRYPOINT = "websecure"
TRAEFIK_TCP_DEFAULT_ENTRYPOINT = "websecure"
TRAEFIK_TCP_DEFAULT_PROTOCOL = "TCP"
TRAEFIK_TCP_DEFAULT_PASSTHROUGH = True
_template_loaders = [FileSystemLoader(str(TEMPLATE_DIR))]
try:
    _template_loaders.append(PackageLoader("k3s_client", "templates"))
except Exception as exc:  # noqa: BLE001
    # PackageLoader may fail in some source layouts; filesystem loader remains available.
    logger.debug("PackageLoader unavailable, using filesystem templates only: %s", exc)

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


def _infer_host_path_type(source: str, target: str, volume: dict[str, Any]) -> str:
    """Infer Kubernetes hostPath.type for source/target volume entries.

    Rules:
    - explicit type override wins (host_path_type/hostPathType/type)
    - source or target ending with "/" implies a directory
    - otherwise, if either path has a filename suffix (e.g. .ini), treat as file
    - fallback is directory for backward compatibility
    """
    explicit_type = (
        volume.get("host_path_type") or volume.get("hostPathType") or volume.get("type")
    )
    if explicit_type:
        return str(explicit_type)

    if source.endswith("/") or target.endswith("/"):
        return "DirectoryOrCreate"

    source_suffix = PurePosixPath(source).suffix
    target_suffix = PurePosixPath(target).suffix
    if source_suffix or target_suffix:
        return "FileOrCreate"

    return "DirectoryOrCreate"


def _name_token(value: Any, fallback: str = "v1") -> str:
    token = re.sub(r"[^a-z0-9-]", "-", str(value).lower()).strip("-")
    token = re.sub(r"-+", "-", token)
    return (token or fallback)[:63].rstrip("-")


def _parse_file_mode(mode: Any) -> int | None:
    """Parse a TOSCA File.mode (e.g. "0444") into a Kubernetes integer mode.

    Kubernetes expects file modes as base-10 integers representing the octal
    permission bits (e.g. 0444 -> 292). Modes are interpreted as octal first to
    match the conventional "0444" notation, falling back to decimal.
    """
    if mode is None:
        return None
    text = str(mode).strip()
    if not text:
        return None
    try:
        return int(text, 8)
    except ValueError:
        try:
            return int(text, 10)
        except ValueError:
            logger.warning("Ignoring unparseable File.mode value: %r", mode)
            return None


def _parse_bool(value: Any, default: bool) -> bool:
    """Parse loose boolean inputs commonly found in YAML/TOSCA properties."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False

    logger.warning(
        "Ignoring unparseable boolean value %r; using default=%s", value, default
    )
    return default


def _parse_traefik_tcp_routes(
    routes: Any,
    *,
    default_name: str,
    default_service_name: str,
    default_service_port: int,
) -> list[dict[str, Any]]:
    """Normalize optional Traefik IngressRouteTCP definitions.

    Supported route keys:
    - name
    - entry_points / entryPoints / entryPoint
    - protocol (only TCP is supported)
    - match OR host_sni / hostSNI
    - service_name / serviceName
    - service_port / servicePort / port
    - tls_passthrough / tlsPassthrough / passthrough
    """
    if routes is None:
        return []

    if not isinstance(routes, list):
        logger.warning("Ignoring non-list traefik_tcp_routes value: %r", routes)
        return []

    normalized: list[dict[str, Any]] = []
    for idx, route in enumerate(routes, start=1):
        if not isinstance(route, dict):
            logger.warning(
                "Ignoring non-mapping traefik_tcp_routes[%d] value: %r", idx, route
            )
            continue

        protocol = str(route.get("protocol", TRAEFIK_TCP_DEFAULT_PROTOCOL)).upper()
        if protocol != TRAEFIK_TCP_DEFAULT_PROTOCOL:
            logger.warning(
                "Ignoring traefik_tcp_routes[%d] with unsupported protocol: %r",
                idx,
                protocol,
            )
            continue

        entry_points = route.get(
            "entryPoints",
            route.get(
                "entry_points",
                route.get("entryPoint", [TRAEFIK_TCP_DEFAULT_ENTRYPOINT]),
            ),
        )
        if isinstance(entry_points, str):
            entry_points = [entry_points]
        if not isinstance(entry_points, list) or not entry_points:
            logger.warning(
                "Ignoring traefik_tcp_routes[%d] with invalid entryPoints: %r",
                idx,
                entry_points,
            )
            continue

        match = route.get("match")
        if not match:
            host_sni = route.get("hostSNI", route.get("host_sni"))
            if host_sni:
                match = f"HostSNI(`{host_sni}`)"

        if not match:
            logger.warning("Ignoring traefik_tcp_routes[%d] without match/hostSNI", idx)
            continue

        service_port = route.get(
            "servicePort",
            route.get("service_port", route.get("port", default_service_port)),
        )
        try:
            service_port = int(service_port)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring traefik_tcp_routes[%d] with invalid service port: %r",
                idx,
                service_port,
            )
            continue

        normalized.append(
            {
                "name": str(route.get("name") or f"{default_name}-passthrough"),
                "entry_points": [str(ep) for ep in entry_points],
                "match": str(match),
                "service_name": str(
                    route.get(
                        "serviceName", route.get("service_name", default_service_name)
                    )
                ),
                "service_port": service_port,
                "tls_passthrough": _parse_bool(
                    route.get(
                        "tlsPassthrough",
                        route.get("tls_passthrough", route.get("passthrough")),
                    ),
                    default=TRAEFIK_TCP_DEFAULT_PASSTHROUGH,
                ),
            }
        )

    return normalized


def _parse_ingress_definition(
    ingress: Any,
    *,
    default_name: str,
    default_service_name: str,
    default_service_port: int,
    default_acme_email: str,
) -> dict[str, Any] | None:
    """Normalize an optional Traefik-backed HTTP ingress definition."""
    if ingress is None:
        return None

    if not isinstance(ingress, dict):
        logger.warning("Ignoring non-mapping ingress value: %r", ingress)
        return None

    domain = ingress.get("domain", ingress.get("host"))
    if not domain:
        logger.warning("Ignoring ingress without domain/host: %r", ingress)
        return None

    service_port = ingress.get(
        "servicePort",
        ingress.get("service_port", ingress.get("port", default_service_port)),
    )
    try:
        service_port = int(service_port)
    except (TypeError, ValueError):
        logger.warning("Ignoring ingress with invalid service port: %r", service_port)
        return None

    path = str(
        ingress.get("path", ingress.get("pat", TRAEFIK_DEFAULT_HTTP_PATH))
        or TRAEFIK_DEFAULT_HTTP_PATH
    )
    annotations = dict(ingress.get("annotations") or {})
    entrypoint = str(
        ingress.get(
            "entryPoint", ingress.get("entrypoint", TRAEFIK_DEFAULT_HTTP_ENTRYPOINT)
        )
    )
    tls_enabled = _parse_bool(ingress.get("tls"), default=True)
    ingress_class_name = str(
        ingress.get(
            "ingressClassName", ingress.get("className", TRAEFIK_DEFAULT_INGRESS_CLASS)
        )
    )
    cert_resolver = str(
        ingress.get(
            "cert_resolver",
            ingress.get(
                "certResolver",
                ingress.get(
                    "resolver",
                    ingress.get("certresolver", TRAEFIK_ACME_RESOLVER_NAME),
                ),
            ),
        )
    )
    effective_acme_email = default_acme_email

    annotations.setdefault(
        "traefik.ingress.kubernetes.io/router.entrypoints", entrypoint
    )
    if tls_enabled:
        annotations.setdefault("traefik.ingress.kubernetes.io/router.tls", "true")
        annotations.setdefault(
            "traefik.ingress.kubernetes.io/router.tls.certresolver", cert_resolver
        )
        annotations.setdefault(
            "traefik.ingress.kubernetes.io/router.tls.domains.0.main", str(domain)
        )

    return {
        "name": str(ingress.get("name") or default_name),
        "domain": str(domain),
        "path": path,
        "path_type": str(
            ingress.get("pathType", ingress.get("path_type", TRAEFIK_DEFAULT_PATH_TYPE))
        ),
        "service_name": str(
            ingress.get(
                "serviceName", ingress.get("service_name", default_service_name)
            )
        ),
        "service_port": service_port,
        "annotations": annotations,
        "ingress_class_name": ingress_class_name,
        "tls_enabled": tls_enabled,
        "acme_email": effective_acme_email,
        "cert_resolver": cert_resolver,
    }


def _iter_volume_requirements(node: dict[str, Any]):
    """Yield (target_node, mount_path) for each AttachesTo 'volume' requirement.

    Microservices attach File/Volume node templates through a requirement named
    'volume' whose relationship carries the desired container path in the
    'mount_path' property.
    """
    for req in node.get("requirements", []) or []:
        if not isinstance(req, dict):
            continue
        for req_name, req_body in req.items():
            if req_name != "volume" or not isinstance(req_body, dict):
                continue
            target_node = req_body.get("node")
            mount_path = None
            relationship = req_body.get("relationship")
            if isinstance(relationship, dict):
                rel_props = relationship.get("properties") or {}
                mount_path = rel_props.get("mount_path")
            yield target_node, mount_path


def _label_by_semantic_key(labels: dict[str, Any], semantic_key: str) -> str | None:
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


def _render_yaml(template_name: str, context: dict[str, Any]) -> dict[str, Any]:
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


def _render_yaml_documents(
    template_name: str, context: dict[str, Any]
) -> list[dict[str, Any]]:
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
    return [doc for doc in yaml.load_all(StringIO(rendered)) if doc is not None]


def build_node_affinity(node_label_key: str, node_id: str) -> dict[str, Any]:
    """Build a hard nodeAffinity block pinning a pod to a single node."""
    return {
        "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [
                    {
                        "matchExpressions": [
                            {
                                "key": str(node_label_key),
                                "operator": "In",
                                "values": [str(node_id)],
                            }
                        ]
                    }
                ]
            }
        }
    }


def build_pinned_deployment_name(msid: str, node_id: str) -> str:
    """Build the stable name used for a node-pinned Deployment."""
    return f"{_name_token(msid)}-pinned-{_name_token(node_id)}"


def _deployment_context(
    *,
    name: str,
    version: str,
    image: str,
    command: list[str],
    args: list[str],
    env_list: list[dict[str, Any]],
    container_ports: list[dict[str, Any]],
    volume_mounts: list[dict[str, Any]],
    volumes: list[dict[str, Any]],
    labels: dict[str, Any],
    app_label: str,
    service_label: str,
    annotations: dict[str, Any],
    node_selector: dict[str, Any],
    affinity: dict[str, Any] | None,
    service_account: str | None,
    image_pull_secret: str | None,
    enable_service_links: bool,
) -> dict[str, Any]:
    version_name = _name_token(version)
    return {
        "name": name,
        "version": version,
        "version_name": version_name,
        "replicas": 1,
        "image": image,
        "command": command,
        "args": args,
        "env_list": env_list,
        "container_ports": container_ports,
        "volume_mounts": volume_mounts,
        "volumes": volumes,
        "labels": labels,
        "app_label": app_label,
        "service_label": service_label,
        "annotations": annotations,
        "node_selector": node_selector,
        "affinity": affinity,
        "service_account": service_account,
        "image_pull_secret": image_pull_secret,
        "enable_service_links": enable_service_links,
    }


def _deployment_manifest_from_context(context: dict[str, Any]) -> dict[str, Any]:
    return _render_yaml("deployment.yaml.j2", context)


def get_microservice_deployment(
    msid: str,
) -> dict[str, Any]:
    """Return the live Deployment object for a microservice."""
    kubectl = Kubectl()
    deployment_yaml = kubectl.get("deployment", name=msid)
    deployment = yaml.load(StringIO(deployment_yaml))
    if not isinstance(deployment, dict):
        raise TypeError(f"Deployment '{msid}' not found")
    return deployment


def _extract_container_spec_from_deployment(
    deployment: dict[str, Any],
) -> dict[str, Any]:
    metadata = deployment.get("metadata") or {}
    spec = deployment.get("spec") or {}
    template = spec.get("template") or {}
    template_metadata = template.get("metadata") or {}
    template_spec = template.get("spec") or {}
    containers = template_spec.get("containers") or []
    if not containers:
        raise ValueError("Deployment does not contain any containers")

    container = containers[0] or {}
    labels = dict(template_metadata.get("labels") or metadata.get("labels") or {})
    image_pull_secrets = template_spec.get("imagePullSecrets") or []

    return {
        "labels": labels,
        "app_label": labels.get("app") or labels.get("service") or metadata.get("name"),
        "service_label": labels.get("service")
        or labels.get("app")
        or metadata.get("name"),
        "version": labels.get("version") or metadata.get("name") or "v1",
        "image": container.get("image"),
        "command": list(container.get("command") or []),
        "args": list(container.get("args") or []),
        "env_list": [
            {"name": env.get("name"), "value": str(env.get("value", ""))}
            for env in (container.get("env") or [])
            if isinstance(env, dict) and env.get("name")
        ],
        "container_ports": [
            {
                "containerPort": int(port.get("containerPort", 0)),
                "protocol": str(port.get("protocol", "TCP")),
            }
            for port in (container.get("ports") or [])
            if isinstance(port, dict)
        ],
        "volume_mounts": [
            dict(mount)
            for mount in (container.get("volumeMounts") or [])
            if isinstance(mount, dict)
        ],
        "volumes": [
            dict(volume)
            for volume in (template_spec.get("volumes") or [])
            if isinstance(volume, dict)
        ],
        "annotations": dict(template_metadata.get("annotations") or {}),
        "node_selector": dict(template_spec.get("nodeSelector") or {}),
        "service_account": template_spec.get("serviceAccountName"),
        "image_pull_secret": (
            str(image_pull_secrets[0].get("name"))
            if image_pull_secrets and isinstance(image_pull_secrets[0], dict)
            else None
        ),
        "enable_service_links": bool(template_spec.get("enableServiceLinks", False)),
    }


def get_microservice_container_spec(
    msid: str,
) -> dict[str, Any]:
    """Return the live container spec for a microservice Deployment."""
    deployment = get_microservice_deployment(msid)
    return _extract_container_spec_from_deployment(deployment)


def build_pinned_pod_manifest(
    msid: str,
    node_id: str,
    container_spec: dict[str, Any],
) -> dict[str, Any]:
    """Build a single-replica Deployment pinned to one node.

    The returned manifest uses the same Deployment template as TOSCA output,
    but with a node-specific name/version so multiple pinned replicas can
    coexist safely.
    """
    pinned_version = _name_token(node_id)
    deployment_name = f"{_name_token(msid)}-pinned"
    context = _deployment_context(
        name=deployment_name,
        version=pinned_version,
        image=str(container_spec["image"]),
        command=list(container_spec.get("command") or []),
        args=list(container_spec.get("args") or []),
        env_list=list(container_spec.get("env_list") or []),
        container_ports=list(container_spec.get("container_ports") or []),
        volume_mounts=list(container_spec.get("volume_mounts") or []),
        volumes=list(container_spec.get("volumes") or []),
        labels=dict(container_spec.get("labels") or {}),
        app_label=str(container_spec.get("app_label") or _name_token(msid)),
        service_label=str(container_spec.get("service_label") or _name_token(msid)),
        annotations=dict(container_spec.get("annotations") or {}),
        node_selector=dict(container_spec.get("node_selector") or {}),
        affinity=build_node_affinity(NODE_AFFINITY_LABEL_KEY, node_id),
        service_account=container_spec.get("service_account"),
        image_pull_secret=container_spec.get("image_pull_secret"),
        enable_service_links=bool(container_spec.get("enable_service_links", False)),
    )
    manifest = _deployment_manifest_from_context(context)
    return manifest


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

    resolved_path: Path | None = None
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
    tosca_file: str | None = None,
    tosca_content: str | None = None,
    image_pull_secret: str | None = None,
    acme_email: str | None = None,
) -> list[dict[str, Any]]:
    logger.debug(
        "Generating Kubernetes manifest",
        extra={
            "has_tosca_file": bool(tosca_file),
            "has_tosca_content": bool(tosca_content),
            "image_pull_secret_set": bool(image_pull_secret),
            "acme_email_set": bool(acme_email),
        },
    )
    if tosca_file:
        tosca_content = _read_tosca_file_content(tosca_file)
    elif not tosca_content:
        raise ValueError("Provide either tosca_file or tosca_content")

    try:
        tosca_dict = yaml.load(StringIO(tosca_content))
        if not isinstance(tosca_dict, dict):
            raise TypeError("TOSCA content must parse into a mapping")
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

    manifests: list[dict[str, Any]] = []
    pending_services: dict[str, dict[str, Any]] = {}
    pending_ingress_route_tcp: list[dict[str, Any]] = []
    pending_ingresses: list[dict[str, Any]] = []
    traefik_acme_email = str(acme_email or DEFAULT_ACME_EMAIL)
    traefik_cert_resolver = TRAEFIK_ACME_RESOLVER_NAME

    # File node templates (derived from Volume) are mounted into the workloads
    # that attach them via a 'volume' requirement.
    file_nodes: dict[str, dict[str, Any]] = {
        node_name: node
        for node_name, node in node_templates.items()
        if str(node.get("type", "")).endswith("File")
    }

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
            if not target:
                # target is the required container path; without it there is
                # nothing to mount.
                continue

            read_only = str(v.get("read_only", "")).lower() == "true"
            if source:
                # source + target -> hostPath bind mount.
                vol_name = _volume_name_from_path(str(source), idx)
                host_path_type = _infer_host_path_type(str(source), str(target), v)
                tosca_volumes.append(
                    {
                        "name": vol_name,
                        "hostPath": {"path": str(source), "type": host_path_type},
                    }
                )
            else:
                # target only -> ephemeral scratch space.
                vol_name = _volume_name_from_path(str(target), idx)
                tosca_volumes.append({"name": vol_name, "emptyDir": {}})

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

        # Attached File node templates -> ConfigMap-backed file mounts.
        for target_node, mount_path in _iter_volume_requirements(node):
            file_node = file_nodes.get(target_node) if target_node else None
            if file_node is None or not mount_path:
                continue
            file_props = file_node.get("properties", {}) or {}
            content = file_props.get("content")
            if content is None:
                logger.warning(
                    "File node '%s' has no content; skipping mount", target_node
                )
                continue

            mount_path = str(mount_path)
            mode_int = _parse_file_mode(file_props.get("mode"))
            # A path that does not end in "/" is treated as a concrete file, so
            # the file is placed exactly there via subPath.
            is_file_path = not mount_path.endswith("/")
            data_key = (
                PurePosixPath(mount_path).name
                if is_file_path
                else _name_token(target_node, "file")
            )

            cm_name = _name_token(f"{k3s_name}-{target_node}")
            cm_vol_name = _name_token(f"cfg-{target_node}")
            manifests.append(
                _render_yaml(
                    "configmap.yaml.j2",
                    {
                        "name": cm_name,
                        "app_label": app_name,
                        "data_key": data_key,
                        "content": content,
                    },
                )
            )

            config_map: dict[str, Any] = {"name": cm_name}
            item: dict[str, Any] = {"key": data_key, "path": data_key}
            if mode_int is not None:
                config_map["defaultMode"] = mode_int
                item["mode"] = mode_int
            config_map["items"] = [item]
            volumes.append({"name": cm_vol_name, "configMap": config_map})

            mount = {"name": cm_vol_name, "mountPath": mount_path, "readOnly": True}
            if is_file_path:
                mount["subPath"] = data_key
            volume_mounts.append(mount)

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
            "enable_service_links": _parse_bool(
                props.get("enable_service_links", props.get("enableServiceLinks")),
                default=False,
            ),
        }
        manifests.append(_render_yaml("deployment.yaml.j2", deployment_context))

        first_service_port = service_ports[0]["port"] if service_ports else 443
        pending_ingress_route_tcp.extend(
            _parse_traefik_tcp_routes(
                props.get("traefik_tcp_routes"),
                default_name=service_name,
                default_service_name=app_name,
                default_service_port=first_service_port,
            )
        )

        # HTTP ingress: 'routes' (list of dicts with domain/port/path) takes priority
        # over the legacy 'ingress' single-dict property.
        routes_raw = props.get("routes")
        ingress_sources: list[Any] = []
        if routes_raw is not None:
            if isinstance(routes_raw, list):
                ingress_sources = routes_raw
            elif isinstance(routes_raw, dict):
                ingress_sources = [routes_raw]
        elif props.get("ingress") is not None:
            ing = props.get("ingress")
            ingress_sources = [ing] if isinstance(ing, dict) else []

        has_ingress = False
        for ingress_src in ingress_sources:
            ingress_definition = _parse_ingress_definition(
                ingress_src,
                default_name=service_name,
                default_service_name=app_name,
                default_service_port=first_service_port,
                default_acme_email=DEFAULT_ACME_EMAIL,
            )
            if ingress_definition is not None:
                ingress_cert_resolver = ingress_definition.get("cert_resolver")
                if ingress_cert_resolver:
                    if traefik_cert_resolver == TRAEFIK_ACME_RESOLVER_NAME:
                        traefik_cert_resolver = str(ingress_cert_resolver)
                    elif traefik_cert_resolver != ingress_cert_resolver:
                        logger.warning(
                            "Multiple ingress cert resolvers requested; keeping %r and ignoring %r",
                            traefik_cert_resolver,
                            ingress_cert_resolver,
                        )
                pending_ingresses.append(ingress_definition)
                has_ingress = True

        if has_ingress:
            service_ports = [
                {key: value for key, value in sp.items() if key != "nodePort"}
                for sp in service_ports
            ]

        # One service per unique app_name — covers multi-version deployments
        service_key = app_name
        if service_ports and service_key not in pending_services:
            svc_type = (
                "NodePort"
                if not has_ingress and any("nodePort" in sp for sp in service_ports)
                else "ClusterIP"
            )
            pending_services[service_key] = {
                "name": app_name,
                "service_type": svc_type,
                "service_ports": service_ports,
                "selector": {"app": app_name},
            }

        # Emit all network resources after all deployments
    for svc_context in pending_services.values():
        manifests.append(_render_yaml("service.yaml.j2", svc_context))
    if pending_ingresses:
        manifests.extend(
            _render_yaml_documents(
                "traefik-acme.yaml.j2",
                {
                    "acme_email": traefik_acme_email,
                    "cert_resolver": traefik_cert_resolver,
                    "acme_storage_path": TRAEFIK_ACME_STORAGE_PATH,
                    "persistent_volume_claim": TRAEFIK_ACME_VOLUME_NAME,
                    "persistent_mount_path": TRAEFIK_ACME_VOLUME_MOUNT_PATH,
                    "persistent_volume_claim_namespace": TRAEFIK_ACME_PVC_NAMESPACE,
                    "persistent_volume_claim_size": TRAEFIK_ACME_PVC_SIZE,
                },
            )
        )
    for ingress_context in pending_ingresses:
        manifests.append(_render_yaml("ingress.yaml.j2", ingress_context))
    for route_context in pending_ingress_route_tcp:
        manifests.append(_render_yaml("ingress_route_tcp.yaml.j2", route_context))

    logger.info("Generated %d Kubernetes manifest objects", len(manifests))

    return manifests

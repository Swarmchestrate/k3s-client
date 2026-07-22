from pathlib import Path
from unittest.mock import patch

import pytest

import k3s_client.utils.manifest as manifest_utils


def test_read_tosca_file_content_raises_when_missing(tmp_path):
    missing_file = tmp_path / "does-not-exist.yaml"
    with pytest.raises(FileNotFoundError):
        manifest_utils._read_tosca_file_content(str(missing_file))


def test_read_tosca_file_content_raises_for_directory(tmp_path):
    with pytest.raises(ValueError):
        manifest_utils._read_tosca_file_content(str(tmp_path))


def test_read_tosca_file_content_reads_from_cwd_relative_path(tmp_path, monkeypatch):
    tosca_file = tmp_path / "sample.yaml"
    tosca_file.write_text("tosca_definitions_version: tosca_simple_yaml_1_3\n")

    monkeypatch.chdir(tmp_path)
    content = manifest_utils._read_tosca_file_content("sample.yaml")

    assert "tosca_definitions_version" in content


def test_read_tosca_file_content_falls_back_to_repo_relative(tmp_path, monkeypatch):
    fake_repo = tmp_path / "repo"
    fake_manifest_file = fake_repo / "k3s_client" / "utils" / "manifest.py"
    fake_tosca_file = fake_repo / "examples" / "sample.yaml"

    fake_manifest_file.parent.mkdir(parents=True, exist_ok=True)
    fake_tosca_file.parent.mkdir(parents=True, exist_ok=True)
    fake_manifest_file.write_text("# test marker\n", encoding="utf-8")
    fake_tosca_file.write_text(
        "tosca_definitions_version: tosca_simple_yaml_1_3\n", encoding="utf-8"
    )

    monkeypatch.setattr(manifest_utils, "__file__", str(fake_manifest_file))
    monkeypatch.chdir(Path("/tmp"))
    content = manifest_utils._read_tosca_file_content("examples/sample.yaml")

    assert "tosca_definitions_version" in content


def test_get_kubernetes_manifest_parses_yaml_content():
    tosca_content = """
service_template:
  node_templates:
    web:
      type: tosca.nodes.Swarm.Microservice
      properties:
        image: nginx:latest
"""

    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    assert manifests
    assert any(doc.get("kind") == "Deployment" for doc in manifests)


def test_get_kubernetes_manifest_accepts_top_level_node_templates():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
"""

    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    assert manifests
    assert any(doc.get("kind") == "Deployment" for doc in manifests)
    assert not any(doc.get("kind") == "Ingress" for doc in manifests)
    assert not any(doc.get("kind") == "HelmChartConfig" for doc in manifests)
    assert not any(doc.get("kind") == "PersistentVolumeClaim" for doc in manifests)


def test_get_kubernetes_manifest_raises_for_invalid_yaml():
    with pytest.raises(ValueError, match="Invalid TOSCA content"):
        manifest_utils.get_kubernetes_manifest(tosca_content="service_template: [")


def test_get_kubernetes_manifest_validates_routes_strictly_when_supported():
    tosca_content = """
service_template:
  node_templates:
    web:
      type: tosca.nodes.Swarm.Microservice
      properties:
        image: nginx:latest
        ports:
        - port: 80
          targetPort: 80
        routes:
        - domain: web.example.com
          port: 80
          path: /
"""

    captured = {"contents": []}

    class DummySardou:
        def __init__(self, content):
            captured["contents"].append(content)

        def get_affinity(self):
            return {}

    with patch("k3s_client.utils.manifest.Sardou", DummySardou):
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    assert len(captured["contents"]) == 1
    assert "routes:" in captured["contents"][0]
    assert any(doc.get("kind") == "Ingress" for doc in manifests)


def test_get_kubernetes_manifest_propagates_sardou_validation_error():
    tosca_content = """
  service_template:
    node_templates:
      web:
        type: tosca.nodes.Swarm.Microservice
        properties:
          image: nginx:latest
  """

    class FailingSardou:
        def __init__(self, content):
            pass

        def get_affinity(self):
            raise ValueError("validation failed")

    with patch("k3s_client.utils.manifest.Sardou", FailingSardou):
        with pytest.raises(ValueError, match="validation failed"):
            manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)


def _deployment(manifests):
    return next(d for d in manifests if d.get("kind") == "Deployment")


def _pod_spec(deployment):
    return deployment["spec"]["template"]["spec"]


def test_pod_spec_disables_service_links_by_default():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    assert spec["enableServiceLinks"] is False


def test_pod_spec_enable_service_links_can_be_overridden_from_tosca():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      enable_service_links: true
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    assert spec["enableServiceLinks"] is True


def test_parse_file_mode():
    assert manifest_utils._parse_file_mode("0444") == 0o444 == 292
    assert manifest_utils._parse_file_mode("644") == 0o644
    assert manifest_utils._parse_file_mode(None) is None
    assert manifest_utils._parse_file_mode("not-a-mode") is None


def test_volume_source_and_target_becomes_hostpath():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      volumes:
      - source: /opt/data
        target: /opt/data
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    vol = next(v for v in spec["volumes"] if "hostPath" in v)
    assert vol["hostPath"]["path"] == "/opt/data"
    assert vol["hostPath"]["type"] == "DirectoryOrCreate"
    mount = next(
        m for m in spec["containers"][0]["volumeMounts"] if m["name"] == vol["name"]
    )
    assert mount["mountPath"] == "/opt/data"


def test_volume_target_only_becomes_emptydir():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      volumes:
      - target: /tmp
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    vol = next(v for v in spec["volumes"] if "emptyDir" in v)
    mount = next(
        m for m in spec["containers"][0]["volumeMounts"] if m["name"] == vol["name"]
    )
    assert mount["mountPath"] == "/tmp"


def test_volume_file_source_and_target_becomes_file_or_create_hostpath():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      volumes:
      - source: /test/source/configuration.ini
        target: /test/target/configuration.ini
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    vol = next(v for v in spec["volumes"] if "hostPath" in v)
    assert vol["hostPath"]["path"] == "/test/source/configuration.ini"
    assert vol["hostPath"]["type"] == "FileOrCreate"
    mount = next(
        m for m in spec["containers"][0]["volumeMounts"] if m["name"] == vol["name"]
    )
    assert mount["mountPath"] == "/test/target/configuration.ini"


def test_volume_source_target_respects_explicit_host_path_type():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      volumes:
      - source: /opt/custom
        target: /app/custom
        host_path_type: Directory
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    vol = next(v for v in spec["volumes"] if "hostPath" in v)
    assert vol["hostPath"]["type"] == "Directory"


def test_volume_source_target_can_be_read_only():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      volumes:
      - source: ./test/config
        target: /test/config
        read_only: "true"
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    vol = next(v for v in spec["volumes"] if "hostPath" in v)
    mount = next(
        m for m in spec["containers"][0]["volumeMounts"] if m["name"] == vol["name"]
    )
    assert mount["mountPath"] == "/test/config"
    assert mount["readOnly"] is True


def test_attached_file_becomes_configmap_with_subpath_mount():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
    requirements:
    - volume:
        node: banner_file
        relationship:
          properties:
            mount_path: /etc/bookinfo/banner.txt
  banner_file:
    type: tosca.nodes.Swarm.File
    properties:
      content: |
        Welcome to Bookinfo.
      mode: "0444"
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    configmap = next(d for d in manifests if d.get("kind") == "ConfigMap")
    assert configmap["data"]["banner.txt"] == "Welcome to Bookinfo.\n"

    spec = _pod_spec(_deployment(manifests))
    vol = next(v for v in spec["volumes"] if "configMap" in v)
    assert vol["configMap"]["name"] == configmap["metadata"]["name"]
    assert vol["configMap"]["defaultMode"] == 0o444
    assert vol["configMap"]["items"][0]["mode"] == 0o444

    mount = next(
        m for m in spec["containers"][0]["volumeMounts"] if m["name"] == vol["name"]
    )
    assert mount["mountPath"] == "/etc/bookinfo/banner.txt"
    assert mount["subPath"] == "banner.txt"


def test_translation_is_deterministic():
    tosca_content = """
node_templates:
  web:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      volumes:
      - target: /tmp
      - source: /opt/data
        target: /opt/data
    requirements:
    - volume:
        node: banner_file
        relationship:
          properties:
            mount_path: /etc/banner.txt
  banner_file:
    type: tosca.nodes.Swarm.File
    properties:
      content: hello
      mode: "0444"
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        first = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)
        second = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    assert first == second


def test_deployment_and_service_do_not_include_namespace():
    tosca_content = """
node_templates:
  nginx:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:1.27-alpine
      ports:
      - port: 443
        targetPort: 443
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    deployment = next(d for d in manifests if d.get("kind") == "Deployment")
    service = next(d for d in manifests if d.get("kind") == "Service")
    assert "namespace" not in deployment["metadata"]
    assert "namespace" not in service["metadata"]


def test_file_configmap_does_not_include_namespace():
    tosca_content = """
node_templates:
  app:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:1.27-alpine
      ports:
      - port: 80
        targetPort: 80
    requirements:
    - volume:
        node: app_index
        relationship:
          properties:
            mount_path: /usr/share/nginx/html/index.html
  app_index:
    type: tosca.nodes.Swarm.File
    properties:
      content: hello
"""

    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    configmap = next(d for d in manifests if d.get("kind") == "ConfigMap")
    assert "namespace" not in configmap["metadata"]


def test_generates_traefik_ingress_with_acme_resources_for_k3s():
    tosca_content = """
node_templates:
  site_a:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:1.27-alpine
      labels:
        app: site-a
      ports:
      - port: 80
        targetPort: 80
      ingress:
        domain: cloud-193-225-251-54.sztaki.science-cloud.hu
        port: 80
        path: /
        email: emodi.mark@gmail.com
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    ingress = next(d for d in manifests if d.get("kind") == "Ingress")
    assert ingress["apiVersion"] == "networking.k8s.io/v1"
    assert ingress["metadata"]["name"] == "site-a"
    assert (
        ingress["metadata"]["annotations"][
            "traefik.ingress.kubernetes.io/router.entrypoints"
        ]
        == "websecure"
    )
    assert (
        ingress["metadata"]["annotations"]["traefik.ingress.kubernetes.io/router.tls"]
        == "true"
    )
    assert (
        ingress["metadata"]["annotations"][
            "traefik.ingress.kubernetes.io/router.tls.certresolver"
        ]
        == "le"
    )
    assert ingress["spec"]["ingressClassName"] == "traefik"
    assert (
        ingress["spec"]["rules"][0]["host"]
        == "cloud-193-225-251-54.sztaki.science-cloud.hu"
    )
    backend = ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]
    assert backend["name"] == "site-a"
    assert backend["port"]["number"] == 80
    assert ingress["spec"]["tls"][0]["hosts"] == [
        "cloud-193-225-251-54.sztaki.science-cloud.hu"
    ]

    chart_config = next(d for d in manifests if d.get("kind") == "HelmChartConfig")
    assert chart_config["metadata"]["name"] == "traefik"
    assert chart_config["metadata"]["namespace"] == "kube-system"
    # email is always hardcoded to DEFAULT_ACME_EMAIL regardless of what is in TOSCA
    assert (
        f"--certificatesresolvers.le.acme.email={manifest_utils.DEFAULT_ACME_EMAIL}"
        in chart_config["spec"]["valuesContent"]
    )

    pvc = next(d for d in manifests if d.get("kind") == "PersistentVolumeClaim")
    assert pvc["metadata"]["name"] == "traefik-data"
    assert pvc["metadata"]["namespace"] == "kube-system"
    assert pvc["spec"]["resources"]["requests"]["storage"] == "64Mi"


def test_generates_one_shared_acme_config_for_multiple_ingresses():
    tosca_content = """
node_templates:
  site_a:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      labels:
        app: site-a
      ports:
      - port: 80
        targetPort: 80
      ingress:
        domain: cloud-193-225-251-54.sztaki.science-cloud.hu
        email: emodi.mark@gmail.com
  site_b:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      labels:
        app: site-b
      ports:
      - port: 80
        targetPort: 80
      ingress:
        domain: webswch.chickenkiller.com
        email: emodi.mark@gmail.com
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    ingresses = [d for d in manifests if d.get("kind") == "Ingress"]
    assert len(ingresses) == 2
    assert sorted(i["spec"]["rules"][0]["host"] for i in ingresses) == [
        "cloud-193-225-251-54.sztaki.science-cloud.hu",
        "webswch.chickenkiller.com",
    ]
    assert len([d for d in manifests if d.get("kind") == "HelmChartConfig"]) == 1
    assert len([d for d in manifests if d.get("kind") == "PersistentVolumeClaim"]) == 1


def test_ingress_defaults_to_websecure_tls_service_port_and_shared_email():
    tosca_content = """
node_templates:
  gateway:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      labels:
        app: edge-gw
      ports:
      - port: 8080
        targetPort: 8080
      ingress:
        domain: edge.example.com
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    ingress = next(d for d in manifests if d.get("kind") == "Ingress")
    annotations = ingress["metadata"]["annotations"]
    assert (
        annotations["traefik.ingress.kubernetes.io/router.entrypoints"] == "websecure"
    )
    assert annotations["traefik.ingress.kubernetes.io/router.tls"] == "true"
    assert annotations["traefik.ingress.kubernetes.io/router.tls.certresolver"] == "le"
    assert (
        ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["port"][
            "number"
        ]
        == 8080
    )
    chart_config = next(d for d in manifests if d.get("kind") == "HelmChartConfig")
    assert (
        f"--certificatesresolvers.le.acme.email={manifest_utils.DEFAULT_ACME_EMAIL}"
        in chart_config["spec"]["valuesContent"]
    )
    assert any(d.get("kind") == "PersistentVolumeClaim" for d in manifests)


def test_ingress_tosca_email_is_ignored_and_hardcoded_default_is_used():
    """TOSCA ingress 'email' field is ignored; email is always DEFAULT_ACME_EMAIL."""
    tosca_content = """
node_templates:
  gateway:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      labels:
        app: edge-gw
      ports:
      - port: 80
        targetPort: 80
      ingress:
        domain: edge.example.com
        email: override@example.com
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(
            tosca_content=tosca_content,
        )

    chart_config = next(d for d in manifests if d.get("kind") == "HelmChartConfig")
    # TOSCA email is ignored; the hardcoded default must appear
    assert (
        f"--certificatesresolvers.le.acme.email={manifest_utils.DEFAULT_ACME_EMAIL}"
        in chart_config["spec"]["valuesContent"]
    )
    assert "override@example.com" not in chart_config["spec"]["valuesContent"]


def test_ingress_uses_function_parameter_email_when_tosca_email_missing():
    tosca_content = """
node_templates:
  gateway:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      labels:
        app: edge-gw
      ports:
      - port: 80
        targetPort: 80
      ingress:
        domain: edge.example.com
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(
            tosca_content=tosca_content,
            acme_email="parameter@example.com",
        )

    chart_config = next(d for d in manifests if d.get("kind") == "HelmChartConfig")
    assert (
        "--certificatesresolvers.le.acme.email=parameter@example.com"
        in chart_config["spec"]["valuesContent"]
    )


def test_ingress_keeps_service_cluster_ip_and_drops_node_port():
    tosca_content = """
node_templates:
  gateway:
    type: tosca.nodes.Swarm.Microservice
    properties:
      image: nginx:latest
      labels:
        app: edge-gw
      ports:
      - port: 80
        targetPort: 80
        nodePort: 30080
      ingress:
        domain: edge.example.com
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    service = next(d for d in manifests if d.get("kind") == "Service")
    assert service["spec"]["type"] == "ClusterIP"
    assert "nodePort" not in service["spec"]["ports"][0]

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


def test_get_kubernetes_manifest_raises_for_invalid_yaml():
    with pytest.raises(ValueError, match="Invalid TOSCA content"):
        manifest_utils.get_kubernetes_manifest(tosca_content="service_template: [")


def _deployment(manifests):
    return next(d for d in manifests if d.get("kind") == "Deployment")


def _pod_spec(deployment):
    return deployment["spec"]["template"]["spec"]


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
      - source: /home/gunjan/classification-conf/configuration.ini
        target: /app/configuration.ini
"""
    with patch("k3s_client.utils.manifest.Sardou") as mock_sardou:
        mock_sardou.return_value.get_affinity.return_value = {}
        manifests = manifest_utils.get_kubernetes_manifest(tosca_content=tosca_content)

    spec = _pod_spec(_deployment(manifests))
    vol = next(v for v in spec["volumes"] if "hostPath" in v)
    assert (
        vol["hostPath"]["path"] == "/home/gunjan/classification-conf/configuration.ini"
    )
    assert vol["hostPath"]["type"] == "FileOrCreate"
    mount = next(
        m for m in spec["containers"][0]["volumeMounts"] if m["name"] == vol["name"]
    )
    assert mount["mountPath"] == "/app/configuration.ini"


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
      - source: ./nas/config
        target: /app/config
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
    assert mount["mountPath"] == "/app/config"
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

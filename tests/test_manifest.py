from pathlib import Path

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

from pathlib import Path

import pytest

from k3s_client.utils.manifest import _read_tosca_file_content


def test_read_tosca_file_content_raises_when_missing(tmp_path):
    missing_file = tmp_path / "does-not-exist.yaml"
    with pytest.raises(FileNotFoundError):
        _read_tosca_file_content(str(missing_file))


def test_read_tosca_file_content_raises_for_directory(tmp_path):
    with pytest.raises(ValueError):
        _read_tosca_file_content(str(tmp_path))


def test_read_tosca_file_content_reads_from_cwd_relative_path(tmp_path, monkeypatch):
    tosca_file = tmp_path / "sample.yaml"
    tosca_file.write_text("tosca_definitions_version: tosca_simple_yaml_1_3\n")

    monkeypatch.chdir(tmp_path)
    content = _read_tosca_file_content("sample.yaml")

    assert "tosca_definitions_version" in content


def test_read_tosca_file_content_falls_back_to_repo_relative(monkeypatch):
    monkeypatch.chdir(Path("/tmp"))
    content = _read_tosca_file_content("examples/Bookinfo.yaml")

    assert "tosca_definitions_version" in content
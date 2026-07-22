from unittest.mock import patch

from k3s_client.cli.kubectl import Kubectl


def test_apply_manifest_uses_server_side_apply_with_default_field_manager(tmp_path):
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("apiVersion: v1\nkind: ConfigMap\n", encoding="utf-8")

    kubectl = Kubectl()

    with patch.object(kubectl, "_run", return_value="ok") as mock_run:
        result = kubectl.apply_manifest(str(manifest))

    assert result == "ok"
    mock_run.assert_called_once_with(
        [
            "kubectl",
            "apply",
            "--server-side",
            "--field-manager=tosca-controller",
            "-f",
            str(manifest),
        ]
    )


def test_apply_manifest_accepts_custom_field_manager(tmp_path):
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("apiVersion: v1\nkind: ConfigMap\n", encoding="utf-8")

    kubectl = Kubectl()

    with patch.object(kubectl, "_run", return_value="ok") as mock_run:
        kubectl.apply_manifest(str(manifest), field_manager="swarm-optimiser")

    mock_run.assert_called_once_with(
        [
            "kubectl",
            "apply",
            "--server-side",
            "--field-manager=swarm-optimiser",
            "-f",
            str(manifest),
        ]
    )

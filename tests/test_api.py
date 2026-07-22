from unittest.mock import patch

from k3s_client.api.applications import ApplicationManager
from k3s_client.api.pods import PodManager
from k3s_client.agent.client import SwarmAgentClient


def _mock_application_agent(mock_client):
    agent = mock_client.return_value
    agent.execute.side_effect = lambda action, params: {
        "action": action,
        "params": params,
    }
    return agent


def test_application_manager_requires_swarm_agent_mode():
    with patch("k3s_client.api.applications.SwarmAgentClient"):
        try:
            ApplicationManager(execution_mode="direct", swarm_agent_url="http://a")
            assert False, "direct mode should not be accepted"
        except Exception as exc:
            assert "swarm-agent" in str(exc)


def test_application_manager_delegates_scale_to():
    with patch("k3s_client.api.applications.SwarmAgentClient") as mock_client:
        _mock_application_agent(mock_client)
        app = ApplicationManager(swarm_agent_url="http://agent")
        out = app.scale_to("ms1", 3, namespace="default")
        assert out["action"] == "applications.scale_to"
        assert out["params"]["msid"] == "ms1"
        assert out["params"]["count"] == 3


def test_application_manager_delegates_pod_operations():
    with patch("k3s_client.api.applications.SwarmAgentClient") as mock_client:
        _mock_application_agent(mock_client)
        app = ApplicationManager(swarm_agent_url="http://agent")

        create_out = app.create_pod("ms1", nodeid="node2", namespace="default")
        delete_out = app.delete_pod("ms1", podid="pod-a", namespace="default")
        scale_out = app.scale_to("ms1", 5, namespace="default")
        migrate_out = app.migrate_pod(
            "ms1", podid="pod-a", nodeid="node3", namespace="default"
        )

        assert create_out["action"] == "applications.create_pod"
        assert delete_out["action"] == "applications.delete_pod"
        assert scale_out["action"] == "applications.scale_to"
        assert migrate_out["action"] == "applications.migrate_pod"


def test_application_manager_delegates_manifest_and_registry_operations():
    with patch("k3s_client.api.applications.SwarmAgentClient") as mock_client:
        _mock_application_agent(mock_client)
        app = ApplicationManager(swarm_agent_url="http://agent")

        apply_out = app.apply_manifest("m.yaml", namespace="default")
        delete_out = app.delete_manifest("m.yaml")
        secret_out = app.create_registry_secret(
            name="s",
            registry="r",
            username="u",
            password="p",
            namespace="default",
        )

        assert apply_out["action"] == "applications.apply_manifest"
        assert delete_out["action"] == "applications.delete_manifest"
        assert secret_out["action"] == "applications.create_registry_secret"


def test_application_manager_delegates_grouped_pod_node_mapping():
    with patch("k3s_client.api.applications.SwarmAgentClient") as mock_client:
        _mock_application_agent(mock_client)
        app = ApplicationManager(swarm_agent_url="http://agent")

        grouped = app.get_pod_node_mapping(namespace="default")

        assert grouped["action"] == "applications.get_grouped_pod_node_mapping"


def test_pod_manager_delegates_list_pods():
    with patch("k3s_client.api.pods.SwarmAgentClient") as mock_client:
        agent = mock_client.return_value
        agent.execute.return_value = ["pod1", "pod2"]

        pm = PodManager(swarm_agent_url="http://agent")
        pods = pm.list_pods(namespace="default")

        assert pods == ["pod1", "pod2"]
        agent.execute.assert_called_once_with(
            action="pods.list_pods",
            params={"namespace": "default", "label_selector": None},
        )


def test_swarm_agent_client_defaults_to_local_base_url():
    client = SwarmAgentClient()
    assert client.base_url == "http://127.0.0.1:8080"
    assert client.url == "http://127.0.0.1:8080/v1/actions"


def test_apply_tosca_dry_run_generates_manifest_and_skips_apply(tmp_path):
    with (
        patch("k3s_client.api.applications.SwarmAgentClient") as mock_client,
        patch("k3s_client.api.applications.get_kubernetes_manifest") as mock_manifest,
    ):
        agent = _mock_application_agent(mock_client)
        mock_manifest.return_value = [
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "a"}},
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "a"}},
        ]
        app = ApplicationManager(swarm_agent_url="http://agent")

        out_file = tmp_path / "generated.yaml"
        result = app.apply_tosca(
            tosca_content="node_templates: {}",
            dry_run=True,
            output_manifest_file=str(out_file),
        )

        assert result["ok"] is True
        assert result["mode"] == "dry-run"
        assert result["applied"] is False
        assert result["agent_response"] is None
        assert result["manifest"]["resource_count"] == 2
        assert result["manifest"]["kind_summary"]["Deployment"] == 1
        assert result["manifest"]["kind_summary"]["Service"] == 1
        assert out_file.exists()
        assert "kind: Deployment" in out_file.read_text(encoding="utf-8")
        assert "kind: Service" in out_file.read_text(encoding="utf-8")
        agent.execute.assert_not_called()


def test_apply_tosca_apply_calls_agent_and_returns_standardized_output(tmp_path):
    with (
        patch("k3s_client.api.applications.SwarmAgentClient") as mock_client,
        patch("k3s_client.api.applications.get_kubernetes_manifest") as mock_manifest,
    ):
        _mock_application_agent(mock_client)
        mock_manifest.return_value = [
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "a"}}
        ]
        app = ApplicationManager(swarm_agent_url="http://agent")

        out_file = tmp_path / "generated.yaml"
        result = app.apply_tosca(
            tosca_content="node_templates: {}",
            output_manifest_file=str(out_file),
        )

        assert result["ok"] is True
        assert result["mode"] == "apply"
        assert result["applied"] is True
        assert result["namespace"] == "default"
        assert result["manifest"]["resource_count"] == 1
        assert result["manifest"]["kind_summary"]["Deployment"] == 1
        assert result["agent_response"]["action"] == "applications.apply_manifest"
        assert result["agent_response"]["params"]["namespace"] == "default"
        assert result["agent_response"]["params"]["manifest_file"] == str(out_file)


def test_apply_tosca_respects_dry_run_by_default_and_allows_override(tmp_path):
    with (
        patch("k3s_client.api.applications.SwarmAgentClient") as mock_client,
        patch("k3s_client.api.applications.get_kubernetes_manifest") as mock_manifest,
    ):
        agent = _mock_application_agent(mock_client)
        mock_manifest.return_value = [
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "a"}}
        ]
        app = ApplicationManager(
            swarm_agent_url="http://agent", dry_run_by_default=True
        )

        out_file = tmp_path / "generated.yaml"
        result_default = app.apply_tosca(
            tosca_content="node_templates: {}",
            output_manifest_file=str(out_file),
        )
        assert result_default["mode"] == "dry-run"
        assert result_default["applied"] is False
        agent.execute.assert_not_called()

        result_override = app.apply_tosca(
            tosca_content="node_templates: {}",
            dry_run=False,
            output_manifest_file=str(out_file),
        )
        assert result_override["mode"] == "apply"
        assert result_override["applied"] is True
        assert (
            result_override["agent_response"]["action"] == "applications.apply_manifest"
        )

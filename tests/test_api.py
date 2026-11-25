from inspect import signature
from unittest.mock import ANY, call, patch

import pytest

from k3s_client.api import applications as applications_module
from k3s_client.api.applications import ApplicationManager
from k3s_client.api.optimizer_runtime import OptimizerRuntimeClient
from k3s_client.api.pods import (
    PodManager,
    parse_cpu_quantity,
    parse_memory_quantity,
)
from k3s_client.exceptions import K3sClientError
from k3s_client.utils import manifest as manifest_utils


def test_application_manager_has_no_http_client_dependency():
    assert not hasattr(applications_module, "SwarmAgentClient")
    params = signature(ApplicationManager.__init__).parameters
    assert "use_kubectl" not in params
    assert "execution_mode" not in params
    assert "swarm_agent_url" not in params
    assert "swarm_agent_token" not in params
    assert "default_namespace" not in params


def test_application_manager_uses_local_kubectl_for_manifest_operations():
    with (
        patch("k3s_client.api.applications.Kubectl") as mock_kubectl,
        patch("k3s_client.api.applications.PodManager"),
        patch("k3s_client.api.applications.OptimizerRuntimeClient"),
    ):
        kubectl = mock_kubectl.return_value
        app = ApplicationManager()

        apply_out = app.apply_manifest("m.yaml")
        delete_out = app.delete_manifest("m.yaml")
        secret_out = app.create_registry_secret(
            name="s",
            registry="r",
            username="u",
            password="p",
        )

        assert apply_out == kubectl.apply_manifest.return_value
        assert delete_out == kubectl.delete_manifest.return_value
        assert secret_out == kubectl.create_registry_secret.return_value
        kubectl.apply_manifest.assert_called_once_with("m.yaml", dry_run=False)
        kubectl.delete_manifest.assert_called_once_with("m.yaml", dry_run=False)
        kubectl.create_registry_secret.assert_called_once_with(
            name="s",
            registry="r",
            username="u",
            password="p",
            email=None,
            dry_run=False,
        )


def test_application_manager_delegates_runtime_methods_to_local_optimizer():
    with (
        patch("k3s_client.api.applications.Kubectl"),
        patch("k3s_client.api.applications.PodManager") as mock_pod_manager,
        patch("k3s_client.api.applications.OptimizerRuntimeClient") as mock_runtime,
        patch("k3s_client.api.applications.get_microservice_deployment"),
    ):
        runtime = mock_runtime.return_value
        pod_manager = mock_pod_manager.return_value
        pod_manager._get_grouped_pod_node_mapping.return_value = {
            "ms1": {"pod-a": "node-1"}
        }
        runtime.scale_to.return_value = {"ok": True, "operation": "scale_to"}
        runtime.create_pod.return_value = {"ok": True, "operation": "create_pod"}
        runtime.delete_pod.return_value = {"ok": True, "operation": "delete_pod"}
        runtime.migrate_pod.return_value = {"ok": True, "operation": "migrate_pod"}

        app = ApplicationManager()

        assert app.scale_to("ms1", 3) == {"ok": True, "operation": "scale_to"}
        assert app.create_pod("ms1", nodeid="node-2") == {
            "ok": True,
            "operation": "create_pod",
        }
        assert app.delete_pod("ms1", podid="pod-a") == {
            "ok": True,
            "operation": "delete_pod",
        }
        assert app.migrate_pod("ms1", podid="pod-a", nodeid="node-3") == {
            "ok": True,
            "operation": "migrate_pod",
        }
        assert app.get_pod_node_mapping() == {"ms1": {"pod-a": "node-1"}}

        runtime.scale_to.assert_called_once_with("ms1", 3, dry_run=False)
        runtime.create_pod.assert_called_once_with(
            msid="ms1",
            nodeid="node-2",
            dry_run=False,
        )
        runtime.delete_pod.assert_called_once_with(
            msid="ms1",
            podid="pod-a",
            dry_run=False,
        )
        runtime.migrate_pod.assert_called_once_with(
            msid="ms1",
            podid="pod-a",
            nodeid="node-3",
            dry_run=False,
        )
        pod_manager._get_grouped_pod_node_mapping.assert_called_once_with(
            label_selector=None,
        )


def test_application_manager_create_pod_without_nodeid_scales_current_deployment():
    with (
        patch("k3s_client.api.applications.Kubectl"),
        patch("k3s_client.api.applications.PodManager"),
        patch("k3s_client.api.applications.OptimizerRuntimeClient") as mock_runtime,
        patch("k3s_client.api.applications.get_microservice_deployment") as mock_dep,
    ):
        runtime = mock_runtime.return_value
        mock_dep.return_value = {"spec": {"replicas": 2}}
        runtime.scale_to.return_value = {"ok": True, "operation": "scale_to"}

        app = ApplicationManager()
        result = app.create_pod("ms1")

        assert result == {"ok": True, "operation": "scale_to"}
        mock_dep.assert_called_once_with("ms1")
        runtime.scale_to.assert_called_once_with("ms1", 3, dry_run=False)


def test_application_manager_delete_pod_without_podid_scales_current_deployment():
    with (
        patch("k3s_client.api.applications.Kubectl"),
        patch("k3s_client.api.applications.PodManager"),
        patch("k3s_client.api.applications.OptimizerRuntimeClient") as mock_runtime,
    ):
        runtime = mock_runtime.return_value
        runtime.delete_pod.return_value = {"ok": True, "operation": "delete_pod"}

        app = ApplicationManager()
        result = app.delete_pod("ms1")

        assert result == {"ok": True, "operation": "delete_pod"}
        runtime.delete_pod.assert_called_once_with(
            msid="ms1", podid=None, dry_run=False
        )


def test_application_manager_apply_tosca_uses_local_manifest_application(tmp_path):
    with (
        patch("k3s_client.api.applications.Kubectl") as mock_kubectl,
        patch("k3s_client.api.applications.PodManager"),
        patch("k3s_client.api.applications.OptimizerRuntimeClient"),
        patch("k3s_client.api.applications.get_kubernetes_manifest") as mock_manifest,
    ):
        kubectl = mock_kubectl.return_value
        mock_manifest.return_value = [
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "a"}},
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "a"}},
        ]
        kubectl.apply_manifest.return_value = "applied"
        app = ApplicationManager()

        out_file = tmp_path / "generated.yaml"
        result = app.apply_tosca(
            tosca_content="node_templates: {}",
            output_manifest_file=str(out_file),
        )

        assert result["ok"] is True
        assert result["mode"] == "apply"
        assert result["applied"] is True
        assert result["apply_response"] == "applied"
        assert result["manifest"]["resource_count"] == 2
        assert out_file.exists()
        kubectl.apply_manifest.assert_called_once_with(str(out_file), dry_run=False)


def test_application_manager_dry_run_supported_across_methods():
    with (
        patch("k3s_client.api.applications.Kubectl"),
        patch("k3s_client.api.applications.PodManager"),
        patch("k3s_client.api.applications.OptimizerRuntimeClient"),
        patch("k3s_client.api.applications.get_kubernetes_manifest"),
    ):
        app = ApplicationManager(dry_run_by_default=True)

        responses = [
            app.apply_manifest("m.yaml"),
            app.delete_manifest("m.yaml"),
            app.create_registry_secret(
                name="s",
                registry="r",
                username="u",
                password="p",
            ),
            app.create_pod("ms1", nodeid="n1"),
            app.scale_to("ms1", 2),
            app.delete_pod("ms1", podid="pod-a"),
            app.migrate_pod("ms1", podid="pod-a", nodeid="n2"),
            app.get_pod_node_mapping(label_selector="app=ms1"),
        ]

        for response in responses:
            assert response["ok"] is True
            assert response["mode"] == "dry-run"
            assert response["executed"] is False
            assert "operation" in response
            assert "params" in response
            assert "result" in response
            assert response["result"] is not None
            assert "namespace" not in response["params"]


def test_application_manager_dry_run_executes_underlying_calls_and_returns_result(
    tmp_path,
):
    with (
        patch("k3s_client.api.applications.Kubectl") as mock_kubectl,
        patch("k3s_client.api.applications.PodManager") as mock_pod_manager,
        patch("k3s_client.api.applications.OptimizerRuntimeClient") as mock_runtime,
        patch("k3s_client.api.applications.get_kubernetes_manifest") as mock_manifest,
    ):
        kubectl = mock_kubectl.return_value
        pod_manager = mock_pod_manager.return_value
        runtime = mock_runtime.return_value

        kubectl.apply_manifest.return_value = [{"kind": "Deployment"}]
        kubectl.delete_manifest.return_value = [{"status": "Success"}]
        kubectl.create_registry_secret.return_value = {"kind": "Secret"}
        pod_manager._get_grouped_pod_node_mapping.return_value = {
            "ms1": {"pod-a": "node-1"}
        }
        runtime.scale_to.return_value = {"operation": "scale_to"}
        runtime.create_pod.return_value = {"operation": "create_pod"}
        runtime.delete_pod.return_value = {"operation": "delete_pod"}
        runtime.migrate_pod.return_value = {"operation": "migrate_pod"}
        mock_manifest.return_value = [
            {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "a"}}
        ]

        app = ApplicationManager(dry_run_by_default=False)
        out_file = tmp_path / "generated.yaml"

        apply_tosca_response = app.apply_tosca(
            tosca_content="node_templates: {}",
            output_manifest_file=str(out_file),
            dry_run=True,
        )
        assert apply_tosca_response["result"] == [{"kind": "Deployment"}]

        apply_response = app.apply_manifest("m.yaml", dry_run=True)
        delete_response = app.delete_manifest("m.yaml", dry_run=True)
        secret_response = app.create_registry_secret(
            name="s",
            registry="r",
            username="u",
            password="p",
            dry_run=True,
        )
        scale_response = app.scale_to("ms1", 2, dry_run=True)
        create_response = app.create_pod("ms1", nodeid="n1", dry_run=True)
        delete_pod_response = app.delete_pod("ms1", podid="pod-a", dry_run=True)
        migrate_response = app.migrate_pod(
            "ms1", podid="pod-a", nodeid="n2", dry_run=True
        )
        mapping_response = app.get_pod_node_mapping(
            label_selector="app=ms1", dry_run=True
        )

        assert apply_response["result"] == [{"kind": "Deployment"}]
        assert delete_response["result"] == [{"status": "Success"}]
        assert secret_response["result"] == {"kind": "Secret"}
        assert scale_response["result"] == {"operation": "scale_to"}
        assert create_response["result"] == {"operation": "create_pod"}
        assert delete_pod_response["result"] == {"operation": "delete_pod"}
        assert migrate_response["result"] == {"operation": "migrate_pod"}
        assert mapping_response["result"] == {"ms1": {"pod-a": "node-1"}}

        kubectl.apply_manifest.assert_any_call(str(out_file), dry_run=True)
        kubectl.apply_manifest.assert_any_call("m.yaml", dry_run=True)
        kubectl.delete_manifest.assert_called_once_with("m.yaml", dry_run=True)
        kubectl.create_registry_secret.assert_called_once_with(
            name="s",
            registry="r",
            username="u",
            password="p",
            email=None,
            dry_run=True,
        )
        runtime.scale_to.assert_called_once_with("ms1", 2, dry_run=True)
        runtime.create_pod.assert_called_once_with(
            msid="ms1",
            nodeid="n1",
            dry_run=True,
        )
        runtime.delete_pod.assert_called_once_with(
            msid="ms1",
            podid="pod-a",
            dry_run=True,
        )
        runtime.migrate_pod.assert_called_once_with(
            msid="ms1",
            podid="pod-a",
            nodeid="n2",
            dry_run=True,
        )


def test_pod_manager_groups_pods_locally():
    with patch("k3s_client.api.pods.Kubectl") as mock_kubectl:
        kubectl = mock_kubectl.return_value
        kubectl.get.return_value = (
            "items:\n"
            "- metadata:\n"
            "    name: pod-a\n"
            "    labels:\n"
            "      app: ms1\n"
            "  spec:\n"
            "    nodeName: node-1\n"
            "- metadata:\n"
            "    name: pod-b\n"
            "    labels:\n"
            "      service: ms1\n"
            "  spec:\n"
            "    nodeName: node-2\n"
        )

        manager = PodManager()
        grouped = manager._get_grouped_pod_node_mapping()

        assert grouped == {"ms1": {"pod-a": "node-1", "pod-b": "node-2"}}
        kubectl.get.assert_called_with("pod", label_selector=None)


def test_pod_manager_accepts_direct_dict_payloads():
    with patch("k3s_client.api.pods.Kubectl") as mock_kubectl:
        kubectl = mock_kubectl.return_value
        kubectl.get.return_value = {
            "items": [
                {
                    "metadata": {"name": "pod-a", "labels": {"app": "ms1"}},
                    "spec": {"nodeName": "node-1"},
                },
                {
                    "metadata": {"name": "pod-b", "labels": {"service": "ms1"}},
                    "spec": {},
                },
            ]
        }

        manager = PodManager()

        assert manager._get_grouped_pod_node_mapping() == {
            "ms1": {"pod-a": "node-1", "pod-b": None}
        }


def test_pod_manager_lists_nodes_with_label_selector():
    with patch("k3s_client.api.pods.Kubectl") as mock_kubectl:
        kubectl = mock_kubectl.return_value
        kubectl.get.return_value = {
            "items": [
                {
                    "metadata": {
                        "name": "worker-1",
                        "labels": {"labels.swarmchestrate.eu/ms_id": "sitea"},
                    }
                }
            ]
        }

        manager = PodManager()
        nodes = manager.list_nodes(
            label_selector="labels.swarmchestrate.eu/ms_id=sitea"
        )

        assert nodes[0]["metadata"]["name"] == "worker-1"
        assert (
            nodes[0]["metadata"]["labels"]["labels.swarmchestrate.eu/ms_id"] == "sitea"
        )
        kubectl.get.assert_called_once_with(
            "node",
            label_selector="labels.swarmchestrate.eu/ms_id=sitea",
        )


def test_resource_quantity_parsers_convert_cpu_to_millicores_and_memory_to_bytes():
    assert parse_cpu_quantity("3") == 3000
    assert parse_cpu_quantity("2500m") == 2500
    assert parse_cpu_quantity("0.5") == 500
    assert parse_memory_quantity("512Ki") == 512 * 1024
    assert parse_memory_quantity("2Mi") == 2 * 1024**2
    assert parse_memory_quantity("1Gi") == 1024**3
    assert parse_memory_quantity("2K") == 2000
    assert parse_memory_quantity("3M") == 3_000_000
    assert parse_memory_quantity("4G") == 4_000_000_000


def test_pod_manager_node_capacity_counts_running_and_pending_pods_only():
    ready_node = {
        "metadata": {"name": "worker-1", "labels": {"zone": "east"}},
        "status": {
            "conditions": [{"type": "Ready", "status": "True"}],
            "allocatable": {"cpu": "3", "memory": "8Gi"},
        },
    }
    not_ready_node = {
        "metadata": {"name": "worker-2", "labels": {}},
        "status": {
            "conditions": [{"type": "Ready", "status": "False"}],
            "allocatable": {"cpu": "8", "memory": "32Gi"},
        },
    }
    pod_items = [
        {
            "status": {"phase": "Running"},
            "spec": {
                "nodeName": "worker-1",
                "containers": [
                    {"resources": {"requests": {"cpu": "500m", "memory": "1Gi"}}}
                ],
            },
        },
        {
            "status": {"phase": "Pending"},
            "spec": {
                "nodeName": "worker-1",
                "containers": [
                    {"resources": {"requests": {"cpu": "250m", "memory": "512Mi"}}},
                    {"resources": {"requests": {"cpu": "250m", "memory": "128Mi"}}},
                ],
            },
        },
        {
            "status": {"phase": "Succeeded"},
            "spec": {
                "nodeName": "worker-1",
                "containers": [
                    {"resources": {"requests": {"cpu": "2", "memory": "4Gi"}}}
                ],
            },
        },
        {
            "status": {"phase": "Failed"},
            "spec": {
                "nodeName": "worker-1",
                "containers": [
                    {"resources": {"requests": {"cpu": "2", "memory": "4Gi"}}}
                ],
            },
        },
        {
            "status": {"phase": "Pending"},
            "spec": {
                "nodeName": "worker-2",
                "containers": [
                    {"resources": {"requests": {"cpu": "2", "memory": "4Gi"}}}
                ],
            },
        },
    ]

    with patch("k3s_client.api.pods.Kubectl") as mock_kubectl:
        mock_kubectl.return_value.get.side_effect = [
            {"items": [ready_node, not_ready_node]},
            {"items": pod_items},
        ]
        manager = PodManager()

        capacities = manager.get_node_capacity(label_selector="zone=east")

    assert capacities == [
        {
            "name": "worker-1",
            "labels": {"zone": "east"},
            "allocatable": {"cpu_millicores": 3000, "memory_bytes": 8 * 1024**3},
            "requested": {
                "cpu_millicores": 1000,
                "memory_bytes": 1_744_830_464,
            },
            "free": {"cpu_millicores": 2000, "memory_bytes": 6_845_104_128},
        }
    ]
    mock_kubectl.return_value.get.assert_has_calls(
        [call("node", label_selector="zone=east"), call("pod", label_selector=None)]
    )


def test_pod_manager_find_best_fit_node_selects_smallest_fit_and_returns_none():
    capacities = [
        {
            "name": "large",
            "allocatable": {"cpu_millicores": 8000, "memory_bytes": 8 * 1024**3},
            "free": {"cpu_millicores": 6000, "memory_bytes": 6 * 1024**3},
        },
        {
            "name": "small",
            "allocatable": {"cpu_millicores": 2000, "memory_bytes": 2 * 1024**3},
            "free": {"cpu_millicores": 1500, "memory_bytes": 1536 * 1024**2},
        },
    ]
    with patch("k3s_client.api.pods.Kubectl"):
        manager = PodManager()
    with patch.object(manager, "get_node_capacity", return_value=capacities):
        selected = manager.find_best_fit_node({"cpu": "500m", "memory": "512Mi"})
        no_fit = manager.find_best_fit_node({"cpu": "7", "memory": "7Gi"})

    assert selected["name"] == "small"
    assert no_fit is None


@pytest.mark.parametrize("operation", ["create_pod", "migrate_pod"])
def test_optimizer_runtime_rejects_insufficient_capacity_before_mutations(operation):
    container_spec = {
        "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}}
    }
    with (
        patch(
            "k3s_client.api.optimizer_runtime.get_microservice_container_spec",
            return_value=container_spec,
        ),
        patch("k3s_client.api.optimizer_runtime.PodManager") as mock_pod_manager,
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
        patch.object(OptimizerRuntimeClient, "_pod_document") as mock_pod_document,
    ):
        mock_pod_manager.return_value.get_node_capacity.return_value = [
            {
                "name": "physical-worker",
                "labels": {manifest_utils.NODE_RESOURCE_LABEL_KEY: "worker-2"},
                "free": {"cpu_millicores": 250, "memory_bytes": 512 * 1024**2},
            }
        ]
        client = OptimizerRuntimeClient()

        with pytest.raises(K3sClientError) as error:
            if operation == "create_pod":
                client.create_pod("productpage", "worker-2")
            else:
                client.migrate_pod(
                    "productpage", podid="pod-a", nodeid="worker-2"
                )

    assert "Insufficient capacity on target node 'physical-worker'" in str(error.value)
    assert "requested cpu=500m, memory=1073741824B" in str(error.value)
    assert "available cpu=250m, memory=536870912B" in str(error.value)
    assert mock_kubectl.method_calls == []
    mock_pod_document.assert_not_called()


@pytest.mark.parametrize("operation", ["create_pod", "migrate_pod"])
@pytest.mark.parametrize("node_state", ["missing", "not-ready"])
def test_optimizer_runtime_rejects_missing_or_not_ready_target(operation, node_state):
    nodes = []
    if node_state == "not-ready":
        nodes.append({
            "metadata": {
                "name": "worker-2",
                "labels": {manifest_utils.NODE_RESOURCE_LABEL_KEY: "audio-class-3"},
            },
            "status": {"conditions": [{"type": "Ready", "status": "False"}]},
        })
    with (
        patch("k3s_client.api.optimizer_runtime.get_microservice_container_spec",
              return_value={}),
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
        patch("k3s_client.api.pods.Kubectl") as mock_pod_kubectl,
    ):
        mock_pod_kubectl.return_value.get.side_effect = [
            {"items": nodes}, {"items": []}
        ]
        client = OptimizerRuntimeClient()
        with pytest.raises(K3sClientError, match="not found or not Ready") as error:
            if operation == "create_pod":
                client.create_pod("audio-class", "audio-class-3")
            else:
                client.migrate_pod("audio-class", "pod-a", "audio-class-3")

        assert str(error.value) == "Target node 'audio-class-3' not found or not Ready"
        assert mock_kubectl.return_value.method_calls == []


@pytest.mark.parametrize("operation", ["create_pod", "migrate_pod"])
def test_optimizer_runtime_rejects_wrong_sat_label_before_mutations(operation):
    container_spec = {
        "affinity": manifest_utils.build_node_affinity(
            manifest_utils.NODE_AFFINITY_LABEL_KEY, "audio-class"
        ),
        "resources": {"requests": {"cpu": "3"}},
    }
    with (
        patch("k3s_client.api.optimizer_runtime.get_microservice_container_spec",
              return_value=container_spec),
        patch("k3s_client.api.optimizer_runtime.PodManager") as mock_pod_manager,
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
    ):
        mock_pod_manager.return_value.get_node_capacity.return_value = [{
            "name": "physical-worker",
            "labels": {
                manifest_utils.NODE_RESOURCE_LABEL_KEY: "audio-class-3",
                manifest_utils.NODE_AFFINITY_LABEL_KEY: "other-service",
            },
            "free": {"cpu_millicores": 0, "memory_bytes": 0},
        }]
        client = OptimizerRuntimeClient()
        with pytest.raises(K3sClientError, match="labels.swarmchestrate.eu/ms_id"):
            if operation == "create_pod":
                client.create_pod("audio-class", "audio-class-3")
            else:
                client.migrate_pod("audio-class", "pod-a", "audio-class-3")
        assert mock_kubectl.return_value.method_calls == []


@pytest.mark.parametrize(
    ("operator", "values", "labels", "matches"),
    [
        ("In", ["edge"], {"tier": "edge"}, True),
        ("In", ["edge"], {"tier": "cloud"}, False),
        ("In", ["edge"], {}, False),
        ("NotIn", ["edge"], {"tier": "cloud"}, True),
        ("NotIn", ["edge"], {"tier": "edge"}, False),
        ("NotIn", ["edge"], {}, True),
        ("Exists", [], {"tier": "edge"}, True),
        ("Exists", [], {}, False),
        ("DoesNotExist", [], {}, True),
        ("DoesNotExist", [], {"tier": "edge"}, False),
    ],
)
def test_optimizer_runtime_checks_sat_label_operators(operator, values, labels, matches):
    expression = {"key": "tier", "operator": operator, "values": values}
    affinity = {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {
        "nodeSelectorTerms": [{"matchExpressions": [expression]}]
    }}}
    labels = {**labels, manifest_utils.NODE_RESOURCE_LABEL_KEY: "audio-class-3"}
    with (
        patch("k3s_client.api.optimizer_runtime.PodManager") as mock_pod_manager,
        patch("k3s_client.api.optimizer_runtime.Kubectl"),
    ):
        mock_pod_manager.return_value.get_node_capacity.return_value = [{
            "name": "physical-worker", "labels": labels,
            "free": {"cpu_millicores": 1000, "memory_bytes": 1024},
        }]
        client = OptimizerRuntimeClient()
        if matches:
            client._check_node_capacity("audio-class-3", {"affinity": affinity})
        else:
            with pytest.raises(K3sClientError, match="tier"):
                client._check_node_capacity("audio-class-3", {"affinity": affinity})


@pytest.mark.parametrize("operation", ["create_pod", "migrate_pod"])
@pytest.mark.parametrize("nodeid", ["audio_class_3", "audio-class-3"])
def test_optimizer_runtime_normalizes_target_resource_name(operation, nodeid):
    container_spec = {
        "image": "nginx",
        "resources": {"requests": {"cpu": "500m"}},
        "affinity": manifest_utils.build_node_affinity(
            manifest_utils.NODE_AFFINITY_LABEL_KEY, "audio-class"
        ),
    }
    with (
        patch(
            "k3s_client.api.optimizer_runtime.get_microservice_container_spec",
            return_value=container_spec,
        ),
        patch("k3s_client.api.optimizer_runtime.PodManager") as mock_pod_manager,
        patch("k3s_client.api.optimizer_runtime.Kubectl"),
        patch.object(
            OptimizerRuntimeClient,
            "_pod_document",
            return_value={"metadata": {"ownerReferences": [
                {"kind": "Deployment", "name": "audio-class-pinned-old"}
            ]}},
        ),
        patch.object(OptimizerRuntimeClient, "_apply_manifest") as mock_apply,
    ):
        mock_pod_manager.return_value.get_node_capacity.return_value = [{
            "name": "physical-worker",
            "labels": {
                manifest_utils.NODE_RESOURCE_LABEL_KEY: "audio-class-3",
                manifest_utils.NODE_AFFINITY_LABEL_KEY: "audio-class",
            },
            "free": {"cpu_millicores": 1000, "memory_bytes": 1024},
        }]
        client = OptimizerRuntimeClient()
        if operation == "create_pod":
            result = client.create_pod("audio-class", nodeid)
            deployment_name = result["deployment_name"]
        else:
            result = client.migrate_pod("audio-class", "pod-a", nodeid)
            deployment_name = result["result"]["deployment_name"]

    assert result["nodeid"] == "audio-class-3"
    if nodeid != "audio-class-3":
        assert result["requested_nodeid"] == nodeid
    else:
        assert "requested_nodeid" not in result
    assert deployment_name == "audio-class-pinned-audio-class-3"
    manifest = mock_apply.call_args.args[0]
    assert manifest["metadata"]["name"] == deployment_name
    terms = manifest["spec"]["template"]["spec"]["affinity"]["nodeAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"
    ]["nodeSelectorTerms"]
    assert terms[0]["matchExpressions"][0] == {
        "key": manifest_utils.NODE_RESOURCE_LABEL_KEY,
        "operator": "In",
        "values": ["audio-class-3"],
    }


def test_optimizer_runtime_uses_swarm_optimiser_field_manager_and_pinned_affinity():
    container_spec = {
        "labels": {"app": "productpage", "service": "productpage"},
        "app_label": "productpage",
        "service_label": "productpage",
        "version": "v1",
        "image": "nginx:1.27",
        "command": [],
        "args": [],
        "env_list": [],
        "container_ports": [],
        "volume_mounts": [],
        "volumes": [],
        "annotations": {},
        "node_selector": {},
        "service_account": None,
        "image_pull_secret": None,
        "enable_service_links": False,
    }

    with (
        patch(
            "k3s_client.api.optimizer_runtime.get_microservice_container_spec",
            return_value=container_spec,
        ),
        patch("k3s_client.api.optimizer_runtime.PodManager") as mock_pod_manager,
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
    ):
        mock_pod_manager.return_value.get_node_capacity.return_value = [
            {
                "name": "worker-2",
                "labels": {manifest_utils.NODE_RESOURCE_LABEL_KEY: "worker-2"},
                "free": {"cpu_millicores": 4000, "memory_bytes": 8 * 1024**3},
            }
        ]
        kubectl = mock_kubectl.return_value
        kubectl.apply_manifest.return_value = "applied"
        client = OptimizerRuntimeClient()
        result = client.create_pod("productpage", "worker-2")

        assert result["deployment_name"] == "productpage-pinned-worker-2"
        kubectl.apply_manifest.assert_called_once()
        assert (
            kubectl.apply_manifest.call_args.kwargs["field_manager"]
            == "swarm-optimiser"
        )

        manifest = manifest_utils.build_pinned_pod_manifest(
            "productpage", "worker-2", container_spec
        )
        affinity = manifest["spec"]["template"]["spec"]["affinity"]["nodeAffinity"]
        required = affinity["requiredDuringSchedulingIgnoredDuringExecution"]
        expr = required["nodeSelectorTerms"][0]["matchExpressions"][0]
        assert expr["key"] == manifest_utils.NODE_RESOURCE_LABEL_KEY
        assert expr["values"] == ["worker-2"]


def test_optimizer_runtime_scales_before_delete_without_pod_delete_call():
    with (
        patch(
            "k3s_client.api.optimizer_runtime.get_microservice_deployment"
        ) as mock_dep,
        patch("k3s_client.api.optimizer_runtime.PodManager"),
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
    ):
        kubectl = mock_kubectl.return_value
        mock_dep.return_value = {"spec": {"replicas": 3}}
        kubectl.scale.return_value = "scaled"

        client = OptimizerRuntimeClient()
        result = client.delete_pod("productpage")

        assert result["scaled_to"] == 2
        mock_dep.assert_called_once_with("productpage")
        kubectl.scale.assert_called_once_with(
            "deployment",
            "productpage",
            2,
            dry_run=False,
        )
        kubectl.delete.assert_not_called()


def test_optimizer_runtime_scales_before_delete_and_recreates_on_migrate():
    container_spec = {
        "labels": {"app": "productpage", "service": "productpage"},
        "app_label": "productpage",
        "service_label": "productpage",
        "version": "v1",
        "image": "nginx:1.27",
        "command": [],
        "args": [],
        "env_list": [],
        "container_ports": [],
        "volume_mounts": [],
        "volumes": [],
        "annotations": {},
        "node_selector": {},
        "service_account": None,
        "image_pull_secret": None,
        "enable_service_links": False,
    }
    pod_doc = {
        "metadata": {
            "name": "pod-a",
            "ownerReferences": [{"kind": "Deployment", "name": "productpage-v1"}],
        },
        "spec": {"nodeName": "node-1"},
    }

    with (
        patch(
            "k3s_client.api.optimizer_runtime.get_microservice_deployment"
        ) as mock_dep,
        patch(
            "k3s_client.api.optimizer_runtime.get_microservice_container_spec",
            return_value=container_spec,
        ),
        patch("k3s_client.api.optimizer_runtime.PodManager") as mock_pod_manager,
        patch.object(OptimizerRuntimeClient, "_pod_document", return_value=pod_doc),
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
    ):
        mock_pod_manager.return_value.get_node_capacity.return_value = [
            {
                "name": "worker-2",
                "labels": {manifest_utils.NODE_RESOURCE_LABEL_KEY: "worker-2"},
                "free": {"cpu_millicores": 4000, "memory_bytes": 8 * 1024**3},
            }
        ]
        kubectl = mock_kubectl.return_value
        mock_dep.return_value = {"spec": {"replicas": 3}}
        kubectl.scale.return_value = "scaled"
        kubectl.delete.return_value = "deleted"
        kubectl.apply_manifest.return_value = "applied"

        client = OptimizerRuntimeClient()
        delete_result = client.delete_pod("productpage", podid="pod-a")
        migrate_result = client.migrate_pod(
            "productpage", podid="pod-a", nodeid="worker-2"
        )

        assert delete_result["scaled_to"] == 2
        assert (
            migrate_result["result"]["deployment_name"] == "productpage-pinned-worker-2"
        )
        assert kubectl.method_calls == [
            call.annotate(
                "pod",
                "pod-a",
                "controller.kubernetes.io/pod-deletion-cost",
                "-999",
                dry_run=False,
            ),
            call.scale("deployment", "productpage", 2, dry_run=False),
            call.annotate(
                "pod",
                "pod-a",
                "controller.kubernetes.io/pod-deletion-cost",
                "-999",
                dry_run=False,
            ),
            call.scale("deployment", "productpage", 2, dry_run=False),
            call.apply_manifest(
                ANY,
                field_manager="swarm-optimiser",
                dry_run=False,
            ),
        ]
        kubectl.delete.assert_not_called()

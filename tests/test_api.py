from inspect import signature
from unittest.mock import ANY, call, patch

from k3s_client.api import applications as applications_module
from k3s_client.api.applications import ApplicationManager
from k3s_client.api.optimizer_runtime import OptimizerRuntimeClient
from k3s_client.api.pods import PodManager
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
        pod_manager.get_grouped_pod_node_mapping.return_value = {
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
        pod_manager.get_grouped_pod_node_mapping.assert_called_once_with(
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
        pod_manager.get_grouped_pod_node_mapping.return_value = {
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


def test_pod_manager_lists_and_groups_pods_locally():
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
        pods = manager.list_pods()
        grouped = manager.get_grouped_pod_node_mapping()

        assert [pod["metadata"]["name"] for pod in pods] == ["pod-a", "pod-b"]
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

        assert manager.get_grouped_pod_node_mapping() == {
            "ms1": {"pod-a": "node-1", "pod-b": None}
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
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
    ):
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
        assert expr["key"] == manifest_utils.NODE_AFFINITY_LABEL_KEY
        assert expr["values"] == ["worker-2"]


def test_optimizer_runtime_scales_before_delete_without_pod_delete_call():
    with (
        patch(
            "k3s_client.api.optimizer_runtime.get_microservice_deployment"
        ) as mock_dep,
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
        patch.object(OptimizerRuntimeClient, "_pod_document", return_value=pod_doc),
        patch("k3s_client.api.optimizer_runtime.Kubectl") as mock_kubectl,
    ):
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

import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.rest import ApiException
from kubernetes.config.config_exception import ConfigException

from k3s_client.cli.kubectl import Kubectl
from k3s_client.exceptions import K3sClientError


@pytest.fixture
def kubectl_and_mocks():
    with (
        patch("k3s_client.cli.kubectl.config.load_incluster_config") as load_incluster,
        patch("k3s_client.cli.kubectl.config.load_kube_config") as load_kube_config,
        patch("k3s_client.cli.kubectl.client.ApiClient") as api_client_cls,
        patch("k3s_client.cli.kubectl.dynamic.DynamicClient") as dynamic_client_cls,
        patch("k3s_client.cli.kubectl.client.AppsV1Api") as apps_v1_cls,
    ):
        api_client = api_client_cls.return_value
        api_client.sanitize_for_serialization.side_effect = lambda payload: payload

        kubectl = Kubectl(kubeconfig="/tmp/kubeconfig")
        yield {
            "kubectl": kubectl,
            "load_incluster": load_incluster,
            "load_kube_config": load_kube_config,
            "dynamic_client": dynamic_client_cls.return_value,
            "apps_v1": apps_v1_cls.return_value,
        }


def test_init_falls_back_to_kubeconfig_when_incluster_unavailable():
    with (
        patch(
            "k3s_client.cli.kubectl.config.load_incluster_config",
            side_effect=ConfigException("no in-cluster config"),
        ) as load_incluster,
        patch("k3s_client.cli.kubectl.config.load_kube_config") as load_kube_config,
        patch("k3s_client.cli.kubectl.client.ApiClient"),
        patch("k3s_client.cli.kubectl.dynamic.DynamicClient"),
        patch("k3s_client.cli.kubectl.client.AppsV1Api"),
    ):
        Kubectl(kubeconfig="/tmp/custom-kubeconfig")

    load_incluster.assert_called_once_with()
    load_kube_config.assert_called_once_with("/tmp/custom-kubeconfig")


def test_apply_manifest_uses_default_field_manager(tmp_path, kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\n",
        encoding="utf-8",
    )

    with patch.object(
        kubectl, "_apply_document", return_value="ConfigMap/cfg configured"
    ) as apply_doc:
        result = kubectl.apply_manifest(str(manifest))

    assert result == "ConfigMap/cfg configured"
    apply_doc.assert_called_once()
    assert apply_doc.call_args.args[1] == "tosca-controller"
    assert apply_doc.call_args.kwargs["dry_run"] is False


def test_apply_manifest_accepts_custom_field_manager(tmp_path, kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\n",
        encoding="utf-8",
    )

    with patch.object(
        kubectl, "_apply_document", return_value="ConfigMap/cfg configured"
    ) as apply_doc:
        kubectl.apply_manifest(str(manifest), field_manager="swarm-optimiser")

    assert apply_doc.call_args.args[1] == "swarm-optimiser"


def test_apply_manifest_dry_run_forwards_flag(tmp_path, kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\n",
        encoding="utf-8",
    )

    with patch.object(
        kubectl, "_apply_document", return_value={"kind": "ConfigMap"}
    ) as apply_doc:
        result = kubectl.apply_manifest(str(manifest), dry_run=True)

    assert isinstance(result, list)
    assert apply_doc.call_args.kwargs["dry_run"] is True


def test_delete_manifest_dry_run_forwards_flag(tmp_path, kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\n",
        encoding="utf-8",
    )

    with patch.object(
        kubectl, "_delete_document", return_value={"status": "Success"}
    ) as delete_doc:
        result = kubectl.delete_manifest(str(manifest), dry_run=True)

    assert isinstance(result, list)
    assert delete_doc.call_args.kwargs["dry_run"] is True


def test_create_registry_secret_builds_dockerconfigjson_and_applies(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]

    with patch.object(
        kubectl, "_apply_document", return_value="Secret/pull-secret configured"
    ) as apply_doc:
        result = kubectl.create_registry_secret(
            name="pull-secret",
            registry="index.docker.io",
            username="user",
            password="pass",
            email="user@example.com",
        )

    assert result == "Secret/pull-secret configured"
    body = apply_doc.call_args.args[0]
    assert body["kind"] == "Secret"
    assert body["type"] == "kubernetes.io/dockerconfigjson"
    encoded = body["data"][".dockerconfigjson"]
    decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
    auth = decoded["auths"]["index.docker.io"]
    assert auth["username"] == "user"
    assert auth["password"] == "pass"
    assert auth["email"] == "user@example.com"
    assert auth["auth"] == base64.b64encode(b"user:pass").decode("utf-8")
    assert apply_doc.call_args.kwargs["field_manager"] == "tosca-controller"
    assert apply_doc.call_args.kwargs["dry_run"] is False


def test_create_registry_secret_dry_run_forwards_flag(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]

    with patch.object(
        kubectl, "_apply_document", return_value={"kind": "Secret"}
    ) as apply_doc:
        result = kubectl.create_registry_secret(
            name="pull-secret",
            registry="index.docker.io",
            username="user",
            password="pass",
            dry_run=True,
        )

    assert isinstance(result, dict)
    assert apply_doc.call_args.kwargs["dry_run"] is True


def test_annotate_patches_resource_metadata(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    resource = MagicMock()
    resource.namespaced = True

    with patch.object(kubectl, "_resource_for_type", return_value=resource):
        result = kubectl.annotate(
            "pod",
            "pod-a",
            "controller.kubernetes.io/pod-deletion-cost",
            "-999",
        )

    assert result == "pod/pod-a annotated"
    resource.patch.assert_called_once_with(
        name="pod-a",
        namespace="default",
        body={
            "metadata": {
                "annotations": {"controller.kubernetes.io/pod-deletion-cost": "-999"}
            }
        },
        content_type="application/merge-patch+json",
    )


def test_delete_by_label_default_includes_ingress(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]

    with patch.object(
        kubectl, "_delete_by_selector", return_value=1
    ) as delete_selector:
        result = kubectl.delete_by_label("app=my-app")

    assert result.startswith("Deleted ")
    called_types = [args[0] for args, _ in delete_selector.call_args_list]
    assert "ingress" in called_types


def test_delete_by_label_dry_run_forwards_flag(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]

    with patch.object(
        kubectl,
        "_delete_by_selector",
        return_value={"resource_type": "pod", "count": 1, "responses": []},
    ) as delete_selector:
        result = kubectl.delete_by_label(
            "app=my-app", resource_types=["pod"], dry_run=True
        )

    assert isinstance(result, dict)
    assert delete_selector.call_args.kwargs["dry_run"] is True


def test_scale_deployment_uses_apps_api(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    apps_v1 = kubectl_and_mocks["apps_v1"]

    result = kubectl.scale("deployment", "productpage", 3)

    assert result == "deployment/productpage scaled"
    apps_v1.patch_namespaced_deployment_scale.assert_called_once_with(
        name="productpage",
        namespace="default",
        body={"spec": {"replicas": 3}},
    )


def test_scale_deployment_dry_run_uses_all(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    apps_v1 = kubectl_and_mocks["apps_v1"]
    apps_v1.patch_namespaced_deployment_scale.return_value = {"kind": "Scale"}

    result = kubectl.scale("deployment", "productpage", 3, dry_run=True)

    assert isinstance(result, dict)
    apps_v1.patch_namespaced_deployment_scale.assert_called_once_with(
        name="productpage",
        namespace="default",
        body={"spec": {"replicas": 3}},
        dry_run="All",
    )


def test_get_serializes_yaml_for_named_resource(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    resource = MagicMock()
    resource.namespaced = True
    resource.get.return_value = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "pod-a"},
    }

    with patch.object(kubectl, "_resource_for_type", return_value=resource):
        result = kubectl.get("pod", name="pod-a")

    assert "kind: Pod" in result
    resource.get.assert_called_once_with(namespace="default", name="pod-a")


def test_get_falls_back_when_sdk_serialization_raises_attribute_error(
    kubectl_and_mocks,
):
    kubectl = kubectl_and_mocks["kubectl"]
    resource = MagicMock()
    resource.namespaced = True
    resource.get.return_value = MagicMock(
        to_dict=MagicMock(
            return_value={
                "items": [
                    {"metadata": {"name": "pod-a"}, "spec": {"nodeName": "node-1"}}
                ]
            }
        )
    )
    kubectl.api_client.sanitize_for_serialization.side_effect = AttributeError(
        "'NoneType' object has no attribute 'items'"
    )

    with patch.object(kubectl, "_resource_for_type", return_value=resource):
        result = kubectl.get("pod")

    assert "nodeName: node-1" in result
    resource.get.assert_called_once_with(namespace="default")


def test_annotate_dry_run_falls_back_when_sdk_serialization_raises_attribute_error(
    kubectl_and_mocks,
):
    kubectl = kubectl_and_mocks["kubectl"]
    resource = MagicMock()
    resource.namespaced = True
    resource.patch.return_value = MagicMock(
        to_dict=MagicMock(return_value={"kind": "Pod", "metadata": {"name": "pod-a"}})
    )
    kubectl.api_client.sanitize_for_serialization.side_effect = AttributeError(
        "'NoneType' object has no attribute 'items'"
    )

    with patch.object(kubectl, "_resource_for_type", return_value=resource):
        result = kubectl.annotate(
            "pod",
            "pod-a",
            "controller.kubernetes.io/pod-deletion-cost",
            "-999",
            dry_run=True,
        )

    assert result == {"kind": "Pod", "metadata": {"name": "pod-a"}}


def test_apply_document_dry_run_falls_back_when_sdk_serialization_raises_attribute_error(
    kubectl_and_mocks,
):
    kubectl = kubectl_and_mocks["kubectl"]
    resource = MagicMock()
    resource.namespaced = True
    resource.patch.side_effect = ApiException(status=404, reason="not found")
    resource.create.return_value = MagicMock(
        to_dict=MagicMock(
            return_value={"kind": "Deployment", "metadata": {"name": "pinned"}}
        )
    )
    kubectl.api_client.sanitize_for_serialization.side_effect = AttributeError(
        "'NoneType' object has no attribute 'items'"
    )

    with patch.object(kubectl, "_resource_for_gvk", return_value=resource):
        result = kubectl._apply_document(
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "pinned"},
            },
            field_manager="swarm-optimiser",
            dry_run=True,
        )

    assert result == {"kind": "Deployment", "metadata": {"name": "pinned"}}


def test_dry_run_api_exception_propagates_as_k3s_client_error(kubectl_and_mocks):
    kubectl = kubectl_and_mocks["kubectl"]
    resource = MagicMock()
    resource.namespaced = True
    resource.patch.side_effect = ApiException(status=403, reason="forbidden")

    with (
        patch.object(kubectl, "_resource_for_type", return_value=resource),
        pytest.raises(K3sClientError),
    ):
        kubectl.annotate(
            "pod",
            "pod-a",
            "controller.kubernetes.io/pod-deletion-cost",
            "-999",
            dry_run=True,
        )

from unittest.mock import patch, MagicMock
from k3s_client.api.pods import PodManager


def test_pod_manager_initialization_sets_v1_attribute():
    """PodManager should initialize without kubeconfig and have v1 attribute."""
    with patch("k3s_client.api.pods.load_kubeconfig") as mock_load:
        mock_load.return_value = None
        pm = PodManager()
        assert hasattr(pm, "v1"), "PodManager should have v1 attribute"


def test_list_pods_returns_list_of_pod_names():
    """list_pods should return pod names from mocked CoreV1Api."""
    with (
        patch("k3s_client.api.pods.load_kubeconfig"),
        patch("k3s_client.api.pods.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value

        # Mock two pods
        pod1 = MagicMock()
        pod1.metadata = MagicMock()
        pod1.metadata.name = "pod1"

        pod2 = MagicMock()
        pod2.metadata = MagicMock()
        pod2.metadata.name = "pod2"

        mock_instance.list_namespaced_pod.return_value.items = [pod1, pod2]

        pm = PodManager()
        pods = pm.list_pods(namespace="default")
        assert pods == ["pod1", "pod2"]


def test_launch_pod_creates_pod_with_correct_parameters():
    """launch_pod should call create_namespaced_pod with correct arguments."""
    with (
        patch("k3s_client.api.pods.load_kubeconfig"),
        patch("k3s_client.api.pods.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value
        mock_instance.create_namespaced_pod.return_value = None

        pm = PodManager()
        result = pm.launch_pod(
            name="mypod",
            image="nginx",
            pod_labels={"app": "test"},
            namespace="default",
        )
        mock_instance.create_namespaced_pod.assert_called_once()
        assert "mypod" in result


def test_launch_pod_on_specific_node():
    """launch_pod should set nodeName when node_name is specified."""
    with (
        patch("k3s_client.api.pods.load_kubeconfig"),
        patch("k3s_client.api.pods.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value
        mock_instance.create_namespaced_pod.return_value = None

        pm = PodManager()
        result = pm.launch_pod(
            name="mypod",
            image="nginx",
            node_name="node-1",
            namespace="default",
        )
        mock_instance.create_namespaced_pod.assert_called_once()
        # Check that node_name was set in the pod spec
        call_args = mock_instance.create_namespaced_pod.call_args
        pod_body = call_args[1]["body"]  # kwargs
        assert pod_body.spec.node_name == "node-1"
        assert "node-1" in result


def test_destroy_pod_deletes_named_pod():
    """destroy_pod should call delete_namespaced_pod for a single named pod."""
    with (
        patch("k3s_client.api.pods.load_kubeconfig"),
        patch("k3s_client.api.pods.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value
        mock_instance.delete_namespaced_pod.return_value = None

        pm = PodManager()
        result = pm.destroy_pod(pod_name="mypod", namespace="default")
        mock_instance.delete_namespaced_pod.assert_called_once_with(
            name="mypod", namespace="default"
        )
        assert "mypod" in result


def test_destroy_pod_deletes_multiple_pods_by_label_selector():
    """destroy_pod should delete all pods matching the given label selector."""
    with (
        patch("k3s_client.api.pods.load_kubeconfig"),
        patch("k3s_client.api.pods.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value

        # Mock pods returned by list_namespaced_pod
        pod1 = MagicMock()
        pod1.metadata = MagicMock()
        pod1.metadata.name = "pod1"

        pod2 = MagicMock()
        pod2.metadata = MagicMock()
        pod2.metadata.name = "pod2"

        mock_instance.list_namespaced_pod.return_value.items = [pod1, pod2]
        mock_instance.delete_namespaced_pod.return_value = None

        pm = PodManager()
        result = pm.destroy_pod(pod_label="app=test", namespace="default")
        # delete_namespaced_pod should be called twice
        assert mock_instance.delete_namespaced_pod.call_count == 2
        assert "app=test" in result


def test_create_registry_secret_for_application():
    """create_registry_secret should call create_namespaced_secret via PodManager API."""
    from k3s_client.api.applications import ApplicationManager

    with (
        patch("k3s_client.api.applications.load_kubeconfig"),
        patch("k3s_client.api.applications.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value
        mock_instance.create_namespaced_secret.return_value = None

        app = ApplicationManager()
        result = app.create_registry_secret(
            name="my-secret",
            namespace="default",
            registry="my-registry.local",
            username="user",
            password="pass",
            email="test@example.com",
            replace=False,
        )

        mock_instance.create_namespaced_secret.assert_called_once()
        assert "created" in result


def test_application_get_pod_node_mapping():
    """ApplicationManager.get_pod_node_mapping should return pod to node mapping."""
    from k3s_client.api.applications import ApplicationManager

    with (
        patch("k3s_client.api.applications.load_kubeconfig"),
        patch("k3s_client.api.applications.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value

        # Mock pods with node assignments
        pod1 = MagicMock()
        pod1.metadata = MagicMock()
        pod1.metadata.name = "pod1"
        pod1.spec = MagicMock()
        pod1.spec.node_name = "node-1"

        pod2 = MagicMock()
        pod2.metadata = MagicMock()
        pod2.metadata.name = "pod2"
        pod2.spec = MagicMock()
        pod2.spec.node_name = "node-2"

        mock_instance.list_namespaced_pod.return_value.items = [pod1, pod2]

        app = ApplicationManager()
        mapping = app.get_pod_node_mapping(namespace="default")
        assert mapping == {"pod1": "node-1", "pod2": "node-2"}
    """get_pod_node_mapping should return pod to node mapping."""
    with (
        patch("k3s_client.api.pods.load_kubeconfig"),
        patch("k3s_client.api.pods.client.CoreV1Api") as mock_api,
    ):
        mock_instance = mock_api.return_value

        # Mock pods with node assignments
        pod1 = MagicMock()
        pod1.metadata = MagicMock()
        pod1.metadata.name = "pod1"
        pod1.spec = MagicMock()
        pod1.spec.node_name = "node-1"

        pod2 = MagicMock()
        pod2.metadata = MagicMock()
        pod2.metadata.name = "pod2"
        pod2.spec = MagicMock()
        pod2.spec.node_name = "node-2"

        mock_instance.list_namespaced_pod.return_value.items = [pod1, pod2]

        pm = PodManager()
        mapping = pm.get_pod_node_mapping(namespace="default")
        assert mapping == {"pod1": "node-1", "pod2": "node-2"}

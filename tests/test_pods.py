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

import logging
from unittest.mock import patch, MagicMock
from k3s_client.api.pods import PodManager
from k3s_client.exceptions import K3sClientError

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_pod_manager_init_loads_config():
    """PodManager can be initialized without errors."""
    with patch("k3s_client.api.pods.load_kubeconfig") as mock_load:
        mock_load.return_value = None
        pm = PodManager(kubeconfig_path=None)
        assert hasattr(pm, "v1"), "PodManager should have v1 attribute"


def test_list_pods_returns_mocked_list():
    """list_pods returns pod names from the mocked CoreV1Api."""
    with patch("k3s_client.api.pods.client.CoreV1Api") as mock_api:
        mock_instance = mock_api.return_value
        mock_instance.list_namespaced_pod.return_value.items = [
            MagicMock(metadata=MagicMock(name="metadata", **{"name": "pod1"})),
            MagicMock(metadata=MagicMock(name="metadata", **{"name": "pod2"})),
        ]

        pm = PodManager()
        pods = pm.list_pods(namespace="default")
        assert pods == ["pod1", "pod2"], "Should return mocked pod names"


def test_launch_pod_calls_create_namespaced_pod():
    """launch_pod calls CoreV1Api.create_namespaced_pod."""
    with patch("k3s_client.api.pods.client.CoreV1Api") as mock_api:
        mock_instance = mock_api.return_value
        mock_instance.create_namespaced_pod.return_value = None

        pm = PodManager()
        result = pm.launch_pod(name="test-pod", image="busybox")
        mock_instance.create_namespaced_pod.assert_called_once()
        assert "Pod test-pod launched successfully" == result


def test_destroy_pod_deletes_single_pod():
    """destroy_pod calls delete_namespaced_pod for a named pod."""
    with patch("k3s_client.api.pods.client.CoreV1Api") as mock_api:
        mock_instance = mock_api.return_value
        mock_instance.delete_namespaced_pod.return_value = None

        pm = PodManager()
        result = pm.destroy_pod(pod_name="pod1", namespace="default")
        mock_instance.delete_namespaced_pod.assert_called_once_with(
            name="pod1", namespace="default"
        )
        assert result == "Pod pod1 deleted successfully"


def test_destroy_pod_deletes_by_label_selector():
    """destroy_pod deletes multiple pods matching a label selector."""
    with patch("k3s_client.api.pods.client.CoreV1Api") as mock_api:
        mock_instance = mock_api.return_value
        # Mock list_namespaced_pod to return two pods
        pod1 = MagicMock(metadata=MagicMock(name="metadata", **{"name": "pod1"}))
        pod2 = MagicMock(metadata=MagicMock(name="metadata", **{"name": "pod2"}))
        mock_instance.list_namespaced_pod.return_value.items = [pod1, pod2]

        pm = PodManager()
        result = pm.destroy_pod(pod_label="app=test", namespace="default")
        assert mock_instance.delete_namespaced_pod.call_count == 2
        assert "Pods deleted with label: app=test" == result
from kubernetes import config
from kubernetes.config.config_exception import ConfigException
import logging

logger = logging.getLogger(__name__)


def load_kubeconfig(path=None):
    """Load kubeconfig from file or in-cluster, fallback to default file."""
    try:
        if path:
            config.load_kube_config(config_file=path)
            logger.debug("Loaded kubeconfig from %s", path)
        else:
            try:
                config.load_incluster_config()
                logger.debug("Loaded in-cluster kubeconfig")
            except ConfigException:
                config.load_kube_config()
                logger.debug("Loaded default kubeconfig (~/.kube/config)")
    except Exception as e:
        logger.exception("Failed to load kubeconfig")
        raise RuntimeError(f"Failed to load kubeconfig: {e}")

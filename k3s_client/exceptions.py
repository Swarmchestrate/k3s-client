# k3s_client/exceptions.py


class K3sClientError(Exception):
    """Base exception for all k3s-client library errors."""


class DeploymentError(K3sClientError):
    """Raised for deployment-specific errors."""


class ServiceError(K3sClientError):
    """Raised for service-specific errors."""


class RegistrySecretError(K3sClientError):
    """Raised for Docker registry secret issues."""


class ManifestError(K3sClientError):
    """Raised for manifest creation or apply errors."""

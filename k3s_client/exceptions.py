# k3s_client/exceptions.py


class K3sClientError(Exception):
    """Base exception for all k3s-client library errors."""

    pass


class DeploymentError(K3sClientError):
    """Raised for deployment-specific errors."""

    pass


class ServiceError(K3sClientError):
    """Raised for service-specific errors."""

    pass


class RegistrySecretError(K3sClientError):
    """Raised for Docker registry secret issues."""

    pass


class ManifestError(K3sClientError):
    """Raised for manifest creation or apply errors."""

    pass

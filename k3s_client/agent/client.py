import json
import logging
from typing import Any
from urllib import error, request

from k3s_client.exceptions import K3sClientError

logger = logging.getLogger(__name__)


class SwarmAgentClient:
    """Lightweight HTTP client for delegating operations to swarm-agent."""

    DEFAULT_BASE_URL = "http://127.0.0.1:8080"

    def __init__(
        self,
        base_url: str | None = None,
        endpoint: str = "/v1/actions",
        timeout: int = 30,
        token: str | None = None,
    ):
        if not base_url:
            base_url = self.DEFAULT_BASE_URL

        self.base_url = base_url.rstrip("/")
        endpoint = endpoint.strip()
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        self.url = f"{self.base_url}{endpoint}"
        self.timeout = timeout
        self.token = token

    def execute(self, action: str, params: dict[str, Any] | None = None) -> Any:
        payload = {"action": action, "params": params or {}}
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = request.Request(self.url, data=data, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise K3sClientError(
                f"swarm-agent request failed ({exc.code}): {details}"
            ) from exc
        except error.URLError as exc:
            raise K3sClientError(f"Unable to reach swarm-agent: {exc.reason}") from exc
        except Exception as exc:
            raise K3sClientError(f"Unexpected swarm-agent error: {exc}") from exc

        if not body:
            return None

        try:
            response_data = json.loads(body)
        except json.JSONDecodeError:
            return body

        if isinstance(response_data, dict):
            if response_data.get("ok") is False:
                message = response_data.get("error") or "swarm-agent returned failure"
                raise K3sClientError(str(message))
            if "result" in response_data:
                return response_data["result"]
        return response_data

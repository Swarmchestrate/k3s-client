from typing import Any

from k3s_client.api.applications import ApplicationManager

# Optimizer emits an ordered action list. Keep dependent actions in sequence.
# Supported actions in this example: create_pod, delete_pod, scale_to.
ACTION_PLAN = [
    {"action": "create_pod", "msid": "productpage"},
    {"action": "create_pod", "msid": "productpage", "nodeid": "worker-2"},
    {"action": "delete_pod", "msid": "productpage", "podid": None},
    {"action": "scale_to", "msid": "reviews", "count": 2},
]


def execute_optimizer_actions(
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute optimizer-driven runtime pod actions in order."""
    manager = ApplicationManager()
    results: list[dict[str, Any]] = []

    for index, item in enumerate(actions):
        action = str(item.get("action") or "").strip()
        msid = item.get("msid")

        if action == "create_pod":
            response = manager.create_pod(
                msid=msid,
                nodeid=item.get("nodeid"),
            )
        elif action == "delete_pod":
            response = manager.delete_pod(
                msid=msid,
                podid=item.get("podid"),
            )
        elif action == "scale_to":
            response = manager.scale_to(
                msid=msid,
                count=int(item.get("count", 0)),
            )
        else:
            raise ValueError(
                f"Unsupported action at index {index}: {action}. "
                "Supported: create_pod, delete_pod, scale_to"
            )

        results.append(
            {
                "index": index,
                "action": action,
                "msid": msid,
                "response": response,
            }
        )

    print("Optimizer action execution results:")
    print(results)
    return results


if __name__ == "__main__":
    execute_optimizer_actions(actions=ACTION_PLAN)

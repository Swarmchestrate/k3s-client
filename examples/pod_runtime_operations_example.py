from k3s_client.api.applications import ApplicationManager

MANIFEST_FILE = "generated-manifests.yaml"
MSID = "productpage"
NAMESPACE = "default"
SWARM_AGENT_URL = "http://swarm-agent.default.svc.cluster.local:8080"


def pod_runtime_operations_example(
    manifest_file: str = MANIFEST_FILE,
    msid: str = MSID,
    namespace: str = NAMESPACE,
    swarm_agent_url: str | None = None,
    target_replicas: int = 3,
    nodeid_for_new_pod: str | None = None,
    podid_to_delete: str | None = None,
) -> dict:
    """Apply a manifest, then run runtime pod operations for an optimizer flow.

    Operations demonstrated:
    1) create_pod(msid)
    2) delete_pod(msid, podid=None)
    3) scale_to(msid, count)
    4) create_pod(msid, nodeid=<node>) for placement-aware scheduling
    """
    manager = ApplicationManager(swarm_agent_url=swarm_agent_url)

    apply_result = manager.apply_manifest(
        manifest_file=manifest_file,
        namespace=namespace,
    )

    created_any_node = manager.create_pod(msid=msid, namespace=namespace)
    deleted_any_pod = manager.delete_pod(
        msid=msid,
        podid=podid_to_delete,
        namespace=namespace,
    )
    scaled = manager.scale_to(msid=msid, count=target_replicas, namespace=namespace)

    created_on_node = None
    if nodeid_for_new_pod:
        created_on_node = manager.create_pod(
            msid=msid,
            nodeid=nodeid_for_new_pod,
            namespace=namespace,
        )

    result = {
        "apply_manifest": apply_result,
        "create_pod": created_any_node,
        "delete_pod": deleted_any_pod,
        "scale_to": scaled,
        "create_pod_on_node": created_on_node,
    }
    print("Runtime pod operation results:")
    print(result)
    return result


if __name__ == "__main__":
    pod_runtime_operations_example(
        manifest_file=MANIFEST_FILE,
        msid=MSID,
        namespace=NAMESPACE,
        swarm_agent_url=SWARM_AGENT_URL,
        target_replicas=3,
        nodeid_for_new_pod=None,
        podid_to_delete=None,
    )

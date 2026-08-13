#!/usr/bin/env python3
"""Real-cluster smoke test for ApplicationManager.

Run this from inside a pod that uses the same ServiceAccount and RBAC
permissions as swarm-agent. This validates in-cluster auth and live SDK
calls end-to-end.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from k3s_client.api.applications import ApplicationManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run k3s-client smoke test")
    parser.add_argument(
        "--tosca-file",
        default="examples/Bookinfo.yaml",
        help="Path to TOSCA file used for apply_tosca",
    )
    parser.add_argument(
        "--manifest-file",
        default="generated-manifests.yaml",
        help="Manifest file path used for delete_manifest",
    )
    parser.add_argument("--msid", required=True, help="Target microservice id")
    parser.add_argument("--nodeid", required=True, help="Target node id for placement")
    parser.add_argument(
        "--other-nodeid",
        required=True,
        help="Alternate node id used for migrate_pod",
    )
    parser.add_argument(
        "--podid",
        required=True,
        help="Existing pod name for delete_pod and migrate_pod",
    )
    parser.add_argument(
        "--registry-secret-name",
        required=True,
        help="Secret name for create_registry_secret",
    )
    parser.add_argument(
        "--registry",
        required=True,
        help="Registry host for create_registry_secret",
    )
    parser.add_argument(
        "--registry-username",
        required=True,
        help="Registry username for create_registry_secret",
    )
    parser.add_argument(
        "--registry-password",
        required=True,
        help="Registry password for create_registry_secret",
    )
    parser.add_argument(
        "--registry-email",
        default=None,
        help="Optional registry email",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run ApplicationManager methods in dry-run mode and validate result payloads",
    )
    return parser.parse_args()


def _validate_result_payloads(results: dict[str, object]) -> None:
    """Ensure dry-run responses contain real result payloads."""
    for operation, payload in results.items():
        if operation == "get_pod_node_mapping":
            # Read-only path still returns a dry-run envelope from ApplicationManager.
            pass
        if not isinstance(payload, dict):
            raise TypeError(f"Dry-run response for {operation} is not a mapping")
        if payload.get("mode") != "dry-run":
            raise ValueError(f"Dry-run response for {operation} missing mode=dry-run")
        if payload.get("executed") is not False:
            raise ValueError(f"Dry-run response for {operation} has executed!=False")
        if payload.get("result") is None:
            raise ValueError(f"Dry-run response for {operation} has empty result")


def main() -> int:
    args = parse_args()
    manager = ApplicationManager(dry_run_by_default=False)

    results: dict[str, object] = {}

    results["apply_tosca"] = manager.apply_tosca(
        tosca_file=args.tosca_file,
        output_manifest_file=args.manifest_file,
        dry_run=args.dry_run,
    )
    results["apply_manifest"] = manager.apply_manifest(
        manifest_file=args.manifest_file,
        dry_run=args.dry_run,
    )
    results["create_registry_secret"] = manager.create_registry_secret(
        name=args.registry_secret_name,
        registry=args.registry,
        username=args.registry_username,
        password=args.registry_password,
        email=args.registry_email,
        dry_run=args.dry_run,
    )
    results["get_pod_node_mapping"] = manager.get_pod_node_mapping(dry_run=args.dry_run)
    results["scale_to"] = manager.scale_to(
        msid=args.msid, count=2, dry_run=args.dry_run
    )
    results["create_pod"] = manager.create_pod(
        msid=args.msid,
        nodeid=args.nodeid,
        dry_run=args.dry_run,
    )
    results["delete_pod"] = manager.delete_pod(
        msid=args.msid,
        podid=args.podid,
        dry_run=args.dry_run,
    )
    results["migrate_pod"] = manager.migrate_pod(
        msid=args.msid,
        podid=args.podid,
        nodeid=args.other_nodeid,
        dry_run=args.dry_run,
    )

    manifest_path = Path(args.manifest_file)
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Expected manifest file was not created: {manifest_path}"
        )
    results["delete_manifest"] = manager.delete_manifest(
        str(manifest_path),
        dry_run=args.dry_run,
    )

    if args.dry_run:
        _validate_result_payloads(results)

    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

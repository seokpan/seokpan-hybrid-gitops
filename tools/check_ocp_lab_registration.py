"""Check path-A controller declarations only; never call Git, oc, Argo or a cluster."""
import argparse
from pathlib import Path
import re
import sys

import yaml

NAME = "seokpan-ocp-lab-app"
CONTROLLER = "openshift-gitops"
REPO = "https://github.com/seokpan/seokpan-hybrid-gitops.git"
DESTINATION = {"server": "https://kubernetes.default.svc", "namespace": "seokpan-argotest"}
KINDS = {("apps", "Deployment"), ("apps", "StatefulSet"),
         ("", "Service"), ("", "ConfigMap"), ("route.openshift.io", "Route")}
ANNOTATIONS = {
    "argocd.argoproj.io/sync-options": "Prune=false,Delete=false",
    "seokpan.io/release-state": "input-required-no-runtime-validation",
}
METADATA_FIELDS = {"name", "namespace", "annotations", "labels"}


class UniqueLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate mapping keys in a registration artifact."""


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError("duplicate mapping key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def registration_blockers(rendered, workload_sha):
    """Match reviewed input values, not the existence/approval of a supplied SHA."""
    if not isinstance(workload_sha, str) or re.fullmatch(r"[0-9a-f]{40}", workload_sha) is None:
        return ["workload SHA must be a complete lowercase 40-character commit ID"]
    try:
        objects = list(yaml.load_all(rendered, Loader=UniqueLoader))
        if len(objects) != 2 or any(not isinstance(obj, dict) for obj in objects):
            raise ValueError
        if sorted(obj.get("kind", "") for obj in objects) != ["AppProject", "Application"]:
            raise ValueError
        project = next(obj for obj in objects if obj["kind"] == "AppProject")
        app = next(obj for obj in objects if obj["kind"] == "Application")
        blockers = []
        for obj in objects:
            metadata = obj["metadata"]
            if not isinstance(metadata, dict):
                raise ValueError
            if obj["apiVersion"] != "argoproj.io/v1alpha1" or \
                    metadata["name"] != NAME or metadata["namespace"] != CONTROLLER:
                blockers.append("controller object API/name/namespace does not match path A")
            if set(metadata) - METADATA_FIELDS:
                blockers.append("controller metadata contains unreviewed fields")
            if metadata.get("annotations") != ANNOTATIONS:
                blockers.append("controller annotations must exactly match the reviewed allowlist")
            if metadata.get("labels", {}) != {}:
                blockers.append("controller labels must be absent or an empty mapping")
            if metadata.get("finalizers") or metadata.get("ownerReferences") or "operation" in obj:
                blockers.append("controller registration must not cascade, adopt or start a sync operation")
        spec = project["spec"]
        if set(spec) - {"description", "sourceRepos", "destinations", "clusterResourceWhitelist",
                        "clusterResourceBlacklist", "namespaceResourceWhitelist"}:
            blockers.append("Project contains additional unreviewed policy fields")
        if spec["sourceRepos"] != [REPO] or spec["destinations"] != [DESTINATION]:
            blockers.append("Project repository or destination exceeds the selected scope")
        if spec["clusterResourceWhitelist"] != [] or \
                spec["clusterResourceBlacklist"] != [{"group": "*", "kind": "*"}]:
            blockers.append("Project must deny cluster-scoped resources")
        allowed = spec["namespaceResourceWhitelist"]
        if len(allowed) != len(KINDS) or \
                any(set(entry) != {"group", "kind"} for entry in allowed) or \
                {(entry["group"], entry["kind"]) for entry in allowed} != KINDS:
            blockers.append("Project must allow exactly the five reviewed namespaced kinds")
        spec = app["spec"]
        if set(spec) != {"project", "source", "destination", "syncPolicy"}:
            blockers.append("Application contains additional or missing execution fields")
        if spec["project"] != NAME or spec["destination"] != DESTINATION:
            blockers.append("Application Project or destination differs")
        if spec["source"] != {"repoURL": REPO, "path": "apps/overlays/lab",
                              "targetRevision": workload_sha}:
            blockers.append("Application must consume the exact prior Workload SHA/path without overrides")
        if spec["syncPolicy"] != {"syncOptions": ["FailOnSharedResource=true"]}:
            blockers.append("Application must remain manual without automated sync/extra sync options")
        return blockers
    except (yaml.YAMLError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return ["invalid or ambiguous path-A registration YAML"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workload-sha", required=True)
    args = parser.parse_args()
    try:
        rendered = args.manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        print("BLOCKED: registration artifact unavailable", file=sys.stderr)
        return 1
    blockers = registration_blockers(rendered, args.workload_sha)
    if blockers:
        for blocker in blockers:
            print("BLOCKED: " + blocker, file=sys.stderr)
        return 1
    print("PASS: path-A controller declaration comparison only")
    print("NOT VERIFIED: Workload approval/release, live RBAC/ownership/window, registration or Sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

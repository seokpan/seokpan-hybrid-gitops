"""Offline Cloud platform candidate. No cluster/auth/network call or deployment approval."""
import argparse
import json
import re
import sys
from pathlib import Path
import yaml

REPO = "https://github.com/seokpan/seokpan-hybrid-gitops.git"
STATE = "source-candidate-no-runtime-approval"
class Invalid(ValueError):
    pass

def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid("DUPLICATE_JSON_KEY")
        result[key] = value
    return result

def read_contract(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise Invalid("REGULAR_LIMITED_INPUT_REQUIRED")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=object_pairs)
    except (UnicodeError, json.JSONDecodeError):
        raise Invalid("JSON_FORMAT") from None

def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid("CONTRACT_FIELDS")

def namespace(value):
    if not isinstance(value, str) or len(value) > 63 or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value):
        raise Invalid("NAMESPACE_FORMAT")
    if value == "default" or value.startswith(("kube-", "openshift-")) or "input-required" in value:
        raise Invalid("APP_NAMESPACE_BOUNDARY")
    return value

def labels(value):
    if not isinstance(value, dict) or not value or len(value) > 8:
        raise Invalid("ROUTER_LABELS_REQUIRED")
    # Explicit matchLabels only; no empty selector or broad expression fallback.
    atom = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,61}[A-Za-z0-9])?"
    for key, item in value.items():
        if not isinstance(key, str) or key.count("/") > 1:
            raise Invalid("LABEL_FORMAT")
        if "/" in key:
            prefix, name = key.split("/")
            if len(prefix) > 253 or any(len(part) > 63 or re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", part) is None for part in prefix.split(".")):
                raise Invalid("LABEL_FORMAT")
        else:
            name = key
        if re.fullmatch(atom, name) is None or not isinstance(item, str) or re.fullmatch(atom, item) is None:
            raise Invalid("LABEL_FORMAT")
    return value

def validate(c):
    exact(c, ("schema_version", "environment", "app_namespace", "argo_namespace", "gitops_revision", "dedicated_namespace", "router_namespace", "router_pod_labels", "include_pod_logs"))
    if type(c["schema_version"]) is not int or c["schema_version"] != 1 or c["environment"] != "cloud":
        raise Invalid("VERSION_OR_ENVIRONMENT")
    namespace(c["app_namespace"])
    if not isinstance(c["argo_namespace"], str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", c["argo_namespace"]) or len(c["argo_namespace"]) > 63:
        raise Invalid("ARGO_NAMESPACE")
    if c["app_namespace"] == c["argo_namespace"]:
        raise Invalid("NAMESPACE_COLLISION")
    if not isinstance(c["gitops_revision"], str) or not re.fullmatch(r"[0-9a-f]{40}", c["gitops_revision"]):
        raise Invalid("PINNED_REVISION_REQUIRED")
    if c["dedicated_namespace"] is not True:
        raise Invalid("DEDICATED_NAMESPACE_REVIEW_REQUIRED")
    if not isinstance(c["router_namespace"], str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", c["router_namespace"]) or len(c["router_namespace"]) > 63:
        raise Invalid("ROUTER_NAMESPACE")
    if c["router_namespace"] == c["app_namespace"]:
        raise Invalid("ROUTER_NAMESPACE_COLLISION")
    labels(c["router_pod_labels"])
    if type(c["include_pod_logs"]) is not bool:
        raise Invalid("LOG_PERMISSION_DECISION_REQUIRED")
    return c

def candidates(contract):
    c = validate(contract)
    ns, argo = c["app_namespace"], c["argo_namespace"]
    def obj(api, kind, name, target=ns):
        return {"apiVersion": api, "kind": kind, "metadata": {"name": name, **({"namespace": target} if target else {}), "annotations": {"seokpan.io/release-state": STATE, "argocd.argoproj.io/sync-options": "Prune=false,Delete=false"}}}
    n = obj("v1", "Namespace", ns, None)
    n["metadata"]["labels"] = {"seokpan.io/environment": "cloud"}
    r = obj("rbac.authorization.k8s.io/v1", "Role", "seokpan-observer")
    r["rules"] = [
        {"apiGroups": [""], "resources": ["pods", "services", "endpoints", "events"], "verbs": ["get", "list", "watch"]},
        {"apiGroups": ["apps"], "resources": ["deployments", "replicasets"], "verbs": ["get", "list", "watch"]},
        {"apiGroups": ["route.openshift.io"], "resources": ["routes"], "verbs": ["get", "list", "watch"]},
        {"apiGroups": ["policy"], "resources": ["poddisruptionbudgets"], "verbs": ["get", "list", "watch"]},
    ]
    if c["include_pod_logs"]:
        r["rules"].append({"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get"]})
    # Bindings require observed OpenShift subjects and separate IdP/RBAC review.
    p = obj("argoproj.io/v1alpha1", "AppProject", "seokpan-cloud-app", argo)
    kinds = [("apps", "Deployment"), ("", "Service"), ("", "ConfigMap"), ("route.openshift.io", "Route"), ("policy", "PodDisruptionBudget")]
    p["spec"] = {"sourceRepos": [REPO], "destinations": [{"server": "https://kubernetes.default.svc", "namespace": ns}], "clusterResourceWhitelist": [], "clusterResourceBlacklist": [{"group": "*", "kind": "*"}], "namespaceResourceWhitelist": [{"group": g, "kind": k} for g, k in kinds]}
    a = obj("argoproj.io/v1alpha1", "Application", "seokpan-cloud-app", argo)
    a["spec"] = {"project": p["metadata"]["name"], "source": {"repoURL": REPO, "targetRevision": c["gitops_revision"], "path": "apps/overlays/cloud"}, "destination": {"server": "https://kubernetes.default.svc", "namespace": ns}, "syncPolicy": {"syncOptions": ["FailOnSharedResource=true", "Prune=false", "Delete=false"]}}
    deny = obj("networking.k8s.io/v1", "NetworkPolicy", "seokpan-deny-ingress")
    deny["spec"] = {"podSelector": {}, "policyTypes": ["Ingress"], "ingress": []}
    peer = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": c["router_namespace"]}}, "podSelector": {"matchLabels": c["router_pod_labels"]}}
    routers = []
    for name, port in (("frontend", 8080), ("backend", 8000)):
        router = obj("networking.k8s.io/v1", "NetworkPolicy", "seokpan-router-to-" + name)
        router["spec"] = {"podSelector": {"matchLabels": {"app.kubernetes.io/name": name}}, "policyTypes": ["Ingress"], "ingress": [{"from": [peer], "ports": [{"protocol": "TCP", "port": port}]}]}
        routers.append(router)
    internal = obj("networking.k8s.io/v1", "NetworkPolicy", "seokpan-frontend-to-backend")
    internal["spec"] = {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "backend"}}, "policyTypes": ["Ingress"], "ingress": [{"from": [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "frontend"}}}], "ports": [{"protocol": "TCP", "port": 8000}]}]}
    return [n, r, p, a, deny, *routers, internal]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--output", type=Path, help="new file only; omit for validation without output")
    args = parser.parse_args()
    try:
        rendered = yaml.safe_dump_all(candidates(read_contract(args.contract)), sort_keys=False)
        if args.output:
            # Exclusive create also refuses existing/dangling symlinks.
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        print("CLOUD_PLATFORM_CONTRACT: PASS / SOURCE_CANDIDATE_ONLY")
        print("RUNTIME_IDP_RBAC_NETWORK_AND_SYNC_ACCEPTANCE: NOT_VERIFIED")
        return 0
    except (Invalid, OSError):
        # Never print the input or subject values in an error.
        print("CLOUD_PLATFORM_CONTRACT: BLOCKED / CONTRACT_OR_OUTPUT", file=sys.stderr)
        return 2
if __name__ == "__main__":
    sys.exit(main())

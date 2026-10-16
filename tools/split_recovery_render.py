# 작성자: 최유준
# 작성 날짜: 2026/10/16
"""Split the common Recovery composition into separate App / Migration Job / Job NP drafts.

Kustomize resolves the backend-config content-hash name and the Backend Image digest once,
for the App and the separate Migration Job together. This tool never edits the hash, never
disables suffix hashing, and never applies anything. The three outputs are review drafts:
they still carry the Job's input-required marker, so release/migration checks keep withholding
until B/C supply the remaining inputs.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
JOB_NAME = "seokpan-migration-recovery"
POLICY_NAME = "recovery-migration"
NAMESPACE = "seokpan-recovery"
MIGRATION_LABEL = {"app.kubernetes.io/name": "seokpan-migration"}
DB_CIDR = "192.168.54.60/32"


def migration_policy_spec():
    return {
        "podSelector": {"matchLabels": dict(MIGRATION_LABEL)},
        "policyTypes": ["Ingress", "Egress"],
        "egress": [
            {"to": [{"ipBlock": {"cidr": DB_CIDR}}], "ports": [{"protocol": "TCP", "port": 3306}]},
            {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                     "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}],
             "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
        ],
    }


def split_documents(rendered):
    docs = [d for d in yaml.safe_load_all(rendered) if d]
    jobs = [d for d in docs if d.get("kind") == "Job"]
    policies = [d for d in docs if d.get("kind") == "NetworkPolicy" and d["metadata"]["name"] == POLICY_NAME]
    app = [d for d in docs if d not in jobs and d not in policies]
    if len(jobs) != 1 or jobs[0]["metadata"]["name"] != JOB_NAME or len(policies) != 1:
        raise ValueError("composition must hold exactly the reviewed Job and its NetworkPolicy")
    return app, jobs[0], policies[0]


def key(doc):
    return (doc["kind"], doc["metadata"]["name"])


def recovery_migration_blockers(app, job, policy):
    """Recovery-specific Job/NP boundaries on top of check_migration_manifest (Source only)."""
    blockers = []
    try:
        pod = job["spec"]["template"]["spec"]
        container, = pod["containers"]
        if job["metadata"].get("namespace") != NAMESPACE or policy["metadata"].get("namespace") != NAMESPACE:
            blockers.append("Migration Job and policy must use the isolated Recovery Namespace")
        if job["spec"].get("suspend") is not True:
            blockers.append("Migration Job must stay suspended in Source")
        if job["spec"]["template"]["metadata"].get("labels") != MIGRATION_LABEL:
            blockers.append("Migration Job needs its own dedicated Pod label only (no Backend label)")
        if pod.get("serviceAccountName") != "default" or pod.get("automountServiceAccountToken") is not False:
            blockers.append("Migration must name the default ServiceAccount without a mounted token")
        if pod.get("imagePullSecrets") != [{"name": "recovery-harbor-pull"}]:
            blockers.append("Migration must name the Recovery Harbor pull reference")
        if container.get("args", [None])[0] != "current" or "--execute" in container.get("args", []):
            blockers.append("Migration Source is limited to read-only current")
        if policy.get("apiVersion") != "networking.k8s.io/v1" or policy.get("spec") != migration_policy_spec():
            blockers.append("Migration NetworkPolicy must allow only the target DB TCP3306 and CoreDNS UDP/TCP53")
        if any(d["kind"] in ("Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding", "ServiceAccount")
               for d in app):
            blockers.append("Recovery Source must not add RBAC or ServiceAccounts")
        backend = next(d for d in app if key(d) == ("Deployment", "backend"))
        if container["image"] != backend["spec"]["template"]["spec"]["containers"][0]["image"]:
            blockers.append("Migration Image must equal the rendered Backend Image")
    except (KeyError, TypeError, ValueError, IndexError, StopIteration):
        blockers.append("Migration composition structure is invalid")
    return list(dict.fromkeys(blockers))


def build(kustomize, path):
    return subprocess.run([kustomize, "build", str(path)], check=True, capture_output=True, text=True).stdout


def write_new(path, text):
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            temp = Path(tmp.name)
            tmp.write(text)
        os.link(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kustomize", default=os.environ.get("KUSTOMIZE", "kustomize"))
    parser.add_argument("--app-output", type=Path, required=True)
    parser.add_argument("--job-output", type=Path, required=True)
    parser.add_argument("--policy-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if subprocess.run([args.kustomize, "version"], check=True, capture_output=True,
                          text=True).stdout.strip() != "v5.7.1":
            print("split withheld: expected Kustomize v5.7.1", file=sys.stderr)
            return 2
        composed = build(args.kustomize, ROOT / "operations/recovery/compose")
        overlay = build(args.kustomize, ROOT / "apps/overlays/recovery")
        app, job, policy = split_documents(composed)
        # The App half must be exactly what the standalone Recovery overlay renders.
        if sorted(app, key=key) != sorted([d for d in yaml.safe_load_all(overlay) if d], key=key):
            print("split withheld: App half differs from the standalone Recovery overlay", file=sys.stderr)
            return 2
        blockers = recovery_migration_blockers(app, job, policy)
        if blockers:
            print("split withheld: " + ", ".join(blockers), file=sys.stderr)
            return 2
        write_new(args.app_output, yaml.safe_dump_all(app, sort_keys=False))
        write_new(args.job_output, yaml.safe_dump(job, sort_keys=False))
        write_new(args.policy_output, yaml.safe_dump(policy, sort_keys=False))
    except (OSError, subprocess.CalledProcessError, ValueError, yaml.YAMLError) as error:
        print(f"split withheld: {type(error).__name__}", file=sys.stderr)
        return 2
    print("split drafts written; migration-source-check and release-manifest still apply separately", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

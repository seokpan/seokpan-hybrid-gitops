"""Stage-1 preflight gate for the lab-only Valkey (lab-redis).

# 작성자: 최유준 작성 날짜: 2026/10/07
This is a Source input gate for the Valkey bundle only. It never reads or writes
the FE/BE, DB or Route inputs, and it does not replace or weaken the full lab
Release Gate (tools/render_release.py), which keeps withholding the whole lab
Application until the FE/BE inputs exist. No cluster, registry, AWS or GitHub
API call is made. A passing gate is not a Pod start, SCC, TLS/AUTH or hostname
proof; those are checked after the first manual Sync.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
IMAGE = ("image-registry.openshift-image-registry.svc:5000/seokpan-argotest/valkey"
         "@sha256:ef0f9fb533b1f06fb7aba6478d758ca1c077d49e2bcb2b4365a4ea7f50b6d42e")
STATE = "source-reviewed-runtime-unverified"
SNI = "lab-redis.seokpan-argotest.svc"
SELECTOR = {"app.kubernetes.io/name": "lab-redis"}
TOKEN_REF = {"secretKeyRef": {"name": "lab-redis-server-auth", "key": "token"}}
RUNTIME_LINES = ["maxmemory 192mb", "maxmemory-policy noeviction", 'save ""',
                 "appendonly no", "dir /data"]


def lab_valkey_blockers(rendered):
    """Return reasons the lab Valkey bundle must not be selected for Sync."""
    blockers = []
    try:
        resources = list(yaml.safe_load_all(rendered))
        if not resources or any(not isinstance(r, dict) for r in resources):
            raise ValueError
        if any(r.get("kind") == "Secret" for r in resources):
            blockers.append("Valkey bundle must not own Secret objects (separate Owner supply)")
        sts_all = [r for r in resources if r.get("kind") == "StatefulSet"
                   and r["metadata"]["name"] == "lab-redis"]
        svc_all = [r for r in resources if r.get("kind") == "Service"
                   and r["metadata"]["name"] == "lab-redis"]
        cfg_all = [r for r in resources if r.get("kind") == "ConfigMap"
                   and r["metadata"]["name"].startswith("lab-redis-config-")]
        run_all = [r for r in resources if r.get("kind") == "ConfigMap"
                   and r["metadata"]["name"].startswith("lab-redis-runtime-")]
        if len(sts_all) != 1 or len(svc_all) != 1 or len(cfg_all) != 1 or len(run_all) != 1:
            blockers.append("Valkey bundle requires exactly one StatefulSet, one Service and "
                            "the two generated ConfigMaps")
            return list(dict.fromkeys(blockers))
        sts, svc, cfg, run = sts_all[0], svc_all[0], cfg_all[0], run_all[0]
        spec = sts["spec"]
        pod = spec["template"]["spec"]

        if sts.get("apiVersion") != "apps/v1":
            blockers.append("Valkey workload must use the reviewed Kubernetes API")
        if spec.get("replicas") != 1:
            blockers.append("Valkey stage 1 requires exactly one reviewed replica")
        if sts["metadata"].get("annotations", {}).get("seokpan.io/release-state") != STATE:
            blockers.append("Valkey release-state must be " + STATE)
        if spec.get("serviceName") != "lab-redis" or \
                spec["selector"].get("matchLabels") != SELECTOR or \
                spec["template"]["metadata"].get("labels") != SELECTOR or \
                svc["spec"].get("selector") != SELECTOR:
            blockers.append("Valkey identity, Service and selectors must match")

        containers = pod.get("containers", [])
        if len(containers) != 1 or pod.get("initContainers"):
            blockers.append("Valkey requires exactly one container and no init containers")
            return list(dict.fromkeys(blockers))
        c = containers[0]
        if c.get("image") != IMAGE:
            blockers.append("Valkey image must be the exact reviewed internal Registry digest")
        if c.get("command") != ["valkey-server"] or \
                c.get("args") != ["/etc/seokpan/redis/redis.conf"]:
            blockers.append("Valkey must start valkey-server directly with the reviewed config")
        if c.get("ports") != [{"name": "redis-tls", "containerPort": 6379, "protocol": "TCP"}]:
            blockers.append("Valkey must expose only the TLS port 6379")

        env = {e["name"]: e for e in c.get("env", [])}
        if set(env) != {"REDISCLI_AUTH", "VALKEYCLI_AUTH"} or any(
                "value" in e or e.get("valueFrom") != TOKEN_REF for e in env.values()):
            blockers.append("Valkey AUTH env must come only from lab-redis-server-auth token")

        if "livenessProbe" in c:
            blockers.append("Valkey must not use a liveness probe while persistence is off")
        if c.get("startupProbe", {}).get("tcpSocket") != {"port": "redis-tls"}:
            blockers.append("Valkey startup probe must be the TLS TCP port")
        command = " ".join(c.get("readinessProbe", {}).get("exec", {}).get("command", []))
        for needle in ("valkey-cli --tls ", "--cacert /etc/seokpan/redis-server-tls/ca.crt",
                       "--sni " + SNI + " ", "-p 6379 ping", "grep -qx PONG"):
            if needle not in command:
                blockers.append("Valkey readiness must prove TLS and AUTH with PONG")
                break
        if re.search(r"(^|\s)(-a|--pass)(\s|$)", command):
            blockers.append("Valkey readiness must not pass a password on argv")

        sc = c.get("securityContext", {})
        if sc.get("runAsNonRoot") is not True or \
                sc.get("allowPrivilegeEscalation") is not False or \
                sc.get("readOnlyRootFilesystem") is not True or \
                sc.get("capabilities") != {"drop": ["ALL"]} or sc.get("privileged") or \
                any(k in sc for k in ("runAsUser", "runAsGroup", "seLinuxOptions")):
            blockers.append("Valkey container must be restricted and arbitrary-UID compatible")
        psc = pod.get("securityContext", {})
        if psc.get("seccompProfile") != {"type": "RuntimeDefault"} or \
                any(k in psc for k in ("runAsUser", "runAsGroup", "fsGroup",
                                       "supplementalGroups", "seLinuxOptions")) or \
                pod.get("automountServiceAccountToken") is not False or \
                any(pod.get(k) for k in ("hostNetwork", "hostPID", "hostIPC")) or \
                any("hostPort" in p for p in c.get("ports", [])):
            blockers.append("Valkey pod must not fix IDs, share host namespaces or mount a token")

        if "volumeClaimTemplates" in spec or any(
                "persistentVolumeClaim" in v for v in pod.get("volumes", [])):
            blockers.append("Valkey must not use persistent storage")
        if c.get("resources") != {"requests": {"cpu": "50m", "memory": "128Mi"},
                                  "limits": {"memory": "256Mi"}}:
            blockers.append("Valkey resources must be the reviewed candidate values")

        volumes = {v["name"]: v for v in pod.get("volumes", [])}
        tls = volumes["server-tls"]["secret"]
        auth = volumes["server-auth"]["secret"]
        if tls.get("secretName") != "lab-redis-server-tls" or \
                {i["key"] for i in tls.get("items", [])} != {"tls.crt", "tls.key", "ca.crt"} or \
                tls.get("defaultMode") != 0o440:
            blockers.append("Valkey TLS Secret reference must be the reviewed external Secret")
        if auth.get("secretName") != "lab-redis-server-auth" or \
                auth.get("items") != [{"key": "redis-auth.conf", "path": "redis-auth.conf"}] or \
                auth.get("defaultMode") != 0o440:
            blockers.append("Valkey AUTH Secret must expose only the include file")
        if volumes["redis-config"]["configMap"].get("name") != cfg["metadata"]["name"] or \
                volumes["runtime-config"]["configMap"].get("name") != run["metadata"]["name"]:
            blockers.append("Valkey ConfigMap references must use the rendered generated names")
        mounts = {m["name"]: m for m in c.get("volumeMounts", [])}
        for name in ("redis-config", "server-tls", "server-auth", "runtime-config"):
            if mounts[name].get("readOnly") is not True or "subPath" in mounts[name]:
                blockers.append("Valkey config and Secret mounts must be read-only without subPath")
                break

        conf = cfg["data"]["redis.conf"].splitlines()
        if [l.strip() for l in conf if re.match(r"\s*port\s", l)] != ["port 0"] or \
                "tls-port 6379" not in conf or "tls-auth-clients no" not in conf or \
                "include /etc/seokpan/redis-runtime/redis-runtime.conf" not in conf or \
                "include /etc/seokpan/redis-server-auth/redis-auth.conf" not in conf:
            blockers.append("Valkey config must be TLS-only 6379 with the reviewed includes")
        runtime = [l for l in run["data"]["redis-runtime.conf"].splitlines()
                   if l.strip() and not l.startswith("#")]
        if runtime != RUNTIME_LINES:
            blockers.append("Valkey runtime config must be unpersisted noeviction below the limit")

        s = svc["spec"]
        if s.get("type", "ClusterIP") != "ClusterIP" or s.get("clusterIP") != "None" or \
                any(k in s for k in ("externalIPs", "externalName", "loadBalancerIP")) or \
                s.get("ports") != [{"name": "redis-tls", "port": 6379,
                                    "targetPort": "redis-tls", "protocol": "TCP"}]:
            blockers.append("Valkey must expose only its internal headless TLS Service")
    except (AttributeError, KeyError, TypeError, ValueError, IndexError, StopIteration,
            yaml.YAMLError):
        blockers.append("Valkey manifest structure is invalid")
    return list(dict.fromkeys(blockers))


def selected_resources(rendered):
    """Resources to select for the Valkey-only manual Sync, as Kind/name."""
    wanted = []
    for r in yaml.safe_load_all(rendered):
        name = r["metadata"]["name"]
        if (r["kind"] in ("StatefulSet", "Service") and name == "lab-redis") or \
                (r["kind"] == "ConfigMap" and name.startswith(("lab-redis-config-",
                                                               "lab-redis-runtime-"))):
            wanted.append(f"{r['kind']}/{name}")
    return wanted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kustomize", default=os.environ.get("KUSTOMIZE", "kustomize"))
    args = parser.parse_args()
    try:
        version = subprocess.run([args.kustomize, "version"], check=True,
                                 capture_output=True, text=True).stdout.strip()
        if version != "v5.7.1":
            print("preflight withheld: expected Kustomize v5.7.1", file=sys.stderr)
            return 2
        rendered = subprocess.run(
            [args.kustomize, "build", str(ROOT / "apps/overlays/lab")],
            check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        print("preflight withheld: Kustomize version/build failed", file=sys.stderr)
        return 2
    blockers = lab_valkey_blockers(rendered)
    if blockers:
        print("preflight withheld: " + "; ".join(blockers), file=sys.stderr)
        return 2
    for item in selected_resources(rendered):
        print(item)
    print("stage-1 Valkey gate passed; select only the resources above for the manual Sync. "
          "Runtime, SCC, TLS/AUTH and hostname checks and the full lab Release Gate "
          "remain separate", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

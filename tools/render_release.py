"""Build with Kustomize and withhold unresolved draft output.

This is a source input gate, not a deployment tool or Runtime readiness proof.
No cluster, registry, AWS or GitHub API calls are made by this script.
"""

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]


def app_manifest_blockers(rendered, environment):
    """Check immutable App images and declared multi-replica lifecycle inputs.

    This verifies Source composition only. A digest's format is not a Scan/Pull
    approval and captured mode is not proof that rollout/data/runtime gates pass.
    """
    blockers = []
    try:
        resources = list(yaml.safe_load_all(rendered))
        if not resources or any(not isinstance(r, dict) for r in resources):
            raise ValueError
        deployments = [r for r in resources if r.get("kind") == "Deployment"]
        names = [r["metadata"]["name"] for r in deployments]
        if names.count("backend") != 1 or names.count("frontend") != 1:
            blockers.append("App release requires one backend and frontend Deployment")
        workloads = [r for r in resources if r.get("kind") in
                     {"Deployment", "StatefulSet", "DaemonSet", "Job", "Pod", "CronJob"}]
        for workload in workloads:
            if workload["kind"] == "Pod":
                pod = workload["spec"]
            elif workload["kind"] == "CronJob":
                pod = workload["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            else:
                pod = workload["spec"]["template"]["spec"]
            if not pod.get("containers"):
                raise ValueError
            for container in [*pod["containers"], *pod.get("initContainers", [])]:
                image = container.get("image", "")
                if not isinstance(image, str) or re.fullmatch(
                        r"[a-zA-Z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+"
                        r"(?::[a-zA-Z0-9_.-]+)?@sha256:[0-9a-f]{64}", image) is None:
                    blockers.append("App and initContainer images must use registry digest references")
        if environment == "cloud":
            backend = next(r for r in deployments if r["metadata"]["name"] == "backend")
            replicas = backend["spec"].get("replicas", 1)
            if not isinstance(replicas, int) or isinstance(replicas, bool):
                raise ValueError
            if replicas > 1:
                container, = backend["spec"]["template"]["spec"]["containers"]
                env_from, = container["envFrom"]
                if set(env_from) != {"configMapRef"} or \
                        env_from["configMapRef"].get("optional", False) or \
                        set(env_from["configMapRef"]) != {"name"}:
                    raise ValueError
                config_name = env_from["configMapRef"]["name"]
                config, = [r["data"] for r in resources if r.get("kind") == "ConfigMap"
                           and r["metadata"]["name"] == config_name
                           and r["metadata"].get("namespace") == backend["metadata"].get("namespace")]
                if any(e.get("name") == "SEOKPAN_GAME_LIFECYCLE_MODE" for e in container.get("env", [])):
                    blockers.append("Cloud lifecycle must not override its reviewed configuration")
                if config.get("SEOKPAN_GAME_LIFECYCLE_MODE") != "captured":
                    blockers.append("multi-replica Cloud activation requires reviewed captured lifecycle configuration")
    except (AttributeError, KeyError, TypeError, ValueError, IndexError, StopIteration, yaml.YAMLError):
        blockers.append("App manifest structure or lifecycle configuration is invalid")
    return list(dict.fromkeys(blockers))


def recovery_manifest_blockers(rendered, namespace, registry):
    """Check declared Recovery boundaries, never actual Secret values or runtime.

    Namespace and Harbor host are independently supplied reviewed inputs. A name
    or PVC reference does not prove isolation, empty storage, TLS or AUTH works.
    """
    blockers = []
    if not namespace or len(namespace) > 63 or \
            re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", namespace) is None:
        return ["reviewed Recovery namespace is required"]
    if not registry or re.fullmatch(r"[a-zA-Z0-9.-]+(?::[0-9]+)?", registry) is None:
        return ["reviewed local Harbor registry host is required"]
    try:
        resources = list(yaml.safe_load_all(rendered))
        if not resources or any(not isinstance(r, dict) for r in resources):
            raise ValueError
        allowed = {"Deployment", "StatefulSet", "Service", "ConfigMap"}
        if any(r.get("kind") not in allowed for r in resources):
            blockers.append("Recovery must not manage namespace, secret, storage or external owners")
        if any(r.get("metadata", {}).get("namespace") != namespace for r in resources):
            blockers.append("Recovery resources must use the reviewed isolated namespace")
        identities = [(r["kind"], r["metadata"]["name"]) for r in resources]
        if len(identities) != len(set(identities)):
            blockers.append("duplicate Recovery resources")
        workloads = [r for r in resources if r.get("kind") in ("Deployment", "StatefulSet")]
        if len(workloads) != 3 or {(r["kind"], r["metadata"]["name"]) for r in workloads} != {
                ("Deployment", "backend"), ("Deployment", "frontend"),
                ("StatefulSet", "recovery-redis")}:
            blockers.append("Recovery requires only its App workloads and the separate new Redis")
        for workload in workloads:
            if workload["apiVersion"] != "apps/v1":
                blockers.append("Recovery workloads must use the reviewed Kubernetes API")
            if workload["spec"].get("replicas") != 1:
                blockers.append("Recovery initial workloads must use one reviewed replica")
            pod = workload["spec"]["template"]["spec"]
            if pod.get("imagePullSecrets") != [{"name": "recovery-harbor-pull"}]:
                blockers.append("Recovery local Harbor pull reference is required")
            for container in [*pod["containers"], *pod.get("initContainers", [])]:
                image = container.get("image", "")
                if re.fullmatch(re.escape(registry) + r"/[a-z0-9._/-]+@sha256:[0-9a-f]{64}", image) is None:
                    blockers.append("Recovery images must be local Harbor digest references")
        redis = next(r for r in workloads if r["kind"] == "StatefulSet"
                     and r["metadata"]["name"] == "recovery-redis")
        service = next(r for r in resources if r.get("kind") == "Service"
                       and r["metadata"]["name"] == "recovery-redis")
        selector = {"app.kubernetes.io/name": "recovery-redis"}
        if redis["spec"].get("serviceName") != "recovery-redis" or \
                redis["spec"]["selector"].get("matchLabels") != selector or \
                redis["spec"]["template"]["metadata"].get("labels") != selector or \
                service["spec"].get("selector") != selector:
            blockers.append("new Recovery Redis identity and Service selectors must match")
        if service["spec"].get("type", "ClusterIP") != "ClusterIP" or \
                service["spec"].get("clusterIP") != "None" or \
                any(k in service["spec"] for k in ("externalIPs", "externalName", "loadBalancerIP")) or \
                service["spec"].get("ports") != [{"name": "redis-tls", "port": 6379,
                                                "targetPort": "redis-tls", "protocol": "TCP"}]:
            blockers.append("Recovery Redis must expose only its internal TLS Service")
        backend = next(r for r in workloads if r["metadata"]["name"] == "backend")
        backend_pod = backend["spec"]["template"]["spec"]
        backend_container, = backend_pod["containers"]
        env_from = backend_container["envFrom"]
        if len(env_from) != 1 or set(env_from[0]) != {"configMapRef"} or \
                set(env_from[0]["configMapRef"]) - {"name", "optional"} or \
                env_from[0]["configMapRef"].get("optional", False) is not False:
            blockers.append("Recovery Backend requires one unprefixed required configuration reference")
            raise ValueError
        backend_config_name = env_from[0]["configMapRef"]["name"]
        backend_config = next(r["data"] for r in resources if r.get("kind") == "ConfigMap"
                              and r["metadata"]["name"] == backend_config_name)
        env_names = [entry["name"] for entry in backend_container["env"]]
        if len(env_names) != len(set(env_names)) or set(env_names) & backend_config.keys():
            blockers.append("Recovery Backend environment must not duplicate or override reviewed configuration")
        if "SEOKPAN_REDIS_AUTH_TOKEN" in backend_config:
            blockers.append("Recovery authentication must not be embedded in public configuration")
        url = urlsplit(backend_config["SEOKPAN_REDIS_URL"])
        hosts = {f"recovery-redis.{namespace}.svc", f"recovery-redis.{namespace}.svc.cluster.local"}
        if backend_config.get("SEOKPAN_CONNECTION_PROFILE") != "recovery" or \
                url.scheme != "rediss" or url.hostname not in hosts or url.port != 6379 or \
                url.path != "/0" or url.username is not None or url.password is not None or \
                url.query or url.fragment or \
                backend_config.get("SEOKPAN_REDIS_EXPECTED_HOST") != url.hostname or \
                backend_config.get("SEOKPAN_REDIS_EXPECTED_PORT") != "6379" or \
                backend_config.get("SEOKPAN_REDIS_EXPECTED_DATABASE") != "0":
            blockers.append("Recovery Backend must use the new local Redis Service with TLS")
        auth = next(e for e in backend_container["env"] if e["name"] == "SEOKPAN_REDIS_AUTH_TOKEN")
        if "value" in auth or auth.get("valueFrom", {}).get("secretKeyRef") != {
                "name": "backend-redis-runtime", "key": "SEOKPAN_REDIS_AUTH_TOKEN"}:
            blockers.append("Recovery Backend AUTH must be a separate external Secret reference")
        ca = next(v for v in backend_pod["volumes"] if v["name"] == "redis-ca")
        ca_mount = next(m for m in backend_container["volumeMounts"] if m["name"] == "redis-ca")
        if ca.get("configMap", {}).get("name") != "backend-redis-ca" or \
                ca["configMap"].get("optional", False) or \
                ca["configMap"].get("items") != [{"key": "ca.crt", "path": "ca.crt"}] or \
                ca_mount.get("mountPath") != "/etc/seokpan/redis-ca" or \
                ca_mount.get("readOnly") is not True or "subPath" in ca_mount or \
                backend_config.get("SEOKPAN_REDIS_CA_FILE") != "/etc/seokpan/redis-ca/ca.crt":
            blockers.append("Recovery Backend Redis CA must be a required external reference")
        pod = redis["spec"]["template"]["spec"]
        container, = pod["containers"]
        if container.get("command") != ["redis-server"] or \
                container.get("args") != ["/etc/seokpan/redis/redis.conf"] or \
                container.get("env") or container.get("envFrom"):
            blockers.append("Recovery Redis must read protected authentication from files, never argv/env")
        volumes = {v["name"]: v for v in pod["volumes"]}
        mounts = {m["name"]: m for m in container["volumeMounts"]}
        if len(volumes) != len(pod["volumes"]) or len(mounts) != len(container["volumeMounts"]):
            blockers.append("Recovery Redis volume identities must be unique")
        if "volumeClaimTemplates" in redis["spec"] or \
                container.get("ports") != [{"name": "redis-tls", "containerPort": 6379, "protocol": "TCP"}]:
            blockers.append("Recovery Redis must not create storage or expose a plaintext port")
        for probe_name in ("startupProbe", "readinessProbe"):
            probe = container.get(probe_name, {})
            if probe.get("tcpSocket") != {"port": "redis-tls"} or \
                    any(key in probe for key in ("exec", "httpGet", "grpc")) or \
                    any(not isinstance(probe.get(key), int) or isinstance(probe.get(key), bool)
                        or probe[key] <= 0 for key in ("periodSeconds", "timeoutSeconds", "failureThreshold")):
                blockers.append("Recovery Redis requires reviewed TLS-listener startup/readiness probes")
        security = container.get("securityContext", {})
        if pod.get("automountServiceAccountToken") is not False or \
                pod.get("enableServiceLinks") is not False or \
                pod.get("securityContext", {}).get("seccompProfile") != {"type": "RuntimeDefault"} or \
                any(k in context for context in (security, pod.get("securityContext", {}))
                    for k in ("runAsUser", "runAsGroup", "fsGroup")) or \
                security.get("runAsNonRoot") is not True or \
                security.get("allowPrivilegeEscalation") is not False or \
                security.get("readOnlyRootFilesystem") is not True or \
                security.get("capabilities", {}).get("drop") != ["ALL"]:
            blockers.append("Recovery Redis must retain its arbitrary-UID restricted workload boundary")
        expected_refs = {
            "server-tls": ("secret", "secretName", "recovery-redis-server-tls", "/etc/seokpan/redis-server-tls",
                           [{"key": key, "path": key} for key in ("tls.crt", "tls.key", "ca.crt")]),
            "server-auth": ("secret", "secretName", "recovery-redis-server-auth", "/etc/seokpan/redis-server-auth",
                            [{"key": "redis-auth.conf", "path": "redis-auth.conf"}]),
            "runtime-config": ("configMap", "name", None, "/etc/seokpan/redis-runtime",
                               [{"key": "redis-runtime.conf", "path": "redis-runtime.conf"}]),
        }
        for name, (kind, field, reference, path, items) in expected_refs.items():
            source = volumes[name].get(kind, {})
            if not source.get(field) or (reference and source[field] != reference) or \
                    source.get("optional", False) or source.get("items") != items or \
                    mounts[name].get("mountPath") != path or \
                    mounts[name].get("readOnly") is not True or "subPath" in mounts[name]:
                blockers.append("Recovery Redis TLS, AUTH and runtime configuration references are required")
        config_name = volumes["redis-config"]["configMap"]["name"]
        if {r["metadata"]["name"] for r in resources if r.get("kind") == "ConfigMap"} != \
                {backend_config_name, config_name} or \
                {r["metadata"]["name"] for r in resources if r.get("kind") == "Service"} != \
                {"backend", "frontend", "recovery-redis"}:
            blockers.append("Recovery source must not manage other owners' configuration or Services")
        config_source = volumes["redis-config"]["configMap"]
        if config_source.get("optional", False) or \
                config_source.get("items") != [{"key": "redis.conf", "path": "redis.conf"}] or \
                mounts["redis-config"].get("mountPath") != "/etc/seokpan/redis" or \
                mounts["redis-config"].get("readOnly") is not True or "subPath" in mounts["redis-config"]:
            blockers.append("Recovery Redis must consume its nonsecret transport configuration read-only")
        config = next(r["data"]["redis.conf"] for r in resources if r.get("kind") == "ConfigMap"
                      and r["metadata"]["name"] == config_name)
        directives = [shlex.split(line, comments=True) for line in config.splitlines()]
        # Redis lowercases directive names before looking them up. Preserve
        # values/paths, but apply the same name semantics to this Source gate.
        directives = [[tokens[0].lower(), *tokens[1:]] for tokens in directives if tokens]
        auth_include = ["include", "/etc/seokpan/redis-server-auth/redis-auth.conf"]
        runtime_include = ["include", "/etc/seokpan/redis-runtime/redis-runtime.conf"]
        fixed = {
            "bind": ["0.0.0.0"], "protected-mode": ["yes"],
            "port": ["0"], "tls-port": ["6379"], "tls-auth-clients": ["no"],
            "tls-cert-file": ["/etc/seokpan/redis-server-tls/tls.crt"],
            "tls-key-file": ["/etc/seokpan/redis-server-tls/tls.key"],
            "tls-ca-cert-file": ["/etc/seokpan/redis-server-tls/ca.crt"],
            "tls-protocols": ["TLSv1.2 TLSv1.3"],
            "daemonize": ["no"], "logfile": [""],
        }
        # Keep this public file limited to the declared transport/process
        # boundary. AUTH, replication and data policies are never added here;
        # C must review its protected/external includes separately.
        if any(d[0] not in {"include", *fixed} for d in directives):
            blockers.append("Recovery public Redis configuration must contain only reviewed transport directives")
        if directives.count(auth_include) != 1 or directives.count(runtime_include) != 1 or \
                len([d for d in directives if d[0] == "include"]) != 2 or \
                any(d[0] in ("requirepass", "masterauth", "user", "aclfile") for d in directives):
            blockers.append("Recovery Redis authentication belongs only in its protected external include")
        for key, value in fixed.items():
            entries = [d for d in directives if d[0] == key]
            if entries != [[key, *value]] or \
                    (auth_include in directives and directives.index(entries[0]) < directives.index(auth_include)) or \
                    (runtime_include in directives and directives.index(entries[0]) < directives.index(runtime_include)):
                blockers.append("Recovery Redis fixed TLS-only settings must follow owner includes")
        # Do not require a particular final storage technology. Actual freshness,
        # permissions, data contents and persistence are C/A review/runtime gates.
        if "runtime-data" not in volumes or len(volumes["runtime-data"]) != 2 or \
                mounts.get("runtime-data", {}).get("mountPath") != "/data" or \
                mounts["runtime-data"].get("readOnly", False):
            blockers.append("Recovery Redis needs a reviewed isolated data volume interface")
    except (AttributeError, KeyError, TypeError, ValueError, IndexError, StopIteration, yaml.YAMLError):
        blockers.append("Recovery manifest structure is invalid or required references are missing")
    return list(dict.fromkeys(blockers))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=("lab", "cloud", "recovery"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kustomize", default=os.environ.get("KUSTOMIZE", "kustomize"))
    parser.add_argument("--recovery-namespace", default=os.environ.get("RECOVERY_NAMESPACE"))
    parser.add_argument("--recovery-registry", default=os.environ.get("RECOVERY_REGISTRY"))
    args = parser.parse_args()
    try:
        version = subprocess.run([args.kustomize, "version"], check=True,
                                 capture_output=True, text=True).stdout.strip()
        if version != "v5.7.1":
            print("release withheld: expected Kustomize v5.7.1", file=sys.stderr)
            return 2
        result = subprocess.run(
            [args.kustomize, "build", str(ROOT / "apps/overlays" / args.environment)],
            check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        print("release withheld: Kustomize version/build failed", file=sys.stderr)
        return 2
    blockers = []
    for label, pattern in (
        ("INPUT_REQUIRED", r"INPUT_REQUIRED"),
        ("reserved .invalid endpoint", r"\.invalid(?:[:/\s\"']|$)"),
        ("input-required draft marker", r"input-required"),
        ("zero-replica activation hold", r"(?m)^\s*replicas:\s*0\s*$"),
    ):
        if re.search(pattern, result.stdout):
            blockers.append(label)
    if not result.stdout.strip():
        blockers.append("empty manifest")
    if args.environment == "recovery":
        blockers.extend(recovery_manifest_blockers(result.stdout, args.recovery_namespace,
                                                    args.recovery_registry))
    else:
        blockers.extend(app_manifest_blockers(result.stdout, args.environment))
    if blockers:
        print("release withheld: " + ", ".join(blockers), file=sys.stderr)
        return 2
    # Commit the output atomically without replacing an existing artifact.
    # link() also refuses an existing symlink, including a dangling one.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=args.output.parent, delete=False) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(result.stdout)
        os.link(temp_path, args.output)
    except FileExistsError:
        print("release withheld: output already exists", file=sys.stderr)
        return 2
    except OSError:
        print("release withheld: could not write output", file=sys.stderr)
        return 2
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    print("source input gate passed; Runtime/owner acceptance remains separate", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

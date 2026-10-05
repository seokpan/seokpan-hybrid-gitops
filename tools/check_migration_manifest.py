"""Compare a reviewed App render and a separate one-shot Migration Job.

This Source check never applies a Job, reads Secret contents or connects to DB.
The supplied deadline and approval reference are inputs, not proof of C's receipt.
"""
import argparse
from pathlib import Path
import re
import sys

import yaml


def migration_manifest_blockers(app_rendered, job_rendered, reviewed_deadline_seconds):
    blockers = []
    try:
        app = list(yaml.safe_load_all(app_rendered))
        jobs = list(yaml.safe_load_all(job_rendered))
        if len(jobs) != 1 or jobs[0]["kind"] != "Job":
            raise ValueError
        job = jobs[0]
        backends = [r for r in app if r.get("kind") == "Deployment"
                    and r["metadata"]["name"] == "backend"]
        backend, = backends
        if not isinstance(reviewed_deadline_seconds, int) or isinstance(reviewed_deadline_seconds, bool) \
                or reviewed_deadline_seconds <= 0 or \
                not isinstance(job["spec"].get("activeDeadlineSeconds"), int) or \
                isinstance(job["spec"].get("activeDeadlineSeconds"), bool) or \
                job["spec"].get("activeDeadlineSeconds") != reviewed_deadline_seconds:
            blockers.append("Job deadline must equal the positive separately reviewed duration")
        namespace = backend["metadata"].get("namespace")
        if not isinstance(namespace, str) or len(namespace) > 63 or \
                re.fullmatch(r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?", namespace) is None or \
                job["metadata"].get("namespace") != namespace:
            blockers.append("Migration Job and reviewed Backend namespace must match")
        backend_pod = backend["spec"]["template"]["spec"]
        pod = job["spec"]["template"]["spec"]
        backend_container, = backend_pod["containers"]
        container, = pod["containers"]
        image = container.get("image", "")
        if not isinstance(image, str) or re.fullmatch(
                r"[a-zA-Z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+"
                r"(?::[a-zA-Z0-9_.-]+)?@sha256:[0-9a-f]{64}", image) is None or \
                image != backend_container.get("image"):
            blockers.append("Migration Image must equal the reviewed Backend registry digest reference")
        if pod.get("initContainers"):
            blockers.append("Migration review must not add unreviewed initContainer execution")
        if pod.get("restartPolicy") != "Never" or job["spec"].get("backoffLimit") != 0 or \
                job["spec"].get("parallelism") != 1 or job["spec"].get("completions") != 1:
            blockers.append("Migration must retain one-shot execution without automatic retries")
        if container.get("command") != ["seokpan-migration-gate"]:
            raise ValueError
        if container.get("envFrom") != backend_container.get("envFrom"):
            blockers.append("Migration configuration must equal the reviewed Backend rendered reference")
        env_from, = container["envFrom"]
        if set(env_from) != {"configMapRef"} or set(env_from["configMapRef"]) != {"name"}:
            raise ValueError
        config, = [r["data"] for r in app if r.get("kind") == "ConfigMap"
                   and r["metadata"]["name"] == env_from["configMapRef"]["name"]
                   and r["metadata"].get("namespace") == namespace]
        if container.get("env") != [{"name": "SEOKPAN_MIGRATION_DATABASE_URL", "valueFrom": {
                "secretKeyRef": {"name": "backend-db-migration", "key": "SEOKPAN_MIGRATION_DATABASE_URL"}}}]:
            blockers.append("Migration requires only its separate purpose-specific credential reference")
        args = list(container["args"])
        action = args.pop(0)
        values = {}
        execute = False
        while args:
            key = args.pop(0)
            if key == "--execute":
                if execute:
                    raise ValueError
                execute = True
            elif key in {"--expect-host", "--expect-port", "--expect-database", "--approval-ref", "--config"}:
                if key in values or not args:
                    raise ValueError
                values[key] = args.pop(0)
            else:
                raise ValueError
        if action not in {"current", "stamp-baseline", "upgrade-head"}:
            raise ValueError
        if action == "current" and execute:
            blockers.append("read-only schema inspection must not enable a writing action")
        if action != "current" and (not execute or not values.get("--approval-ref", "").strip()):
            blockers.append("writing Migration needs explicit execution and separate approval reference")
        if any(values.get(flag) != config.get(key) for flag, key in (
                ("--expect-host", "SEOKPAN_DATABASE_EXPECTED_HOST"),
                ("--expect-port", "SEOKPAN_DATABASE_EXPECTED_PORT"),
                ("--expect-database", "SEOKPAN_DATABASE_EXPECTED_NAME"))):
            blockers.append("Migration expected DB target must equal the reviewed App configuration")
        def ca_ref(pod_spec, workload_container):
            volume = next(v for v in pod_spec["volumes"] if v["name"] == "database-ca")
            mount = next(m for m in workload_container["volumeMounts"] if m["name"] == "database-ca")
            return volume, mount
        if ca_ref(pod, container) != ca_ref(backend_pod, backend_container) or \
                config.get("SEOKPAN_DATABASE_CA_FILE") != "/etc/seokpan/database-ca/ca.crt":
            blockers.append("Migration must use the same required DB CA reference and read-only path")
        ca_volume, ca_mount = ca_ref(pod, container)
        if ca_volume.get("configMap", {}).get("name") != "backend-database-ca" or \
                ca_volume["configMap"].get("optional", False) or \
                ca_volume["configMap"].get("items") != [{"key": "ca.crt", "path": "ca.crt"}] or \
                ca_mount.get("mountPath") != "/etc/seokpan/database-ca" or \
                ca_mount.get("readOnly") is not True or "subPath" in ca_mount:
            blockers.append("Migration DB CA must retain its required external read-only interface")
        if re.search(r"INPUT_REQUIRED|input-required|\.invalid(?:[:/\s\"']|$)", app_rendered + job_rendered):
            blockers.append("Migration review requires resolved App and Job inputs")
    except (AttributeError, KeyError, TypeError, ValueError, IndexError, StopIteration, yaml.YAMLError):
        blockers.append("Migration/App structure or required review inputs are invalid")
    return list(dict.fromkeys(blockers))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-manifest", type=Path, required=True)
    parser.add_argument("--job-manifest", type=Path, required=True)
    parser.add_argument("--reviewed-deadline-seconds", type=int, required=True)
    args = parser.parse_args()
    try:
        blockers = migration_manifest_blockers(args.app_manifest.read_text(encoding="utf-8"),
            args.job_manifest.read_text(encoding="utf-8"), args.reviewed_deadline_seconds)
    except OSError:
        blockers = ["could not read the separately reviewed manifests"]
    if blockers:
        print("migration source check withheld: " + ", ".join(blockers), file=sys.stderr)
        return 2
    print("migration Source inputs match; C review and actual execution remain separate")
    return 0


if __name__ == "__main__":
    sys.exit(main())

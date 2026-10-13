"""Check by default; explicit dry-run/create/verify on a locked existing target.

SOPS plaintext and Secret objects stay in subprocess pipes/in memory. Output is
only a fixed verdict, names and UID receipts. No activation, overwrite or retry.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import prepare_recovery_redis_inputs as prep

NAMESPACE = prep.NAMESPACE
CIPHER_SHA256 = "4c931e6240e054d84b935ed47efc02ce1cede42f4cd255cbf10060b414b74ec0"
MARKER = "seokpan.io/recovery-input-run"


def read_cipher(path, expected_hash, owner_uid):
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600 or before.st_uid != owner_uid:
            raise prep.Rejected("OWNED_REGULAR_MODE_600_REQUIRED")
        if before.st_size > prep.MAX_INPUT_BYTES:
            raise prep.Rejected("ENCRYPTED_INPUT_TOO_LARGE")
        raw = os.read(fd, prep.MAX_INPUT_BYTES + 1)
        after = os.fstat(fd)
        fields = ("st_ino", "st_dev", "st_mtime_ns", "st_ctime_ns", "st_size")
        if any(getattr(before, k) != getattr(after, k) for k in fields):
            raise prep.Rejected("INPUT_CHANGED_DURING_READ")
        if len(raw) != before.st_size or hashlib.sha256(raw).hexdigest() != expected_hash:
            raise prep.Rejected("ENCRYPTED_REVISION_MISMATCH")
        return raw
    finally:
        os.close(fd)


def decrypt_objects(cipher, runner=subprocess.run):
    try:
        result = runner(["sops", "--decrypt", "--input-type", "yaml", "--output-type", "json", "/dev/stdin"],
                        input=cipher, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise prep.Rejected("SOPS_LAUNCH_OR_TIMEOUT") from None
    if result.returncode:
        raise prep.Rejected("SOPS_DECRYPT_OR_MAC_FAILED")
    return prep.prepare_objects(prep.parse_input(result.stdout))


def same_object(obj, expected, run_id):
    meta = obj.get("metadata", {})
    if (obj.get("apiVersion") != "v1" or obj.get("kind") != expected["kind"] or
        meta.get("namespace") != NAMESPACE or meta.get("name") != expected["metadata"]["name"] or
        meta.get("deletionTimestamp") or meta.get("annotations", {}).get(MARKER) != run_id):
        return False
    if expected["kind"] == "Secret":
        try:
            actual = {k: base64.b64decode(v, validate=True).decode("utf-8") for k, v in obj.get("data", {}).items()}
        except (ValueError, UnicodeError, TypeError):
            return False
        return obj.get("type") == "Opaque" and actual == expected["stringData"]
    return not obj.get("binaryData") and obj.get("data") == expected["data"]


class Supplier:
    def __init__(self, context, api_server, namespace_uid, run_id, runner=subprocess.run):
        if not context or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,199}", context):
            raise prep.Rejected("EXISTING_CONTEXT_REQUIRED")
        if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]+)?/?", api_server or ""):
            raise prep.Rejected("EXPECTED_HTTPS_API_SERVER_REQUIRED")
        if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", namespace_uid or ""):
            raise prep.Rejected("EXISTING_NAMESPACE_UID_REQUIRED")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}", run_id or ""):
            raise prep.Rejected("SAFE_RUN_ID_REQUIRED")
        self.context, self.server, self.namespace_uid, self.run_id = context, api_server, namespace_uid, run_id
        self.runner, self.calls, self.create_attempts = runner, 0, 0
        self.receipts = []
        self.verified_receipts = []

    def call(self, args, value=None, absent_ok=False):
        self.calls += 1
        if self.calls > 35:
            raise prep.Rejected("CLI_CALL_LIMIT")
        cmd = ["oc", "--context", self.context, *args]
        try:
            kwargs = {"capture_output": True, "timeout": 20}
            if value is None:
                kwargs["stdin"] = subprocess.DEVNULL
            else:
                kwargs["input"] = json.dumps(value).encode()
            result = self.runner(cmd, **kwargs)
        except (OSError, subprocess.TimeoutExpired):
            raise prep.Rejected("CLI_OUTCOME_UNCERTAIN_NO_RETRY") from None
        if result.returncode:
            raise prep.Rejected("CLI_REJECTED_NO_RAW_OUTPUT")
        if absent_ok and not result.stdout.strip():
            return None
        if len(result.stdout) > 4 * 1024 * 1024:
            raise prep.Rejected("CLI_RESPONSE_TOO_LARGE")
        try:
            value = prep.parse_input(result.stdout)
        except Exception:
            raise prep.Rejected("CLI_RESPONSE_SHAPE") from None
        if not isinstance(value, dict):
            raise prep.Rejected("CLI_RESPONSE_SHAPE")
        return value

    def target(self):
        cfg = self.call(["config", "view", "--minify", "-o", "json"])
        clusters, users = cfg.get("clusters", []), cfg.get("users", [])
        if len(clusters) != 1 or len(users) != 1:
            raise prep.Rejected("EXACT_EXISTING_CONTEXT_REQUIRED")
        cluster = clusters[0].get("cluster", {})
        auth = users[0].get("user", {})
        if cluster.get("server") != self.server or cluster.get("insecure-skip-tls-verify"):
            raise prep.Rejected("TLS_TARGET_MISMATCH")
        if auth.get("exec") or auth.get("auth-provider"):
            raise prep.Rejected("NO_AUTH_EXEC_OR_SESSION_ISSUANCE")
        ns = self.call(["get", "namespace", NAMESPACE, "--request-timeout=15s", "-o", "json"])
        if (ns.get("metadata", {}).get("uid") != self.namespace_uid or
            ns.get("metadata", {}).get("name") != NAMESPACE or ns.get("metadata", {}).get("deletionTimestamp") or
            ns.get("status", {}).get("phase") != "Active"):
            raise prep.Rejected("EXISTING_NAMESPACE_IDENTITY_REQUIRED")

    def get(self, obj, absent_ok=False):
        args = ["get", obj["kind"].lower(), obj["metadata"]["name"], "-n", NAMESPACE,
                "--request-timeout=15s", "-o", "json"]
        if absent_ok:
            args.append("--ignore-not-found")
        return self.call(args, absent_ok=absent_ok)

    def supply(self, objects, mode):
        if mode not in ("dry-run", "create", "verify"):
            raise prep.Rejected("KNOWN_MODE_REQUIRED")
        for obj in objects:
            obj["metadata"]["annotations"] = {MARKER: self.run_id}
        self.target()
        if mode == "verify":
            for obj in objects:
                current = self.get(obj, absent_ok=True)
                if current is None:
                    raise prep.Rejected("SUPPLIED_OBJECT_MISSING")
                if not same_object(current, obj, self.run_id):
                    raise prep.Rejected("SUPPLIED_OBJECT_MISMATCH")
                uid = current.get("metadata", {}).get("uid")
                if not uid:
                    raise prep.Rejected("SUPPLIED_OBJECT_UID_MISSING")
                self.verified_receipts.append({"kind": obj["kind"], "name": obj["metadata"]["name"], "uid": uid})
            return "PASS_OBJECT_CONTENT_AND_RUN_MARKER_NOT_TLS_RUNTIME"
        # All existing objects must be absent before any server dry-run/create.
        for obj in objects:
            if self.get(obj, absent_ok=True) is not None:
                raise prep.Rejected("EXISTING_OBJECT_NO_OVERWRITE")
        for obj in objects:
            preview = self.call(["create", "-f", "-", "--dry-run=server", "--request-timeout=15s", "-o", "json"], obj)
            if not same_object(preview, obj, self.run_id):
                raise prep.Rejected("SERVER_DRY_RUN_NOT_PRESERVED")
        if mode == "dry-run":
            return "PASS_FIVE_SERVER_DRY_RUNS_NO_PERSISTED_CREATE"
        self.target()  # Identity remains unchanged immediately before first write.
        for obj in objects:
            self.create_attempts += 1
            created = self.call(["create", "-f", "-", "--request-timeout=15s", "-o", "json"], obj)
            uid = created.get("metadata", {}).get("uid")
            if not uid or not same_object(created, obj, self.run_id):
                raise prep.Rejected("CREATE_OUTCOME_REQUIRES_READ_NO_RETRY")
            self.receipts.append({"kind": obj["kind"], "name": obj["metadata"]["name"], "uid": uid})
            current = self.get(obj)
            if current.get("metadata", {}).get("uid") != uid or not same_object(current, obj, self.run_id):
                raise prep.Rejected("CREATED_OBJECT_READBACK_MISMATCH")
        return "PASS_FIVE_OBJECTS_CREATED_AND_READBACK_NOT_TLS_RUNTIME"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cipher", type=Path)
    parser.add_argument("--mode", choices=["check", "dry-run", "create", "verify"], default="check")
    parser.add_argument("--context")
    parser.add_argument("--api-server")
    parser.add_argument("--namespace-uid")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    supplier = None
    decrypt_attempts = 0
    try:
        if os.name != "posix":
            raise prep.Rejected("USE_EXISTING_LINUX_EXECUTOR")
        if args.mode != "check":
            supplier = Supplier(args.context, args.api_server, args.namespace_uid, args.run_id)
        cipher = read_cipher(args.cipher, CIPHER_SHA256, os.getuid())
        decrypt_attempts = 1
        objects = decrypt_objects(cipher)
        status = "PASS_PROTECTED_INPUT_MAPPING_NO_API" if supplier is None else supplier.supply(objects, args.mode)
        result = {"status": status, "object_mapping": prep.public_summary(objects)["objects"],
                  "api_apply": "NOT_RUN", "mode": args.mode}
        code = 0
    except prep.Rejected as exc:
        result = {"status": "STOP", "reason": str(exc), "no_retry": True}
        code = 2
    except Exception:
        result = {"status": "STOP", "reason": "LOCAL_OR_RESPONSE_ERROR_NO_RAW_OUTPUT", "no_retry": True}
        code = 2
    result.update(sops_decrypt_invocations=decrypt_attempts, cli_calls=0 if supplier is None else supplier.calls,
                  create_attempts=0 if supplier is None else supplier.create_attempts,
                  confirmed_created=[] if supplier is None else supplier.receipts,
                  verified_objects=[] if supplier is None else supplier.verified_receipts,
                  workload_activation="NOT_RUN", runtime_tls_auth="NOT_VERIFIED")
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())

"""Offline consumer preparation. No decryption, file output, API or activation.

Accept the five decrypted JSON fields reported by C via stdin. CLI emits only
names/key names and a fixed verdict. Objects are constructed only in memory.
PEM checks below are structure checks, never certificate/TLS acceptance.
"""
import hashlib
import json
import re
import sys

NAMESPACE = "seokpan-recovery"
CA_SHA256 = "9c3e26bd292230480f78b4f582f725a38340d73e674f302dcca4775534a12efc"
MAX_INPUT_BYTES = 262144
FIELDS = {"tls_crt", "tls_key", "ca_crt", "redis_auth_conf", "backend_redis_auth_token"}
RUNTIME = 'dir /data\nmaxmemory 384mb\nmaxmemory-policy noeviction\nsave ""\nappendonly no\n'


class Rejected(Exception):
    """Only fixed diagnostic codes may be placed in this exception."""


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def parse_input(raw):
    if len(raw) > MAX_INPUT_BYTES:
        raise Rejected("INPUT_TOO_LARGE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    except Rejected:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Rejected("INVALID_JSON") from None


def pem_structure(value, label):
    pattern = r"-----BEGIN " + label + r"-----\r?\n[A-Za-z0-9+/=\r\n]+-----END " + label + r"-----(?:\r?\n)?"
    return re.fullmatch(pattern, value) is not None


def prepare_objects(payload, *, expected_ca_sha256=CA_SHA256):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise Rejected("EXACT_FIVE_FIELDS_REQUIRED")
    if any(not isinstance(value, str) or not value or len(value.encode("utf-8")) > MAX_INPUT_BYTES
           for value in payload.values()):
        raise Rejected("NONEMPTY_BOUNDED_STRINGS_REQUIRED")
    if not pem_structure(payload["ca_crt"], "CERTIFICATE") or not pem_structure(payload["tls_crt"], "CERTIFICATE"):
        raise Rejected("CERTIFICATE_PEM_STRUCTURE_REQUIRED")
    if not any(pem_structure(payload["tls_key"], label)
               for label in ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY")):
        raise Rejected("PRIVATE_KEY_PEM_STRUCTURE_REQUIRED")
    if hashlib.sha256(payload["ca_crt"].encode("utf-8")).hexdigest() != expected_ca_sha256:
        raise Rejected("CA_REVISION_HASH_MISMATCH")
    token = payload["backend_redis_auth_token"]
    if re.fullmatch(r"[0-9a-fA-F]{64}", token) is None:
        raise Rejected("REPORTED_TOKEN_FORMAT_REQUIRED")
    lines = [line.strip() for line in payload["redis_auth_conf"].splitlines()
             if line.strip() and not line.strip().startswith("#")]
    if len(lines) != 1:
        raise Rejected("ONLY_REQUIREPASS_DIRECTIVE_ALLOWED")
    match = re.fullmatch(r'requirepass[ \t]+("[0-9a-fA-F]{64}"|[0-9a-fA-F]{64})', lines[0])
    if match is None:
        raise Rejected("ONLY_REQUIREPASS_DIRECTIVE_ALLOWED")
    if match[1].strip('"') != token:
        raise Rejected("SERVER_BACKEND_AUTH_MISMATCH")

    def obj(kind, name, data):
        value = {"apiVersion": "v1", "kind": kind,
                 "metadata": {"name": name, "namespace": NAMESPACE}}
        if kind == "Secret":
            value.update(type="Opaque", stringData=data)
        else:
            value["data"] = data
        return value

    return [
        obj("Secret", "recovery-redis-server-tls", {
            "tls.crt": payload["tls_crt"], "tls.key": payload["tls_key"], "ca.crt": payload["ca_crt"]}),
        obj("Secret", "recovery-redis-server-auth", {"redis-auth.conf": payload["redis_auth_conf"]}),
        obj("Secret", "backend-redis-runtime", {"SEOKPAN_REDIS_AUTH_TOKEN": token}),
        obj("ConfigMap", "backend-redis-ca", {"ca.crt": payload["ca_crt"]}),
        obj("ConfigMap", "recovery-redis-runtime-input-required", {"redis-runtime.conf": RUNTIME}),
    ]


def public_summary(objects):
    return {"status": "PASS_OFFLINE_MAPPING_ONLY", "namespace": NAMESPACE,
            "objects": [{"kind": obj["kind"], "name": obj["metadata"]["name"],
                         "keys": sorted(obj.get("stringData", obj.get("data", {})))} for obj in objects],
            "actual_sops_decryption_certificate_chain_san_key_pair_tls_auth": "NOT_VERIFIED",
            "api_apply_activation": "NOT_RUN"}


def main():
    try:
        payload = parse_input(sys.stdin.buffer.read(MAX_INPUT_BYTES + 1))
        result = public_summary(prepare_objects(payload))
        code = 0
    except Rejected as exc:
        result = {"status": "BLOCKED", "reason": str(exc), "api_apply_activation": "NOT_RUN"}
        code = 1
    except Exception:
        result = {"status": "BLOCKED", "reason": "LOCAL_INPUT_ERROR", "api_apply_activation": "NOT_RUN"}
        code = 1
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())

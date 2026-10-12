"""Offline inventory/hash and Recovery manifest comparison; no restore or secret decryption."""
import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
import yaml
from render_release import recovery_manifest_blockers

ROLES = {"app_manifest", "image_archive", "database_dump", "database_ca", "redis_ca", "protected_inputs", "tool_archive", "source_archive"}
# v2 keeps mutable periodic Data outside the immutable asset inventory.
DATABASE_RESTORE = {
    "database": "stone_game",
    "backup_kind": "periodic",
    "selection": "backup_id_utc_descending_sha256_valid",
    "procedure": "seokpan-hybrid-infra#48",
    "script": "ansible/data/controller/restore.sh",
    "rpo_limit_seconds": 1800,
}
REFS = {
    "backend-db-runtime": ["SEOKPAN_IDENTITY_DATABASE_URL", "SEOKPAN_GAME_DATABASE_URL"],
    "backend-db-migration": ["SEOKPAN_MIGRATION_DATABASE_URL"],
    "backend-redis-runtime": ["SEOKPAN_REDIS_AUTH_TOKEN"],
    "recovery-harbor-pull": [".dockerconfigjson"],
    "recovery-redis-server-tls": ["tls.crt", "tls.key", "ca.crt"],
    "recovery-redis-server-auth": ["redis-auth.conf"],
}
class Invalid(ValueError):
    pass

def pairs(rows):
    result={}
    for key,value in rows:
        if key in result: raise Invalid("DUPLICATE_JSON_KEY")
        result[key]=value
    return result

def exact(obj, keys):
    if not isinstance(obj,dict) or set(obj)!=set(keys): raise Invalid("INVENTORY_FIELDS")

def protected_directory(s):
    if not stat.S_ISDIR(s.st_mode): raise Invalid("BUNDLE_DIRECTORY")
    if os.name == "posix" and (s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700):
        raise Invalid("BUNDLE_DIRECTORY_OWNER_OR_MODE")

def safe_file(root, name):
    if not isinstance(name,str) or "\\" in name or not name or len(name)>255:
        raise Invalid("BUNDLE_PATH")
    relative=PurePosixPath(name)
    if relative.is_absolute() or any(p in ("..", ".") for p in relative.parts) or relative.as_posix()!=name or ":" in name:
        raise Invalid("BUNDLE_PATH")
    path=root
    for index,part in enumerate(relative.parts):
        path=path/part
        s=path.lstat()
        if stat.S_ISLNK(s.st_mode) or getattr(s,"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",1024):
            raise Invalid("BUNDLE_LINK")
        if index < len(relative.parts)-1: protected_directory(s)
    if os.name == "posix" and (path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o600):
        raise Invalid("BUNDLE_FILE_OWNER_OR_MODE")
    if not path.is_file() or path.stat().st_size==0 or path.stat().st_size>64*1024**3:
        raise Invalid("BUNDLE_FILE_SIZE")
    return path

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def encrypted_value(value):
    if not isinstance(value, str): return False
    match = re.fullmatch(r"ENC\[AES256_GCM,data:([A-Za-z0-9+/=]*),iv:([A-Za-z0-9+/=]+),tag:([A-Za-z0-9+/=]+),type:(str|int|float|bool)\]", value)
    if match is None: return False
    try:
        for part in match.group(1, 2, 3): base64.b64decode(part, validate=True)
    except ValueError: return False
    return True


class ProtectedYamlLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent): raise Invalid("SOPS_ALIAS")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result: raise Invalid("SOPS_MAPPING_KEY")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def protected_input_format(path):
    # Structural acceptance only: no decryption, MAC verification or key access.
    with path.open("rb") as stream: header = stream.read(64)
    if header.startswith((b"age-encryption.org/v1\n", b"-----BEGIN AGE ENCRYPTED FILE-----")):
        return "AGE_ENVELOPE_MARKER_ONLY"
    if path.stat().st_size > 262144: raise Invalid("SOPS_SIZE")
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=ProtectedYamlLoader)
    except (UnicodeError, yaml.YAMLError, RecursionError):
        raise Invalid("SOPS_DOCUMENT") from None
    if not isinstance(document, dict) or "sops" not in document or len(document) < 2:
        raise Invalid("SOPS_DOCUMENT")
    metadata = document["sops"]
    if not isinstance(metadata, dict) or not encrypted_value(metadata.get("mac")):
        raise Invalid("SOPS_METADATA")
    if not isinstance(metadata.get("version"), str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", metadata["version"]):
        raise Invalid("SOPS_METADATA")
    recipients = metadata.get("age")
    if not isinstance(recipients, list) or not recipients or len(recipients) > 32:
        raise Invalid("SOPS_AGE_METADATA")
    for row in recipients:
        if not isinstance(row, dict) or not isinstance(row.get("recipient"), str) or not re.fullmatch(r"age1[0-9a-z]+", row["recipient"]):
            raise Invalid("SOPS_AGE_METADATA")
        envelope = row.get("enc")
        if not isinstance(envelope, str) or not envelope.startswith("-----BEGIN AGE ENCRYPTED FILE-----\n") or not envelope.rstrip().endswith("-----END AGE ENCRYPTED FILE-----"):
            raise Invalid("SOPS_AGE_METADATA")
    count = 0
    def visit(value, depth=0):
        nonlocal count
        count += 1
        if depth > 32 or count > 10000: raise Invalid("SOPS_SHAPE_LIMIT")
        if isinstance(value, dict):
            if not value: raise Invalid("SOPS_EMPTY_PAYLOAD")
            for child in value.values(): visit(child, depth + 1)
        elif isinstance(value, list):
            if not value: raise Invalid("SOPS_EMPTY_PAYLOAD")
            for child in value: visit(child, depth + 1)
        elif not encrypted_value(value): raise Invalid("SOPS_PLAINTEXT_PAYLOAD")
    for key, value in document.items():
        if key != "sops": visit(value)
    return "SOPS_AGE_ENCRYPTED_VALUES_STRUCTURE_ONLY"

def check(root, inventory_name="inventory.json"):
    # Intended for a quiescent, owner-protected local copy. Concurrent modifications
    # and storage failure-domain independence require a separate owner receipt.
    root=Path(root)
    s=root.lstat()
    if not stat.S_ISDIR(s.st_mode) or root.is_symlink() or getattr(s,"st_file_attributes",0)&1024:
        raise Invalid("BUNDLE_ROOT")
    if os.name == "posix" and (s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700):
        raise Invalid("BUNDLE_ROOT_OWNER_OR_MODE")
    inventory=safe_file(root,inventory_name)
    if inventory.stat().st_size>65536: raise Invalid("INVENTORY_SIZE")
    try: c=json.loads(inventory.read_text(encoding="utf-8"),object_pairs_hook=pairs)
    except (UnicodeError,json.JSONDecodeError): raise Invalid("INVENTORY_JSON") from None
    version = c.get("schema_version") if isinstance(c, dict) else None
    keys=("schema_version","environment","namespace","registry","source_revisions","images","server_command","secret_references","artifacts")
    exact(c, keys + (("database_restore",) if version == 2 else ()))
    if type(version) is not int or version not in (1, 2) or c["environment"]!="recovery":
        raise Invalid("INVENTORY_VERSION_OR_ENVIRONMENT")
    if version == 2 and c["database_restore"] != DATABASE_RESTORE:
        raise Invalid("EXTERNAL_DATABASE_RESTORE_CONTRACT")
    if not isinstance(c["namespace"],str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*",c["namespace"]) or len(c["namespace"])>63 or c["namespace"]=="default" or c["namespace"].startswith(("kube-","openshift-")) or "input-required" in c["namespace"]:
        raise Invalid("ISOLATED_NAMESPACE")
    exact(c["source_revisions"],("app","gitops"))
    if any(not isinstance(v,str) or not re.fullmatch(r"[a-f0-9]{40}",v) for v in c["source_revisions"].values()):
        raise Invalid("SOURCE_REVISION")
    if c["secret_references"]!=REFS: raise Invalid("SECRET_REFERENCE_CONTRACT")
    if c["server_command"]!=["redis-server"]: raise Invalid("SERVER_SOURCE_CONTRACT_REVIEW_REQUIRED")
    exact(c["images"],("backend","frontend","recovery-redis"))
    if not isinstance(c["registry"],str) or not re.fullmatch(r"[a-zA-Z0-9.-]+(?::[0-9]+)?",c["registry"]) or c["registry"].endswith(".invalid"):
        raise Invalid("REGISTRY_INPUT")
    if any(not isinstance(v,str) or not re.fullmatch(re.escape(c["registry"])+r"/[a-z0-9._/-]+@sha256:[0-9a-f]{64}",v) for v in c["images"].values()):
        raise Invalid("IMMUTABLE_LOCAL_IMAGES")
    rows=c["artifacts"]
    required_roles = ROLES if version == 1 else ROLES - {"database_dump"}
    if not isinstance(rows,list) or len(rows)!=len(required_roles): raise Invalid("ARTIFACT_ROLES")
    roles={}; paths=set(); allowed={inventory_name}
    for row in rows:
        exact(row,("role","path","sha256"))
        if not isinstance(row["role"],str) or row["role"] not in required_roles or row["role"] in roles: raise Invalid("ARTIFACT_ROLES")
        if not isinstance(row["sha256"],str) or not re.fullmatch(r"[a-f0-9]{64}",row["sha256"]): raise Invalid("ARTIFACT_HASH_FORMAT")
        path=safe_file(root,row["path"])
        if row["path"].casefold() in paths or row["path"].casefold()==inventory_name.casefold(): raise Invalid("DUPLICATE_ARTIFACT_PATH")
        paths.add(row["path"].casefold())
        allowed.add(row["path"])
        if digest(path)!=row["sha256"]: raise Invalid("ARTIFACT_HASH_MISMATCH")
        roles[row["role"]]=path
    # Every subdirectory must be owner-protected; only tracked regular files
    # are accepted. Archives remain opaque hashed files, never restored here.
    # Casefold prevents portable-name collisions above; membership below must
    # preserve spelling so case variants cannot masquerade as tracked files.
    for item in root.rglob("*"):
        state=item.lstat()
        if stat.S_ISLNK(state.st_mode) or getattr(state,"st_file_attributes",0)&1024: raise Invalid("BUNDLE_LINK")
        if stat.S_ISDIR(state.st_mode):
            protected_directory(state)
        elif not stat.S_ISREG(state.st_mode):
            raise Invalid("BUNDLE_SPECIAL_FILE")
        elif item.relative_to(root).as_posix() not in allowed:
            raise Invalid("UNTRACKED_BUNDLE_FILE")
    protected=roles["protected_inputs"]
    protected_format = protected_input_format(protected)
    for role in ("database_ca","redis_ca"):
        path=roles[role]
        if path.stat().st_size>1024*1024: raise Invalid("CA_SIZE")
        data=path.read_bytes()
        if b"-----BEGIN CERTIFICATE-----" not in data or b"PRIVATE KEY" in data:
            raise Invalid("PUBLIC_CA_REQUIRED")
    manifest=roles["app_manifest"]
    if manifest.stat().st_size>2*1024*1024: raise Invalid("MANIFEST_SIZE")
    rendered=manifest.read_text(encoding="utf-8")
    if re.search(r"INPUT_REQUIRED|input-required|\.invalid(?:[:/\s]|$)",rendered): raise Invalid("UNRESOLVED_MANIFEST")
    if recovery_manifest_blockers(rendered,c["namespace"],c["registry"]): raise Invalid("RECOVERY_MANIFEST_GATE")
    resources=list(yaml.safe_load_all(rendered))
    observed={r["metadata"]["name"]:r["spec"]["template"]["spec"]["containers"][0]["image"] for r in resources if r["kind"] in ("Deployment","StatefulSet")}
    if observed!=c["images"]: raise Invalid("MANIFEST_IMAGE_MAPPING")
    redis=next(r for r in resources if r["kind"]=="StatefulSet")
    if redis["spec"]["template"]["spec"]["containers"][0]["command"]!=c["server_command"]: raise Invalid("MANIFEST_SERVER_COMMAND")
    return {"artifact_count":len(roles),"result":"SOURCE_INVENTORY_HASH_AND_MANIFEST_PASS","protected_inputs_format":protected_format,"database_source":"EXTERNAL_PERIODIC_RESTORE_REQUIRED" if version == 2 else "LEGACY_FIXED_DUMP_NOT_CURRENT_RPO_EVIDENCE","runtime_restore_independent_copy_identity_rto_rpo":"NOT_VERIFIED"}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle",type=Path)
    parser.add_argument("--inventory",default="inventory.json")
    args=parser.parse_args()
    try:
        print(json.dumps(check(args.bundle,args.inventory),sort_keys=True));return 0
    except (Invalid,OSError,ValueError,KeyError,TypeError,StopIteration,RecursionError,yaml.YAMLError):
        # No file contents, identities, paths, Secret values or raw error output.
        print("RECOVERY_BUNDLE_INVENTORY: BLOCKED / INPUT_HASH_OR_MANIFEST",file=sys.stderr);return 2
if __name__=="__main__": sys.exit(main())

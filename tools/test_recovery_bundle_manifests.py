import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml
import test_app_manifests
from check_recovery_bundle import DATABASE_RESTORE, REFS, Invalid, check
ROOT=Path(__file__).resolve().parents[1]
class RecoveryBundleTests(unittest.TestCase):
    def bundle(self,root):
        case=test_app_manifests.RecoveryReleaseBoundaries()
        manifest=case.fixture()
        payloads={"app_manifest":yaml.safe_dump_all(manifest).encode(),"image_archive":b"synthetic OCI archive, not actual images","database_dump":b"synthetic dump, not actual data","database_ca":b"-----BEGIN CERTIFICATE-----\nfixture-only\n-----END CERTIFICATE-----\n","redis_ca":b"-----BEGIN CERTIFICATE-----\nfixture-only\n-----END CERTIFICATE-----\n","protected_inputs":b"age-encryption.org/v1\nsynthetic-envelope-not-decryptable","tool_archive":b"synthetic tools","source_archive":b"synthetic source"}
        c={"schema_version":1,"environment":"recovery","namespace":case.namespace,"registry":case.registry,"source_revisions":{"app":"a"*40,"gitops":"b"*40},"images":{r["metadata"]["name"]:r["spec"]["template"]["spec"]["containers"][0]["image"] for r in manifest if r["kind"] in ("Deployment","StatefulSet")},"server_command":["redis-server"],"secret_references":copy.deepcopy(REFS),"artifacts":[]}
        for role,data in payloads.items():
            path=role+".fixture";(root/path).write_bytes(data);(root/path).chmod(0o600)
            c["artifacts"].append({"role":role,"path":path,"sha256":hashlib.sha256(data).hexdigest()})
        self.save(root,c);return c
    def save(self,root,c):
        (root/"inventory.json").write_text(json.dumps(c),encoding="utf-8");(root/"inventory.json").chmod(0o600)
    def rehash(self,root,c,role):
        row=next(r for r in c["artifacts"] if r["role"]==role);row["sha256"]=hashlib.sha256((root/row["path"]).read_bytes()).hexdigest();self.save(root,c)
    def test_hash_manifest_pass_does_not_claim_archive_or_runtime_acceptance(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.bundle(root);result=check(root)
            self.assertEqual(result["artifact_count"],8)
            self.assertEqual(result["runtime_restore_independent_copy_identity_rto_rpo"],"NOT_VERIFIED")
            self.assertEqual(result["result"],"SOURCE_INVENTORY_HASH_AND_MANIFEST_PASS")
    def test_changed_and_missing_artifact_fail(self):
        for missing in (False,True):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as td:
                root=Path(td);self.bundle(root);p=root/"database_dump.fixture"
                p.unlink() if missing else p.write_bytes(b"changed")
                with self.assertRaises((Invalid,OSError)):check(root)
    def test_traversal_duplicate_unknown_and_live_secret_metadata_fail(self):
        mutations=[lambda c:c["artifacts"][0].update(path="../external"),lambda c:c["artifacts"][0].update(path="C:/external"),lambda c:c["artifacts"][1].update(path=c["artifacts"][0]["path"]),lambda c:c.update(secret_value="sentinel-do-not-output"),lambda c:c["secret_references"].update(client_secret="sentinel"),lambda c:c.update(source_revisions={"app":"main","gitops":"b"*40}),lambda c:c.update(namespace="default"),lambda c:c.update(server_command=["valkey-server"]),lambda c:c["images"].update(backend="harbor.fixture.test/backend:latest")]
        for n,mutate in enumerate(mutations):
            with self.subTest(case=n),tempfile.TemporaryDirectory() as td:
                root=Path(td);c=self.bundle(root);mutate(c);self.save(root,c)
                with self.assertRaises(Invalid):check(root)
    def test_plaintext_inputs_and_ca_private_key_fail_after_rehash(self):
        for role,data in [("protected_inputs",b"plaintext-auth"),("database_ca",b"-----BEGIN CERTIFICATE-----\n-----BEGIN PRIVATE KEY-----")]:
            with self.subTest(role=role),tempfile.TemporaryDirectory() as td:
                root=Path(td);c=self.bundle(root);(root/(role+".fixture")).write_bytes(data);self.rehash(root,c,role)
                with self.assertRaises(Invalid):check(root)
    def test_manifest_namespace_hold_and_image_mapping_fail(self):
        for mutation in ("namespace","hold","mapping"):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as td:
                root=Path(td);c=self.bundle(root)
                if mutation=="mapping":c["images"]["backend"]=c["images"]["backend"][:-64]+"c"*64
                else:
                    path=root/"app_manifest.fixture";docs=list(yaml.safe_load_all(path.read_text()))
                    if mutation=="namespace":docs[0]["metadata"]["namespace"]="wrong-owner"
                    else:next(r for r in docs if r["kind"]=="Deployment")["spec"]["replicas"]=0
                    path.write_text(yaml.safe_dump_all(docs));self.rehash(root,c,"app_manifest")
                self.save(root,c)
                with self.assertRaises(Invalid):check(root)
    def test_untracked_file_and_duplicate_json_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.bundle(root);(root/"plaintext-untracked").write_text("sentinel")
            with self.assertRaises(Invalid):check(root)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.bundle(root);(root/"inventory.json").write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaises(Invalid):check(root)
    @unittest.skipUnless(os.name == "posix", "POSIX owner/mode and symlink acceptance is verified on Linux CI")
    def test_symlink_and_unsafe_file_mode_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.bundle(root)
            artifact=root/"database_dump.fixture";artifact.chmod(0o644)
            with self.assertRaises(Invalid):check(root)
            artifact.chmod(0o600)
            outside=root.parent/(root.name+"-outside")
            outside.write_bytes(artifact.read_bytes());outside.chmod(0o600)
            try:
                artifact.unlink();artifact.symlink_to(outside)
                with self.assertRaises(Invalid):check(root)
            finally:outside.unlink()
    @unittest.skipUnless(os.name == "posix", "POSIX nested directory protection is verified on Linux CI")
    def test_nested_directory_permissions_and_owner_are_rejected(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.bundle(root);nested=root/"sub";nested.mkdir(mode=0o700)
            row=next(r for r in c["artifacts"] if r["role"]=="database_dump")
            (root/row["path"]).rename(nested/"dump.fixture");row["path"]="sub/dump.fixture";self.save(root,c)
            self.assertEqual(check(root)["result"],"SOURCE_INVENTORY_HASH_AND_MANIFEST_PASS")
            nested.chmod(0o777)
            with self.assertRaisesRegex(Invalid,"BUNDLE_DIRECTORY_OWNER_OR_MODE"):check(root)
            nested.chmod(0o700)
            original=Path.lstat
            def changed_owner(path,*args,**kwargs):
                actual=original(path,*args,**kwargs)
                if path==nested:
                    return SimpleNamespace(st_mode=actual.st_mode,st_uid=os.getuid()+1,st_file_attributes=0)
                return actual
            with patch.object(Path,"lstat",changed_owner):
                with self.assertRaisesRegex(Invalid,"BUNDLE_DIRECTORY_OWNER_OR_MODE"):check(root)
            extra=root/"empty-unprotected";extra.mkdir();extra.chmod(0o777)
            with self.assertRaisesRegex(Invalid,"BUNDLE_DIRECTORY_OWNER_OR_MODE"):check(root)
    @unittest.skipUnless(os.name == "posix", "POSIX special files are verified on Linux CI")
    def test_untracked_and_tracked_fifo_are_rejected_without_reading(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.bundle(root);fifo=root/"untracked-pipe";os.mkfifo(fifo,mode=0o600)
            with self.assertRaisesRegex(Invalid,"BUNDLE_SPECIAL_FILE"):check(root)
            fifo.unlink()
            row=next(r for r in c["artifacts"] if r["role"]=="database_dump")
            artifact=root/row["path"];artifact.unlink();os.mkfifo(artifact,mode=0o600)
            with self.assertRaises(Invalid):check(root)
    def test_untracked_case_variant_inventory_and_artifact_are_rejected(self):
        for name in ("Inventory.JSON", "DATABASE_DUMP.fixture", "SUB/DUMP.fixture"):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                root=Path(td);c=self.bundle(root)
                if "/" in name:
                    folder=root/"sub";folder.mkdir(mode=0o700)
                    row=next(r for r in c["artifacts"] if r["role"]=="database_dump")
                    (root/row["path"]).rename(folder/"dump.fixture")
                    row["path"]="sub/dump.fixture";self.save(root,c)
                    original=folder/"dump.fixture"
                else:original=root/("inventory.json" if name=="Inventory.JSON" else "database_dump.fixture")
                extra=root/name
                if extra.exists():self.skipTest("requires a case-sensitive filesystem; covered by Linux CI")
                extra.parent.mkdir(mode=0o700,exist_ok=True)
                extra.write_bytes(original.read_bytes());extra.chmod(0o600)
                with self.assertRaisesRegex(Invalid,"UNTRACKED_BUNDLE_FILE"):check(root)
                r=subprocess.run([sys.executable,str(ROOT/"tools/check_recovery_bundle.py"),str(root)],capture_output=True,text=True,timeout=15)
                self.assertEqual(r.returncode,2)
                self.assertNotIn(str(root),r.stdout+r.stderr)
                self.assertNotIn(name,r.stdout+r.stderr)
    def test_mismatched_case_in_inventory_and_artifact_paths_is_rejected(self):
        for inventory in (True,False):
            with self.subTest(inventory=inventory),tempfile.TemporaryDirectory() as td:
                root=Path(td);self.bundle(root)
                original=root/("inventory.json" if inventory else "database_dump.fixture")
                renamed=root/("Inventory.JSON" if inventory else "DATABASE_DUMP.fixture")
                temporary=root/"rename-staging";original.rename(temporary);temporary.rename(renamed)
                with self.assertRaises((Invalid,OSError)):check(root)
    def test_exact_mixed_case_registered_paths_are_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.bundle(root);folder=root/"Sub";folder.mkdir(mode=0o700)
            row=next(r for r in c["artifacts"] if r["role"]=="database_dump")
            (root/row["path"]).rename(folder/"Dump.FIXTURE");row["path"]="Sub/Dump.FIXTURE";self.save(root,c)
            temporary=root/"rename-staging";(root/"inventory.json").rename(temporary);temporary.rename(root/"Inventory.JSON")
            self.assertEqual(check(root,"Inventory.JSON")["result"],"SOURCE_INVENTORY_HASH_AND_MANIFEST_PASS")
    def test_casefold_duplicate_registered_artifact_paths_remain_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.bundle(root);first=c["artifacts"][0];other=c["artifacts"][1]
            (root/other["path"]).unlink()
            other.update(path=first["path"].upper(),sha256=first["sha256"])
            duplicate=root/other["path"]
            if not duplicate.exists():duplicate.write_bytes((root/first["path"]).read_bytes());duplicate.chmod(0o600)
            self.save(root,c)
            with self.assertRaisesRegex(Invalid,"DUPLICATE_ARTIFACT_PATH"):check(root)
    def test_cli_failure_does_not_expose_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.bundle(root);c["secret_references"]["do-not-expose"]=["sentinel-password"];self.save(root,c)
            r=subprocess.run([sys.executable,str(ROOT/"tools/check_recovery_bundle.py"),str(root)],capture_output=True,text=True)
            self.assertEqual(r.returncode,2)
            self.assertNotIn("sentinel",r.stdout+r.stderr)
            self.assertNotIn(str(root),r.stdout+r.stderr)

    @staticmethod
    def sops_fixture():
        # Format-only synthetic ciphertext; never a decryption/MAC proof.
        value = "ENC[AES256_GCM,data:YWJj,iv:YWJj,tag:YWJj,type:str]"
        return {"credentials": {"password": value}, "sops": {
            "age": [{"recipient": "age1fixture", "enc":
                "-----BEGIN AGE ENCRYPTED FILE-----\nfixture\n-----END AGE ENCRYPTED FILE-----\n"}],
            "mac": value, "version": "3.9.0"}}

    def replace_protected(self, root, inventory, data):
        (root/"protected_inputs.fixture").write_bytes(data)
        self.rehash(root, inventory, "protected_inputs")

    def test_sops_age_yaml_accepted_without_claiming_decryption(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); c=self.bundle(root)
            self.replace_protected(root,c,yaml.safe_dump(self.sops_fixture()).encode())
            result=check(root)
            self.assertEqual(result["protected_inputs_format"],"SOPS_AGE_ENCRYPTED_VALUES_STRUCTURE_ONLY")
            self.assertEqual(result["runtime_restore_independent_copy_identity_rto_rpo"],"NOT_VERIFIED")

    def test_sops_plaintext_nested_values_and_partial_encryption_rejected(self):
        for value in ("sentinel-password", True, 12, None, {"nested": "sentinel-password"}, ["sentinel-password"], {}):
            with self.subTest(value_type=type(value).__name__),tempfile.TemporaryDirectory() as td:
                root=Path(td); c=self.bundle(root); payload=self.sops_fixture()
                payload["credentials"]["extra"]=value
                self.replace_protected(root,c,yaml.safe_dump(payload).encode())
                with self.assertRaises(Invalid): check(root)

    def test_sops_metadata_and_bad_ciphertext_rejected(self):
        mutations=[lambda d:d["sops"].update(mac="plaintext"),lambda d:d["sops"].update(age=[]),
                   lambda d:d["sops"].update(password="sentinel-password"),
                   lambda d:d["sops"]["age"][0].update(password="sentinel-password"),
                   lambda d:d["sops"].update(lastmodified="sentinel-password"),
                   lambda d:d["sops"].update(version="latest"),
                   lambda d:d["sops"]["age"][0].update(enc="plaintext"),
                   lambda d:d["credentials"].update(password="ENC[AES256_GCM,data:!,iv:YWJj,tag:YWJj,type:str]")]
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td); c=self.bundle(root); payload=self.sops_fixture(); mutate(payload)
                self.replace_protected(root,c,yaml.safe_dump(payload).encode())
                with self.assertRaises(Invalid): check(root)

    def test_sops_duplicate_keys_aliases_and_oversize_rejected(self):
        fixture=yaml.safe_dump(self.sops_fixture()).encode()
        for data in (b"password: first\npassword: second\n"+fixture,
                     b"value: &shared encrypted\nother: *shared\n"+fixture,
                     b"#"*262145):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td); c=self.bundle(root); self.replace_protected(root,c,data)
                with self.assertRaises(Invalid): check(root)

    def version2(self, root):
        c=self.bundle(root); c["schema_version"]=2
        c["database_restore"]=copy.deepcopy(DATABASE_RESTORE)
        row=next(r for r in c["artifacts"] if r["role"]=="database_dump")
        (root/row["path"]).unlink(); c["artifacts"].remove(row); self.save(root,c)
        return c

    def test_v2_external_periodic_contract_needs_no_fixed_dump(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self.version2(root); result=check(root)
            self.assertEqual(result["artifact_count"],7)
            self.assertEqual(result["database_source"],"EXTERNAL_PERIODIC_RESTORE_REQUIRED")
            self.assertEqual(result["runtime_restore_independent_copy_identity_rto_rpo"],"NOT_VERIFIED")

    def test_v2_cannot_substitute_rehearsal_mtime_database_or_rpo(self):
        for key,value in (("backup_kind","rehearsal"),("selection","file_mtime"),
                          ("database","other_db"),("rpo_limit_seconds",3600)):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as td:
                root=Path(td); c=self.version2(root); c["database_restore"][key]=value; self.save(root,c)
                with self.assertRaisesRegex(Invalid,"EXTERNAL_DATABASE_RESTORE_CONTRACT"): check(root)

    def test_v2_fixed_dump_cannot_masquerade_as_current_periodic(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); c=self.bundle(root); c["schema_version"]=2
            c["database_restore"]=copy.deepcopy(DATABASE_RESTORE); self.save(root,c)
            with self.assertRaisesRegex(Invalid,"ARTIFACT_ROLES"): check(root)

    def test_sops_cli_error_stays_redacted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); c=self.bundle(root); payload=self.sops_fixture()
            payload["credentials"]["password"]="sentinel-password"
            self.replace_protected(root,c,yaml.safe_dump(payload).encode())
            r=subprocess.run([sys.executable,str(ROOT/"tools/check_recovery_bundle.py"),str(root)],capture_output=True,text=True)
            self.assertEqual(r.returncode,2)
            self.assertNotIn("sentinel",r.stdout+r.stderr)
            self.assertNotIn(str(root),r.stdout+r.stderr)
if __name__=="__main__":unittest.main()

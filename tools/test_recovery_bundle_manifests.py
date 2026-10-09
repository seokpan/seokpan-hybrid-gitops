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
from check_recovery_bundle import REFS, Invalid, check
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
    def test_cli_failure_does_not_expose_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);c=self.bundle(root);c["secret_references"]["do-not-expose"]=["sentinel-password"];self.save(root,c)
            r=subprocess.run([sys.executable,str(ROOT/"tools/check_recovery_bundle.py"),str(root)],capture_output=True,text=True)
            self.assertEqual(r.returncode,2)
            self.assertNotIn("sentinel",r.stdout+r.stderr)
            self.assertNotIn(str(root),r.stdout+r.stderr)
if __name__=="__main__":unittest.main()

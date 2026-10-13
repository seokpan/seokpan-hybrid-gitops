"""Fake SOPS/CLI responses only; no real credentials, cluster or writes."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import prepare_recovery_redis_inputs as prep
from supply_recovery_redis_inputs import NAMESPACE, Supplier, decrypt_objects, read_cipher


def objects():
    cert = "-----BEGIN CERTIFICATE-----\nQUJD\n-----END CERTIFICATE-----\n"
    payload = {"tls_crt": cert, "ca_crt": cert,
               "tls_key": "-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----\n",
               "redis_auth_conf": "requirepass " + "a" * 64 + "\n", "backend_redis_auth_token": "a" * 64}
    return prep.prepare_objects(payload, expected_ca_sha256=hashlib.sha256(cert.encode()).hexdigest())


class FakeCLI:
    def __init__(self):
        self.calls, self.saved = [], {}
        self.server, self.ns_uid = "https://api.recovery.test:6443", "namespace-uid"
        self.fail_create, self.mutate_preview, self.auth = None, False, {}

    def __call__(self, cmd, input=None, **kwargs):
        args = cmd[3:]
        self.calls.append(args)
        if args[0] == "config":
            value = {"clusters": [{"cluster": {"server": self.server}}], "users": [{"user": self.auth}]}
        elif args[:2] == ["get", "namespace"]:
            value = {"metadata": {"name": NAMESPACE, "uid": self.ns_uid}, "status": {"phase": "Active"}}
        elif args[0] == "get":
            value = self.saved.get(args[2])
            if value is None:
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        else:
            value = json.loads(input)
            if value["kind"] == "Secret":
                value["data"] = {k: base64.b64encode(v.encode()).decode() for k, v in value.pop("stringData").items()}
            if "--dry-run=server" in args:
                if self.mutate_preview:
                    value["data"] = {}
            else:
                number = len(self.saved) + 1
                if number == self.fail_create:
                    raise subprocess.TimeoutExpired(cmd, 20)
                value["metadata"]["uid"] = f"object-{number}"
                self.saved[value["metadata"]["name"]] = copy.deepcopy(value)
        return SimpleNamespace(returncode=0, stdout=json.dumps(value).encode(), stderr=b"private sentinel error")


class SupplyTests(unittest.TestCase):
    def supplier(self, cli):
        return Supplier("existing-context", "https://api.recovery.test:6443", "namespace-uid", "run-1", cli)

    def test_exact_mapping_and_shared_ca(self):
        rows = objects()
        self.assertEqual([r["kind"] for r in rows], ["Secret"] * 3 + ["ConfigMap"] * 2)
        self.assertEqual(rows[0]["stringData"]["ca.crt"], rows[3]["data"]["ca.crt"])
        self.assertTrue(all(r["metadata"]["namespace"] == NAMESPACE for r in rows))

    def test_dry_run_all_five_no_persisted_writes(self):
        cli = FakeCLI()
        self.assertIn("NO_PERSISTED_CREATE", self.supplier(cli).supply(objects(), "dry-run"))
        self.assertFalse(cli.saved)
        self.assertEqual(sum("--dry-run=server" in a for a in cli.calls), 5)

    def test_create_readback_and_separate_verify(self):
        cli = FakeCLI()
        supplier = self.supplier(cli)
        self.assertIn("CREATED_AND_READBACK", supplier.supply(objects(), "create"))
        self.assertEqual(len(supplier.receipts), 5)
        self.assertIn("NOT_TLS_RUNTIME", self.supplier(cli).supply(objects(), "verify"))

    def test_existing_object_prevents_all_create_calls(self):
        cli = FakeCLI()
        cli.saved["backend-redis-runtime"] = {}
        with self.assertRaisesRegex(prep.Rejected, "EXISTING_OBJECT_NO_OVERWRITE"):
            self.supplier(cli).supply(objects(), "create")
        self.assertFalse(any(a[0] == "create" for a in cli.calls))

    def test_wrong_target_and_auth_exec_prevent_all_create_calls(self):
        for field, value in [("server", "https://wrong.test"), ("ns_uid", "wrong"), ("auth", {"exec": {"command": "login"}})]:
            cli = FakeCLI()
            setattr(cli, field, value)
            with self.assertRaises(prep.Rejected):
                self.supplier(cli).supply(objects(), "create")
            self.assertFalse(any(a[0] == "create" for a in cli.calls))

    def test_modified_dry_run_prevents_persisted_writes(self):
        cli = FakeCLI()
        cli.mutate_preview = True
        with self.assertRaisesRegex(prep.Rejected, "SERVER_DRY_RUN_NOT_PRESERVED"):
            self.supplier(cli).supply(objects(), "create")
        self.assertFalse(cli.saved)

    def test_timeout_keeps_receipts_without_retry_delete_or_overwrite(self):
        cli = FakeCLI()
        cli.fail_create = 3
        supplier = self.supplier(cli)
        with self.assertRaisesRegex(prep.Rejected, "OUTCOME_UNCERTAIN_NO_RETRY"):
            supplier.supply(objects(), "create")
        self.assertEqual(supplier.create_attempts, 3)
        self.assertEqual(len(supplier.receipts), 2)
        self.assertFalse(any(a[0] in ("patch", "apply", "delete", "replace") for a in cli.calls))

    def test_verify_rejects_secret_content_change(self):
        cli = FakeCLI()
        self.supplier(cli).supply(objects(), "create")
        cli.saved["backend-redis-runtime"]["data"] = {"wrong": "eA=="}
        with self.assertRaisesRegex(prep.Rejected, "SUPPLIED_OBJECT_MISMATCH"):
            self.supplier(cli).supply(objects(), "verify")

    def test_partial_verify_retains_matched_uids_before_missing_object(self):
        cli = FakeCLI()
        cli.fail_create = 3
        with self.assertRaises(prep.Rejected):
            self.supplier(cli).supply(objects(), "create")
        supplier = self.supplier(cli)
        before = len(cli.saved)
        with self.assertRaisesRegex(prep.Rejected, "SUPPLIED_OBJECT_MISSING"):
            supplier.supply(objects(), "verify")
        self.assertEqual(len(supplier.verified_receipts), 2)
        self.assertEqual(len(cli.saved), before)

    def test_sops_errors_redacted(self):
        def fake(*args, **kwargs):
            return SimpleNamespace(returncode=1, stdout=b"", stderr=b"secret-value-sentinel")
        with self.assertRaisesRegex(prep.Rejected, "^SOPS_DECRYPT_OR_MAC_FAILED$"):
            decrypt_objects(b"cipher", fake)

    def test_sops_plaintext_shape_rejected(self):
        def fake(*args, **kwargs):
            return SimpleNamespace(returncode=0, stdout=b'{"backend_redis_auth_token":"secret-value-sentinel"}', stderr=b"")
        with self.assertRaisesRegex(prep.Rejected, "EXACT_FIVE_FIELDS_REQUIRED"):
            decrypt_objects(b"cipher", fake)

    @unittest.skipUnless(os.name == "posix", "Owned-file contract is verified on Linux CI")
    def test_private_regular_cipher_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cipher"
            path.write_bytes(b"encrypted-only")
            path.chmod(0o600)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(read_cipher(path, digest, os.getuid()), b"encrypted-only")
            link = Path(td) / "link"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                read_cipher(link, digest, os.getuid())
            path.chmod(0o644)
            with self.assertRaisesRegex(prep.Rejected, "MODE_600"):
                read_cipher(path, digest, os.getuid())


if __name__ == "__main__":
    unittest.main()

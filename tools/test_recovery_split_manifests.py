# 작성자: 최유준
# 작성 날짜: 2026/10/16
"""Recovery common composition split: one hash/digest resolution, separate App/Job/NP drafts.

Real Kustomize output only. Passing is Source composition evidence, not Apply, Pull, DB access,
Secret/CA supply or Migration acceptance.
"""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

import split_recovery_render as split
from check_migration_manifest import migration_manifest_blockers

ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZE = os.environ.get("KUSTOMIZE", "kustomize")


def build(path):
    return subprocess.run([KUSTOMIZE, "build", str(ROOT / path)], check=True, capture_output=True, text=True).stdout


class RecoverySplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.composed = build("operations/recovery/compose")
        cls.overlay = build("apps/overlays/recovery")
        cls.app, cls.job, cls.policy = split.split_documents(cls.composed)

    def test_app_half_equals_standalone_overlay_and_shares_hash_and_digest(self):
        key = split.key
        self.assertEqual(sorted(self.app, key=key),
                         sorted([d for d in yaml.safe_load_all(self.overlay) if d], key=key))
        backend = next(d for d in self.app if key(d) == ("Deployment", "backend"))
        container, = backend["spec"]["template"]["spec"]["containers"]
        job_container, = self.job["spec"]["template"]["spec"]["containers"]
        config = next(d["metadata"]["name"] for d in self.app if d["kind"] == "ConfigMap"
                      and d["metadata"]["name"].startswith("backend-config-"))
        self.assertEqual(job_container["envFrom"], [{"configMapRef": {"name": config}}])
        self.assertEqual(job_container["envFrom"], container["envFrom"])
        self.assertEqual(job_container["image"], container["image"])
        self.assertRegex(job_container["image"], r"^harbor\.seokpan\.soldesk\.store/seokpan-hybrid/backend@sha256:[0-9a-f]{64}$")

    def test_job_is_dedicated_suspended_read_only_and_reviewed_by_both_checks(self):
        self.assertEqual(split.recovery_migration_blockers(self.app, self.job, self.policy), [])
        self.assertIs(self.job["spec"]["suspend"], True)
        self.assertEqual(self.job["spec"]["backoffLimit"], 0)
        pod = self.job["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "default")
        self.assertIs(pod["automountServiceAccountToken"], False)
        self.assertEqual(pod["imagePullSecrets"], [{"name": "recovery-harbor-pull"}])
        self.assertEqual(self.job["spec"]["template"]["metadata"]["labels"],
                         {"app.kubernetes.io/name": "seokpan-migration"})
        self.assertEqual(pod["containers"][0]["args"][0], "current")
        self.assertNotIn("--execute", pod["containers"][0]["args"])
        # Only the unresolved-input markers may stop the existing Job check (hold is intentional).
        blockers = migration_manifest_blockers(yaml.safe_dump_all(self.app), yaml.safe_dump(self.job), 300)
        self.assertEqual(blockers, ["Migration review requires resolved App and Job inputs"])

    def test_migration_drift_is_rejected(self):
        def policy_dns_removed(app, job, policy): policy["spec"]["egress"].pop()
        def policy_db_widened(app, job, policy): policy["spec"]["egress"][0]["to"][0]["ipBlock"]["cidr"] = "192.168.54.0/24"
        def policy_valkey_added(app, job, policy): policy["spec"]["egress"].append(
            {"to": [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "recovery-redis"}}}],
             "ports": [{"protocol": "TCP", "port": 6379}]})
        def policy_ingress(app, job, policy): policy["spec"]["ingress"] = [{}]
        def backend_label(app, job, policy): job["spec"]["template"]["metadata"]["labels"] = {"app.kubernetes.io/name": "backend"}
        def active(app, job, policy): job["spec"]["suspend"] = False
        def upgrade(app, job, policy): job["spec"]["template"]["spec"]["containers"][0]["args"][0] = "upgrade-head"
        def token(app, job, policy): job["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
        def other_sa(app, job, policy): job["spec"]["template"]["spec"]["serviceAccountName"] = "backend"
        def no_pull(app, job, policy): job["spec"]["template"]["spec"].pop("imagePullSecrets")
        def role(app, job, policy): app.append({"kind": "Role", "metadata": {"name": "x"}})
        def other_image(app, job, policy): job["spec"]["template"]["spec"]["containers"][0]["image"] = "harbor.seokpan.soldesk.store/seokpan-hybrid/backend@sha256:" + "b" * 64
        for mutate in (policy_dns_removed, policy_db_widened, policy_valkey_added, policy_ingress, backend_label,
                       active, upgrade, token, other_sa, no_pull, role, other_image):
            with self.subTest(mutation=mutate.__name__):
                app, job, policy = map(copy.deepcopy, (self.app, self.job, self.policy))
                mutate(app, job, policy)
                self.assertTrue(split.recovery_migration_blockers(app, job, policy))

    def test_cli_writes_three_new_files_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            out = {n: Path(directory) / f"{n}.yaml" for n in ("app", "job", "policy")}
            command = [sys.executable, str(ROOT / "tools/split_recovery_render.py"), "--kustomize", KUSTOMIZE,
                       "--app-output", str(out["app"]), "--job-output", str(out["job"]),
                       "--policy-output", str(out["policy"])]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            before = out["job"].read_text(encoding="utf-8")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(out["job"].read_text(encoding="utf-8"), before)

    def test_compose_images_match_overlay_and_release_gate_still_withholds_recovery(self):
        compose = yaml.safe_load((ROOT / "operations/recovery/compose/kustomization.yaml").read_text(encoding="utf-8"))
        overlay = yaml.safe_load((ROOT / "apps/overlays/recovery/kustomization.yaml").read_text(encoding="utf-8"))
        wanted = next(i for i in overlay["images"] if i["name"] == "seokpan-backend")
        self.assertEqual(compose["images"], [wanted])
        result = subprocess.run([sys.executable, str(ROOT / "tools/render_release.py"), "recovery", "--output",
                                 str(Path(tempfile.gettempdir()) / "never-written-recovery.yaml"),
                                 "--kustomize", KUSTOMIZE, "--recovery-namespace", "seokpan-recovery",
                                 "--recovery-registry", "harbor.seokpan.soldesk.store"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("INPUT_REQUIRED", result.stderr)
        self.assertFalse((Path(tempfile.gettempdir()) / "never-written-recovery.yaml").exists())


if __name__ == "__main__":
    unittest.main()

"""Mutation checks for immutable releases and separate Migration comparison.

Controlled fixtures isolate Source semantics. Actual Kustomize composition is
covered by the existing App/OCP/Cloud suites; no service or Secret is contacted.
"""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from check_migration_manifest import migration_manifest_blockers
from render_release import app_manifest_blockers, recovery_manifest_blockers

ROOT = Path(__file__).resolve().parents[1]


class ReleaseSafetyBoundaries(unittest.TestCase):
    def fixture(self, mode="legacy", replicas=1):
        resources = []
        for name in ("backend", "frontend"):
            r = yaml.safe_load((ROOT / "apps/base" / (name + ".yaml")).read_text())
            r["metadata"]["namespace"] = "reviewed-lab"
            r["metadata"]["annotations"]["seokpan.io/release-state"] = "source-reviewed-runtime-unverified"
            r["spec"]["replicas"] = replicas
            c = r["spec"]["template"]["spec"]["containers"][0]
            c["image"] = "harbor.fixture.test/" + name + "@sha256:" + "a" * 64
            resources.append(r)
        config = {
            "SEOKPAN_GAME_LIFECYCLE_MODE": mode,
            "SEOKPAN_DATABASE_EXPECTED_HOST": "db.fixture.test",
            "SEOKPAN_DATABASE_EXPECTED_PORT": "3306",
            "SEOKPAN_DATABASE_EXPECTED_NAME": "fixture_db",
            "SEOKPAN_DATABASE_CA_FILE": "/etc/seokpan/database-ca/ca.crt",
        }
        resources.append({"apiVersion": "v1", "kind": "ConfigMap",
            "metadata": {"name": "backend-config-reviewedhash", "namespace": "reviewed-lab"}, "data": config})
        resources[0]["spec"]["template"]["spec"]["containers"][0]["envFrom"] = [
            {"configMapRef": {"name": "backend-config-reviewedhash"}}]
        return resources

    @staticmethod
    def container(resources, name="backend"):
        return next(r for r in resources if r["kind"] == "Deployment"
                    and r["metadata"]["name"] == name)["spec"]["template"]["spec"]["containers"][0]

    def job(self):
        j = yaml.safe_load((ROOT / "operations/ocp-lab/migration/job.yaml").read_text())
        j["metadata"]["name"] = "reviewed-migration-run"
        j["metadata"]["namespace"] = "reviewed-lab"
        j["metadata"]["annotations"]["seokpan.io/release-state"] = "source-reviewed-runtime-unverified"
        c = j["spec"]["template"]["spec"]["containers"][0]
        c["image"] = self.container(self.fixture())["image"]
        c["envFrom"] = [{"configMapRef": {"name": "backend-config-reviewedhash"}}]
        c["args"] = ["current", "--expect-host", "db.fixture.test", "--expect-port", "3306",
                     "--expect-database", "fixture_db"]
        return j

    def migration_blockers(self, app, job, deadline=300):
        return migration_manifest_blockers(yaml.safe_dump_all(app), yaml.safe_dump(job), deadline)

    def test_lab_release_requires_immutable_backend_frontend_and_init_images(self):
        app = self.fixture()
        self.assertEqual(app_manifest_blockers(yaml.safe_dump_all(app), "lab"), [])
        for image in ("harbor.fixture.test/backend:latest", "harbor.fixture.test/backend:reviewed-tag",
                      "harbor.fixture.test/backend@sha256:" + "a" * 63, None):
            with self.subTest(image=image):
                rs = self.fixture()
                self.container(rs)["image"] = image
                self.assertTrue(app_manifest_blockers(yaml.safe_dump_all(rs), "lab"))
        app[0]["spec"]["template"]["spec"]["initContainers"] = [{"name": "init", "image": "busybox:latest"}]
        self.assertTrue(app_manifest_blockers(yaml.safe_dump_all(app), "lab"))
        app[0]["spec"]["template"]["spec"]["initContainers"][0]["image"] = "harbor.fixture.test/init@sha256:" + "b" * 64
        self.assertEqual(app_manifest_blockers(yaml.safe_dump_all(app), "lab"), [])
        self.assertTrue(app_manifest_blockers(yaml.safe_dump_all([app[-1]]), "lab"))

    def test_lab_cli_withholds_mutable_tag_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            app = self.fixture()
            self.container(app)["image"] = "harbor.fixture.test/backend:mutable"
            rendered = yaml.safe_dump_all(app)
            tool = directory / "kustomize-fixture"
            tool.write_text("#!" + sys.executable + "\nimport sys\nprint('v5.7.1' if sys.argv[1]=='version' else "
                + repr(rendered) + ")\n")
            tool.chmod(0o755)
            output = directory / "new.yaml"
            p = subprocess.run([sys.executable, str(ROOT / "tools/render_release.py"), "lab",
                "--output", str(output), "--kustomize", str(tool)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertIn("digest references", p.stderr)
            self.assertFalse(output.exists())

    def test_cloud_multi_replica_requires_explicit_captured_source_not_a_runtime_claim(self):
        for mode in ("legacy", "INPUT_REQUIRED", "unknown"):
            with self.subTest(mode=mode):
                self.assertTrue(app_manifest_blockers(yaml.safe_dump_all(self.fixture(mode, 3)), "cloud"))
        app = self.fixture("captured", 3)
        self.assertEqual(app_manifest_blockers(yaml.safe_dump_all(app), "cloud"), [])
        self.container(app)["env"].append({"name": "SEOKPAN_GAME_LIFECYCLE_MODE", "value": "legacy"})
        self.assertTrue(app_manifest_blockers(yaml.safe_dump_all(app), "cloud"))

    def test_recovery_redis_probes_are_listener_only_and_hold_is_preserved(self):
        redis = list(yaml.safe_load_all((ROOT / "apps/overlays/recovery/redis.yaml").read_text()))[0]
        self.assertEqual(redis["spec"]["replicas"], 0)
        c = redis["spec"]["template"]["spec"]["containers"][0]
        for name in ("startupProbe", "readinessProbe"):
            self.assertEqual(c[name]["tcpSocket"], {"port": "redis-tls"})
            self.assertFalse({"exec", "httpGet", "grpc"} & set(c[name]))
        self.assertNotIn("livenessProbe", c)
        self.assertIn("INPUT_REQUIRED", c["image"])
        # Reuse the existing independent Recovery fixture, without importing its
        # TestCase into this module's discovered suite or pretending to Build it.
        import test_app_manifests
        fixture_case = test_app_manifests.RecoveryReleaseBoundaries()
        recovery = fixture_case.fixture()
        self.assertEqual(recovery_manifest_blockers(yaml.safe_dump_all(recovery),
            fixture_case.namespace, fixture_case.registry), [])
        for probe_name in ("startupProbe", "readinessProbe"):
            rs = copy.deepcopy(recovery)
            redis = next(r for r in rs if r["kind"] == "StatefulSet")
            redis["spec"]["template"]["spec"]["containers"][0].pop(probe_name)
            self.assertIn("Recovery Redis requires reviewed TLS-listener startup/readiness probes",
                recovery_manifest_blockers(yaml.safe_dump_all(rs), fixture_case.namespace, fixture_case.registry))

    def test_migration_same_digest_deadline_target_and_ca_compare(self):
        self.assertEqual(self.migration_blockers(self.fixture(), self.job()), [])
        mutations = [
            ("different digest", lambda j: j["spec"]["template"]["spec"]["containers"][0].update(image="harbor.fixture.test/backend@sha256:" + "b" * 64)),
            ("mutable image", lambda j: j["spec"]["template"]["spec"]["containers"][0].update(image="harbor.fixture.test/backend:latest")),
            ("missing deadline", lambda j: j["spec"].pop("activeDeadlineSeconds")),
            ("deadline mismatch", lambda j: j["spec"].update(activeDeadlineSeconds=301)),
            ("wrong namespace", lambda j: j["metadata"].update(namespace="unreviewed")),
            ("wrong config hash", lambda j: j["spec"]["template"]["spec"]["containers"][0]["envFrom"][0]["configMapRef"].update(name="wrong-config")),
            ("wrong target", lambda j: j["spec"]["template"]["spec"]["containers"][0]["args"].__setitem__(2, "wrong-db.test")),
            ("missing CA", lambda j: j["spec"]["template"]["spec"].update(volumes=[])),
            ("runtime credential", lambda j: j["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "SEOKPAN_GAME_DATABASE_URL", "value": "not-allowed"})),
            ("automatic retry", lambda j: j["spec"].update(backoffLimit=1)),
        ]
        for name, mutate in mutations:
            with self.subTest(boundary=name):
                job = self.job()
                mutate(job)
                self.assertTrue(self.migration_blockers(self.fixture(), job))
        for deadline in (None, True, 0, -1):
            self.assertTrue(self.migration_blockers(self.fixture(), self.job(), deadline))
        app, j = self.fixture(), self.job()
        for r in app:
            r["metadata"].pop("namespace")
        j["metadata"].pop("namespace")
        self.assertTrue(self.migration_blockers(app, j))
        app = self.fixture()
        app.append(copy.deepcopy(app[-1]))
        self.assertTrue(self.migration_blockers(app, self.job()))

    def test_writing_migration_needs_explicit_action_approval_and_reviewed_budget(self):
        j = self.job()
        c = j["spec"]["template"]["spec"]["containers"][0]
        c["args"][0] = "upgrade-head"
        self.assertTrue(self.migration_blockers(self.fixture(), j))
        c["args"].append("--execute")
        self.assertTrue(self.migration_blockers(self.fixture(), j))
        c["args"].extend(["--approval-ref", "C-reviewed-run-ref"])
        j["spec"]["activeDeadlineSeconds"] = 900
        self.assertTrue(self.migration_blockers(self.fixture(), j))
        self.assertEqual(self.migration_blockers(self.fixture(), j, 900), [])
        self.assertTrue(j["spec"]["suspend"])
        # Success only compares declarations. It neither resumes this Job nor
        # verifies the supplied review reference or actual database privileges.


if __name__ == "__main__":
    unittest.main()

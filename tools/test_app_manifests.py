"""Exercise actual Kustomize and safety boundaries of the input-required source.

Requires kustomize v5.7.1 and PyYAML. No cluster or external service is contacted.
These tests are not an SCC, admission, image, connection or Recovery Run result.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZE = os.environ.get("KUSTOMIZE", shutil.which("kustomize") or "kustomize")


class AppManifestBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renders = {}
        for name, path in (("base", "apps/base"), ("lab", "apps/overlays/lab"),
                           ("recovery", "apps/overlays/recovery")):
            rendered = subprocess.run(
                [KUSTOMIZE, "build", str(ROOT / path)],
                check=True, capture_output=True, text=True,
            ).stdout
            cls.renders[name] = list(yaml.safe_load_all(rendered))

    def by_kind(self, env, kind):
        return [r for r in self.renders[env] if r["kind"] == kind]

    def test_builds_have_unique_objects_and_no_owned_secrets_or_namespace(self):
        forbidden = {"Secret", "Namespace", "Job", "CronJob", "Application",
                     "AppProject", "StatefulSet", "PersistentVolumeClaim"}
        for env, resources in self.renders.items():
            with self.subTest(env=env):
                keys = [(r["apiVersion"], r["kind"], r["metadata"].get("namespace"),
                         r["metadata"]["name"]) for r in resources]
                self.assertEqual(len(keys), len(set(keys)))
                self.assertFalse(forbidden & {r["kind"] for r in resources})

    def test_no_candidate_can_start_pods_with_missing_release_inputs(self):
        for env in self.renders:
            for dep in self.by_kind(env, "Deployment"):
                with self.subTest(env=env, app=dep["metadata"]["name"]):
                    self.assertEqual(dep["spec"]["replicas"], 0)
                    container = dep["spec"]["template"]["spec"]["containers"][0]
                    self.assertIn("INPUT_REQUIRED", container["image"])
                    self.assertIn("input-required", dep["metadata"]["annotations"][
                        "seokpan.io/release-state"])

    def test_fixed_uid_gid_and_lab_dns_bypass_are_absent(self):
        for env in self.renders:
            for dep in self.by_kind(env, "Deployment"):
                pod = dep["spec"]["template"]["spec"]
                self.assertNotIn("hostAliases", pod)
                self.assertFalse(pod["automountServiceAccountToken"])
                self.assertFalse(pod["enableServiceLinks"])
                self.assertEqual(pod["securityContext"]["seccompProfile"]["type"],
                                 "RuntimeDefault")
                for context in [pod["securityContext"],
                                *(c["securityContext"] for c in pod["containers"])]:
                    self.assertFalse({"runAsUser", "runAsGroup", "fsGroup"} & context.keys())
                for c in pod["containers"]:
                    self.assertTrue(c["securityContext"]["runAsNonRoot"])
                    self.assertFalse(c["securityContext"]["allowPrivilegeEscalation"])
                    self.assertTrue(c["securityContext"]["readOnlyRootFilesystem"])
                    self.assertEqual(c["securityContext"]["capabilities"]["drop"], ["ALL"])

    def test_backend_auth_separate_from_nonsecret_connection_metadata(self):
        for env in ("lab", "recovery"):
            data = self.by_kind(env, "ConfigMap")[0]["data"]
            self.assertEqual(data["SEOKPAN_CONNECTION_PROFILE"], env)
            url = urlsplit(data["SEOKPAN_REDIS_URL"])
            self.assertEqual(url.scheme, "rediss")
            self.assertIsNone(url.username)
            self.assertIsNone(url.password)
            self.assertEqual(url.query, "")
            self.assertEqual(url.hostname, data["SEOKPAN_REDIS_EXPECTED_HOST"])
            self.assertEqual(str(url.port), data["SEOKPAN_REDIS_EXPECTED_PORT"])
            self.assertEqual(url.path, "/" + data["SEOKPAN_REDIS_EXPECTED_DATABASE"])
            self.assertNotIn("SEOKPAN_REDIS_AUTH_TOKEN", data)
            backend = next(d for d in self.by_kind(env, "Deployment")
                           if d["metadata"]["name"] == "backend")
            values = {e["name"]: e for e in backend["spec"]["template"]["spec"][
                "containers"][0]["env"]}
            for name in ("SEOKPAN_IDENTITY_DATABASE_URL", "SEOKPAN_GAME_DATABASE_URL",
                         "SEOKPAN_REDIS_AUTH_TOKEN"):
                self.assertNotIn("value", values[name])
                self.assertIn("secretKeyRef", values[name]["valueFrom"])

    def test_ca_inputs_are_required_external_refs(self):
        for env in self.renders:
            backend = next(d for d in self.by_kind(env, "Deployment")
                           if d["metadata"]["name"] == "backend")
            pod = backend["spec"]["template"]["spec"]
            mounts = {m["name"]: m for m in pod["containers"][0]["volumeMounts"]}
            for volume in pod["volumes"]:
                if volume["name"] in ("database-ca", "redis-ca"):
                    self.assertIn("configMap", volume)
                    self.assertFalse(volume["configMap"].get("optional", False))
                    self.assertTrue(mounts[volume["name"]]["readOnly"])
                    self.assertNotIn("subPath", mounts[volume["name"]])

    def test_registry_pull_secret_is_only_recovery_environment_specific(self):
        for env in ("base", "lab"):
            for dep in self.by_kind(env, "Deployment"):
                self.assertNotIn("imagePullSecrets", dep["spec"]["template"]["spec"])
        for dep in self.by_kind("recovery", "Deployment"):
            self.assertEqual(dep["spec"]["template"]["spec"]["imagePullSecrets"],
                             [{"name": "recovery-harbor-pull"}])

    def test_probe_and_service_ports_match_app_contract_without_public_probes(self):
        for env in self.renders:
            for dep in self.by_kind(env, "Deployment"):
                name = dep["metadata"]["name"]
                c = dep["spec"]["template"]["spec"]["containers"][0]
                self.assertEqual(c["ports"][0]["containerPort"],
                                 8000 if name == "backend" else 8080)
                expected = ("/health/startup", "/health/live", "/health/ready") \
                    if name == "backend" else ("/health/live",) * 3
                self.assertEqual(tuple(c[key]["httpGet"]["path"] for key in
                                       ("startupProbe", "livenessProbe", "readinessProbe")),
                                 expected)
            for route in self.by_kind(env, "Route"):
                self.assertNotIn("health", route["spec"].get("path", ""))

    def test_lab_same_host_api_ws_and_recovery_no_assumed_entry_path(self):
        config = self.by_kind("lab", "ConfigMap")[0]["data"]
        origin, = json.loads(config["SEOKPAN_ALLOWED_ORIGINS"])
        host = urlsplit(origin).hostname
        routes = self.by_kind("lab", "Route")
        self.assertEqual(len(routes), 3)
        self.assertEqual({r["spec"]["host"] for r in routes}, {host})
        self.assertEqual({r["spec"].get("path", "/") for r in routes},
                         {"/", "/api/v1", "/ws/v1"})
        self.assertEqual(self.by_kind("recovery", "Route"), [])
        self.assertEqual(self.by_kind("recovery", "Ingress"), [])
        recovery = self.by_kind("recovery", "ConfigMap")[0]["data"]
        self.assertIn("recovery-direct-db", recovery["SEOKPAN_DATABASE_EXPECTED_HOST"])
        self.assertIn("new-recovery-redis", recovery["SEOKPAN_REDIS_EXPECTED_HOST"])

    def test_release_gate_withholds_draft_and_does_not_overwrite_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "recovery.yaml"
            for env in ("lab", "recovery"):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "tools/render_release.py"), env,
                     "--output", str(output), "--kustomize", KUSTOMIZE],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("release withheld", result.stderr)
                self.assertFalse(output.exists())
            output.write_text("previous reviewed artifact", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/render_release.py"), "recovery",
                 "--output", str(output), "--kustomize", KUSTOMIZE],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(), "previous reviewed artifact")

    def test_successful_input_gate_creates_only_new_artifacts_and_preserves_symlinks(self):
        # A controlled tool response isolates output preservation after a
        # successful input gate. Actual overlay rendering is covered above.
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            fixture = directory / "kustomize-fixture"
            manifest = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: fixture\n"
            fixture.write_text(
                "#!" + sys.executable + "\nimport sys\n"
                "print('v5.7.1' if sys.argv[1] == 'version' else " + repr(manifest) + ", end='' if sys.argv[1] != 'version' else '\\n')\n",
                encoding="utf-8",
            )
            fixture.chmod(0o755)

            def render(output):
                return subprocess.run(
                    [sys.executable, str(ROOT / "tools/render_release.py"), "lab",
                     "--output", str(output), "--kustomize", str(fixture)],
                    capture_output=True, text=True,
                )

            output = directory / "new.yaml"
            self.assertEqual(render(output).returncode, 0)
            self.assertEqual(output.read_text(), manifest)
            output.write_text("preserved reviewed artifact", encoding="utf-8")
            result = render(output)
            self.assertEqual(result.returncode, 2)
            self.assertIn("output already exists", result.stderr)
            self.assertEqual(output.read_text(), "preserved reviewed artifact")

            symlink = directory / "existing-symlink.yaml"
            symlink.symlink_to(output)
            self.assertEqual(render(symlink).returncode, 2)
            self.assertTrue(symlink.is_symlink())
            self.assertEqual(output.read_text(), "preserved reviewed artifact")

            dangling = directory / "dangling-symlink.yaml"
            missing = directory / "missing.yaml"
            dangling.symlink_to(missing)
            self.assertEqual(render(dangling).returncode, 2)
            self.assertTrue(dangling.is_symlink())
            self.assertFalse(missing.exists())
            self.assertEqual({p.name for p in directory.iterdir()},
                             {"kustomize-fixture", "new.yaml", "existing-symlink.yaml",
                              "dangling-symlink.yaml"})


if __name__ == "__main__":
    unittest.main()

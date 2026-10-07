"""Exercise the stage-1 lab Valkey preflight gate and the new activation boundary.

# 작성자: 최유준 작성 날짜: 2026/10/07
Requires kustomize v5.7.1 and PyYAML. No cluster or external service is contacted.
These tests are not a Pod start, SCC, TLS/AUTH or hostname result.
"""

import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

from preflight_lab_valkey import lab_valkey_blockers, selected_resources


ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZE = os.environ.get("KUSTOMIZE", shutil.which("kustomize") or "kustomize")


def build(path):
    return subprocess.run([KUSTOMIZE, "build", str(ROOT / path)],
                          check=True, capture_output=True, text=True).stdout


class LabValkeyPreflight(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = build("apps/overlays/lab")
        cls.resources = list(yaml.safe_load_all(cls.rendered))

    def mutated(self, change):
        resources = copy.deepcopy(self.resources)
        change(resources)
        return yaml.safe_dump_all(resources)

    @staticmethod
    def sts(rs):
        return next(r for r in rs if r["kind"] == "StatefulSet")

    def pod(self, rs):
        return self.sts(rs)["spec"]["template"]["spec"]

    def ctr(self, rs):
        return self.pod(rs)["containers"][0]

    def volume(self, rs, name):
        return next(v for v in self.pod(rs)["volumes"] if v["name"] == name)

    @staticmethod
    def configmap(rs, prefix):
        return next(r for r in rs if r["kind"] == "ConfigMap"
                    and r["metadata"]["name"].startswith(prefix))

    @staticmethod
    def service(rs):
        return next(r for r in rs if r["kind"] == "Service"
                    and r["metadata"]["name"] == "lab-redis")

    def test_real_lab_render_passes_and_selects_only_the_valkey_bundle(self):
        self.assertEqual(lab_valkey_blockers(self.rendered), [])
        selected = selected_resources(self.rendered)
        self.assertEqual(len(selected), 4)
        self.assertIn("StatefulSet/lab-redis", selected)
        self.assertIn("Service/lab-redis", selected)
        self.assertEqual(sorted(s.split("/")[0] for s in selected),
                         ["ConfigMap", "ConfigMap", "Service", "StatefulSet"])
        self.assertTrue(any(s.startswith("ConfigMap/lab-redis-config-") for s in selected))
        self.assertTrue(any(s.startswith("ConfigMap/lab-redis-runtime-") for s in selected))
        self.assertFalse(any("Secret" in s or "Deployment" in s or "Route" in s
                             for s in selected))

    def test_transport_directive_overrides_duplicates_and_public_auth_are_rejected(self):
        def replace_config(change):
            def mutate(rs):
                config = self.configmap(rs, "lab-redis-config-")["data"]
                config["redis.conf"] = change(config["redis.conf"])
            return mutate

        cases = {
            "uppercase plaintext port": lambda text: text + "\nPORT 6380\n",
            "later TLS off": lambda text: text + "\ntls-port 0\n",
            "mixed-case TLS off": lambda text: text + "\nTlS-PoRt 0\n",
            "duplicate same TLS port": lambda text: text + "\ntls-port 6379\n",
            "later client certificate mode": lambda text: text + "\ntls-auth-clients yes\n",
            "public authentication": lambda text: text + "\nrequirepass SYNTHETIC_NOT_A_REAL_PASSWORD\n",
            "additional include": lambda text: text + "\ninclude /unreviewed/config.conf\n",
            "include after transport": lambda text: text.replace(
                "include /etc/seokpan/redis-runtime/redis-runtime.conf", "")
                + "\ninclude /etc/seokpan/redis-runtime/redis-runtime.conf\n",
            "different certificate": lambda text: text.replace(
                "tls-cert-file /etc/seokpan/redis-server-tls/tls.crt", "tls-cert-file /other/tls.crt"),
            "missing protected mode": lambda text: text.replace("protected-mode yes", ""),
            "invalid quoted directive": lambda text: text + '\ntls-protocols "unclosed\n',

            "inline hash text": lambda text: text.replace("port 0", "port 0 # inline text"),
            "inline hash after include": lambda text: text.replace(
                "include /etc/seokpan/redis-runtime/redis-runtime.conf",
                "include /etc/seokpan/redis-runtime/redis-runtime.conf # inline text"),
            "shell quote concatenation": lambda text: text.replace("protected-mode yes", 'protected-mode "ye"s'),
            "unquoted backslash escape": lambda text: text.replace("protected-mode yes", "protected-mode y\\es"),
        }
        for name, change in cases.items():
            with self.subTest(boundary=name):
                self.assertTrue(lab_valkey_blockers(self.mutated(replace_config(change))))

    def test_transport_directive_case_full_line_comments_and_spacing_preserve_reviewed_values(self):
        def mutate(rs):
            config = self.configmap(rs, "lab-redis-config-")["data"]
            lines = []
            for line in config["redis.conf"].splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    name, arguments = line.split(None, 1)
                    line = "  " + name.upper() + "  " + arguments + "  "
                lines.append(line)
            config["redis.conf"] = "# transport settings\n" + "\n".join(lines) + "\n"
        self.assertEqual(lab_valkey_blockers(self.mutated(mutate)), [])

    def test_gate_does_not_depend_on_fe_be_db_or_route_inputs(self):
        only_valkey = self.mutated(lambda rs: rs.__setitem__(
            slice(None), [r for r in rs if r["kind"] in ("StatefulSet", "Service", "ConfigMap")
                          and r["metadata"]["name"].startswith("lab-redis")]))
        self.assertEqual(lab_valkey_blockers(only_valkey), [])

    def test_gate_rejects_each_boundary_it_is_meant_to_hold(self):
        def digest_tag(rs):
            self.ctr(rs)["image"] = "image-registry.openshift-image-registry.svc:5000/" \
                                    "seokpan-argotest/valkey:7.2.14"

        def plaintext_port(rs):
            cm = self.configmap(rs, "lab-redis-config-")
            cm["data"]["redis.conf"] = cm["data"]["redis.conf"].replace("port 0", "port 6379")

        cases = {
            "image must be the exact reviewed": digest_tag,
            "exactly one reviewed replica": lambda rs: self.sts(rs)["spec"].update(replicas=0),
            "release-state must be": lambda rs: self.sts(rs)["metadata"]["annotations"].update(
                {"seokpan.io/release-state": "input-required-no-runtime-validation"}),
            "TLS-only 6379 with the reviewed includes": plaintext_port,
            "AUTH env must come only": lambda rs: self.ctr(rs)["env"][0].update(value="x"),
            "TLS Secret reference": lambda rs: self.volume(rs, "server-tls")["secret"].update(
                secretName="other-secret"),
            "AUTH Secret must expose only": lambda rs: self.volume(rs, "server-auth")["secret"]
            ["items"].append({"key": "token", "path": "token"}),
            "must not fix IDs": lambda rs: self.pod(rs).setdefault("securityContext", {}).update(
                fsGroup=1000),
            "restricted and arbitrary-UID": lambda rs: self.ctr(rs)["securityContext"].update(
                runAsUser=1000),
            "must not use persistent storage": lambda rs: self.pod(rs)["volumes"].append(
                {"name": "x", "persistentVolumeClaim": {"claimName": "pvc"}}),
            "must not fix IDs, share host": lambda rs: self.ctr(rs)["ports"][0].update(
                hostPort=6379),
            "internal headless TLS Service": lambda rs: self.service(rs)["spec"].update(
                type="NodePort"),
            "readiness must prove TLS and AUTH": lambda rs: self.ctr(rs)["readinessProbe"][
                "exec"].update(command=["sh", "-c", "valkey-cli ping"]),
            "must not pass a password": lambda rs: self.ctr(rs)["readinessProbe"]["exec"][
                "command"].__setitem__(2, self.ctr(rs)["readinessProbe"]["exec"]["command"][2]
                                       + " -a secret"),
            "must not use a liveness probe": lambda rs: self.ctr(rs).update(
                livenessProbe={"tcpSocket": {"port": "redis-tls"}}),
            "reviewed candidate values": lambda rs: self.ctr(rs)["resources"]["limits"].update(
                memory="512Mi"),
            "must not own Secret objects": lambda rs: rs.append(
                {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "lab-redis-server-tls"}}),
            "rendered generated names": lambda rs: self.volume(rs, "redis-config")[
                "configMap"].update(name="lab-redis-config-other"),
            "unpersisted noeviction": lambda rs: self.configmap(rs, "lab-redis-runtime-")[
                "data"].update({"redis-runtime.conf": "appendonly yes\n"}),
        }
        for expected, change in cases.items():
            with self.subTest(expected=expected):
                blockers = lab_valkey_blockers(self.mutated(change))
                self.assertTrue(any(expected in b for b in blockers), blockers)

    def test_cli_selects_the_bundle_without_the_full_release_gate(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/preflight_lab_valkey.py"), "--kustomize", KUSTOMIZE],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.split()), 4)
        broken = subprocess.run(
            [sys.executable, str(ROOT / "tools/preflight_lab_valkey.py"),
             "--kustomize", "/nonexistent/kustomize"], capture_output=True, text=True)
        self.assertEqual(broken.returncode, 2)

    def test_full_lab_release_gate_passes_after_stage2_and_recovery_still_withholds(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/render_release.py"), "lab",
                 "--output", str(Path(tmp) / "lab.yaml"), "--kustomize", KUSTOMIZE],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(tmp) / "lab.yaml").exists())
            held = subprocess.run(
                [sys.executable, str(ROOT / "tools/render_release.py"), "recovery",
                 "--output", str(Path(tmp) / "recovery.yaml"), "--kustomize", KUSTOMIZE],
                capture_output=True, text=True)
            self.assertEqual(held.returncode, 2)
            self.assertFalse((Path(tmp) / "recovery.yaml").exists())


class Stage1ActivationBoundary(unittest.TestCase):
    """Only lab workloads (Valkey, FE, BE) may run; base and recovery keep their hold."""

    def workloads(self, path):
        return [r for r in yaml.safe_load_all(build(path))
                if r["kind"] in ("Deployment", "StatefulSet")]

    def test_only_lab_valkey_is_active_and_other_holds_stay(self):
        for path in ("apps/base", "apps/overlays/lab", "apps/overlays/recovery"):
            for workload in self.workloads(path):
                name = workload["metadata"]["name"]
                state = workload["metadata"]["annotations"]["seokpan.io/release-state"]
                with self.subTest(path=path, workload=name):
                    if path == "apps/overlays/lab":
                        self.assertEqual(workload["spec"]["replicas"], 1)
                        self.assertEqual(state, "source-reviewed-runtime-unverified")
                    else:
                        self.assertEqual(workload["spec"]["replicas"], 0)
                        self.assertIn("input-required", state)

    def test_lab_valkey_activation_stays_in_the_lab_overlay(self):
        base_names = {r["metadata"]["name"] for r in self.workloads("apps/base")}
        self.assertEqual(base_names, {"backend", "frontend"})
        recovery = {r["metadata"]["name"]: r["spec"]["replicas"]
                    for r in self.workloads("apps/overlays/recovery")}
        self.assertEqual(recovery, {"backend": 0, "frontend": 0, "recovery-redis": 0})


if __name__ == "__main__":
    unittest.main()

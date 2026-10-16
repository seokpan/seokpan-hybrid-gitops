# 작성자: 최유준 / 작성 날짜: 2026-10-15
"""platform/rosa-monitoring 선언 경계 검사. 클러스터 호출·Apply 없음."""
import os
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "platform" / "rosa-monitoring"
KUSTOMIZE = os.environ.get("KUSTOMIZE", "kustomize")
NAMESPACE = "seokpan-cloud"
UWM_NAMESPACE = "openshift-user-workload-monitoring"
ALLOWED_KINDS = {
    ("monitoring.coreos.com", "ServiceMonitor"),
    ("monitoring.coreos.com", "PrometheusRule"),
    ("networking.k8s.io", "NetworkPolicy"),
}


def api_group(doc):
    version = doc["apiVersion"]
    return version.split("/")[0] if "/" in version else ""


def load(relative):
    return yaml.safe_load((BASE / relative).read_text(encoding="utf-8"))


class AppBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [KUSTOMIZE, "build", str(BASE / "app")],
            check=True, capture_output=True, text=True,
        )
        cls.docs = [d for d in yaml.safe_load_all(result.stdout) if d]

    def test_only_allowed_kinds(self):
        kinds = {(api_group(d), d["kind"]) for d in self.docs}
        self.assertTrue(kinds)
        self.assertLessEqual(kinds, ALLOWED_KINDS)

    def test_namespace_is_not_overridden(self):
        for doc in self.docs:
            self.assertEqual(doc["metadata"].get("namespace", NAMESPACE), NAMESPACE)

    def test_smoke_rule_is_not_in_app_path(self):
        names = {d["metadata"]["name"] for d in self.docs}
        self.assertNotIn("seokpan-monitoring-smoke", names)

    def test_service_monitor_targets_backend_metrics(self):
        monitors = [d for d in self.docs if d["kind"] == "ServiceMonitor"]
        self.assertEqual(len(monitors), 1)
        spec = monitors[0]["spec"]
        self.assertEqual(spec["selector"]["matchLabels"], {"app.kubernetes.io/name": "backend"})
        self.assertEqual([(e["port"], e["path"]) for e in spec["endpoints"]], [("http", "/metrics")])

    def test_network_policy_adds_only_uwm_ingress(self):
        policies = [d for d in self.docs if d["kind"] == "NetworkPolicy"]
        self.assertEqual(len(policies), 1)
        spec = policies[0]["spec"]
        self.assertEqual(spec["policyTypes"], ["Ingress"])
        self.assertNotIn("egress", spec)
        self.assertEqual(spec["podSelector"], {"matchLabels": {"app.kubernetes.io/name": "backend"}})
        self.assertEqual(len(spec["ingress"]), 1)
        rule = spec["ingress"][0]
        self.assertEqual(rule["ports"], [{"protocol": "TCP", "port": 8000}])
        for peer in rule["from"]:
            # Namespace와 Pod selector는 같은 peer의 AND 조건이어야 한다
            self.assertEqual(
                peer["namespaceSelector"]["matchLabels"],
                {"kubernetes.io/metadata.name": UWM_NAMESPACE},
            )
            self.assertEqual(
                peer["podSelector"]["matchLabels"],
                {
                    "app.kubernetes.io/name": "prometheus",
                    "app.kubernetes.io/instance": "user-workload",
                },
            )


class ProjectTest(unittest.TestCase):
    def test_appproject_boundary(self):
        project = load("project/appproject.yaml")
        spec = project["spec"]
        self.assertEqual(project["metadata"]["name"], "seokpan-cloud-monitoring")
        self.assertEqual([d["namespace"] for d in spec["destinations"]], [NAMESPACE])
        self.assertEqual(spec["clusterResourceWhitelist"], [])
        allowed = {(i["group"], i["kind"]) for i in spec["namespaceResourceWhitelist"]}
        self.assertEqual(allowed, ALLOWED_KINDS)

    def test_application_is_manual_sync(self):
        app = load("project/application.yaml")
        spec = app["spec"]
        self.assertEqual(spec["project"], "seokpan-cloud-monitoring")
        self.assertEqual(spec["source"]["path"], "platform/rosa-monitoring/app")
        self.assertEqual(spec["destination"]["namespace"], NAMESPACE)
        sync = spec.get("syncPolicy", {})
        self.assertNotIn("automated", sync)
        self.assertIn("Prune=false", sync["syncOptions"])
        self.assertNotIn("finalizers", app["metadata"])


if __name__ == "__main__":
    unittest.main()

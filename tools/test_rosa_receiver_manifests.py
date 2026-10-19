# 작성자: 최유준 / 작성 날짜: 2026-10-19
"""platform/rosa-monitoring/receiver 시험용 선언 경계 검사. 클러스터 호출·Apply 없음."""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECEIVER = ROOT / "platform" / "rosa-monitoring" / "receiver"
APP = ROOT / "platform" / "rosa-monitoring" / "app"
NAMESPACE = "seokpan-cloud"
SMTP_FROM = "alertmanager@alerts-seokpan.soldesk.store"
CONFIG_FILE = "alertmanagerconfig-seokpan-cloud.yaml"
RULE_FILE = "prometheusrule-receiver-test.yaml"


def load(name):
    return yaml.safe_load((RECEIVER / name).read_text(encoding="utf-8"))


class ReceiverBoundaryTest(unittest.TestCase):
    def test_receiver_files_are_outside_the_argo_app_path(self):
        names = {p.name for p in APP.iterdir()}
        self.assertNotIn(CONFIG_FILE, names)
        self.assertNotIn(RULE_FILE, names)
        kustomization = yaml.safe_load((APP / "kustomization.yaml").read_text(encoding="utf-8"))
        for resource in kustomization["resources"]:
            self.assertNotIn("receiver", resource)

    def test_alertmanager_config_has_no_plaintext_secret(self):
        doc = load(CONFIG_FILE)
        self.assertEqual(doc["kind"], "AlertmanagerConfig")
        self.assertEqual(doc["metadata"]["namespace"], NAMESPACE)
        email = doc["spec"]["receivers"][0]["emailConfigs"][0]
        self.assertEqual(email["from"], SMTP_FROM)
        self.assertEqual(email["smarthost"], "smtp.resend.com:587")
        self.assertTrue(email["requireTLS"])
        self.assertEqual(
            email["authPassword"],
            {"name": "alertmanager-smtp-credential", "key": "smtp-password"},
        )
        text = (RECEIVER / CONFIG_FILE).read_text(encoding="utf-8")
        self.assertNotRegex(text, r"re_[A-Za-z0-9]{8,}")  # Resend API Key 형식

    def test_receiver_test_rule_is_single_temporary_rule(self):
        doc = load(RULE_FILE)
        self.assertEqual(doc["kind"], "PrometheusRule")
        self.assertEqual(doc["metadata"]["namespace"], NAMESPACE)
        self.assertEqual(doc["metadata"]["name"], "seokpan-receiver-test")
        rules = [r for g in doc["spec"]["groups"] for r in g["rules"]]
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule["alert"], "SeokpanReceiverTest")
        self.assertEqual(rule["expr"], "vector(1)")
        self.assertEqual(rule["labels"]["purpose"], "receiver-test")
        self.assertEqual(rule["labels"]["severity"], "info")


if __name__ == "__main__":
    unittest.main()

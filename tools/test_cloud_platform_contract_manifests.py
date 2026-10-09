import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from cloud_platform_contract import Invalid, candidates, read_contract
ROOT = Path(__file__).resolve().parents[1]
class CloudPlatformContractTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads((ROOT / "platform/cloud/contract.fixture.json").read_text())
    def test_manual_project_and_resource_boundary(self):
        docs = candidates(self.c)
        project = next(d for d in docs if d["kind"] == "AppProject")
        app = next(d for d in docs if d["kind"] == "Application")
        self.assertEqual(project["spec"]["destinations"], [{"server":"https://kubernetes.default.svc", "namespace":"fixture-cloud"}])
        kinds = {k["kind"] for k in project["spec"]["namespaceResourceWhitelist"]}
        self.assertFalse(kinds & {"Secret", "Namespace", "Role", "RoleBinding", "NetworkPolicy", "StatefulSet"})
        self.assertEqual(project["spec"]["clusterResourceBlacklist"], [{"group":"*", "kind":"*"}])
        self.assertNotIn("automated", app["spec"]["syncPolicy"])
        self.assertNotIn("finalizers", app["metadata"])
        self.assertNotIn("CreateNamespace=true", app["spec"]["syncPolicy"]["syncOptions"])
        self.assertEqual(app["spec"]["source"]["targetRevision"], self.c["gitops_revision"])
    def test_read_only_role_excludes_secret_and_execution(self):
        for logs in (False, True):
            self.c["include_pod_logs"] = logs
            role = next(d for d in candidates(self.c) if d["kind"] == "Role")
            resources = {r for rule in role["rules"] for r in rule["resources"]}
            verbs = {v for rule in role["rules"] for v in rule["verbs"]}
            self.assertFalse(resources & {"*", "secrets", "pods/exec", "pods/portforward", "roles", "rolebindings"})
            self.assertLessEqual(verbs, {"get", "list", "watch"})
            self.assertEqual("pods/log" in resources, logs)
            self.assertNotIn("RoleBinding", [d["kind"] for d in candidates(self.c)])
    def test_router_selector_is_same_peer_and_not_or(self):
        policy = next(d for d in candidates(self.c) if d["metadata"]["name"] == "seokpan-router-to-frontend")
        peers = policy["spec"]["ingress"][0]["from"]
        self.assertEqual(len(peers), 1)
        self.assertEqual(set(peers[0]), {"namespaceSelector", "podSelector"})
        self.assertEqual(peers[0]["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"], "fixture-router")
        self.assertEqual(peers[0]["podSelector"]["matchLabels"], {"app":"fixture-router"})
        self.assertEqual(policy["spec"]["podSelector"]["matchLabels"], {"app.kubernetes.io/name":"frontend"})
        self.assertEqual(policy["spec"]["ingress"][0]["ports"], [{"protocol":"TCP","port":8080}])
        be=next(d for d in candidates(self.c) if d["metadata"]["name"]=="seokpan-router-to-backend")
        self.assertEqual(be["spec"]["ingress"][0]["ports"], [{"protocol":"TCP","port":8000}])
    def test_ingress_only_and_frontend_scoped(self):
        policies = [d for d in candidates(self.c) if d["kind"] == "NetworkPolicy"]
        self.assertEqual(len(policies), 4)
        self.assertTrue(all(d["spec"]["policyTypes"] == ["Ingress"] and "egress" not in d["spec"] for d in policies))
        internal = next(d for d in policies if d["metadata"]["name"] == "seokpan-frontend-to-backend")
        peer = internal["spec"]["ingress"][0]["from"][0]
        self.assertNotIn("namespaceSelector", peer)
        self.assertEqual(peer["podSelector"]["matchLabels"], {"app.kubernetes.io/name":"frontend"})
    def test_invalid_scope_and_unknown_fields_refused(self):
        bad = [("app_namespace","default"),("app_namespace","openshift-user"),("app_namespace","cloud-input-required"),("app_namespace","fixture-argo"),("app_namespace","a"*64),("gitops_revision","main"),("router_pod_labels",{}),("router_pod_labels",{"app":"*"}),("router_namespace","fixture-cloud"),("include_pod_logs",1),("dedicated_namespace",False),("schema_version",True),("environment","recovery")]
        for key,value in bad:
            with self.subTest(key=key,value=value):
                c=copy.deepcopy(self.c); c[key]=value
                with self.assertRaises(Invalid): candidates(c)
        c=copy.deepcopy(self.c); c["client_secret"]="do-not-accept"
        with self.assertRaises(Invalid): candidates(c)
    def test_duplicate_json_and_output_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/"input.json"; output=root/"result.yaml"
            source.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaises(Invalid): read_contract(source)
            source.write_text(json.dumps(self.c))
            command=[sys.executable,str(ROOT/"tools/cloud_platform_contract.py"),str(source),"--output",str(output)]
            first=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            before=output.read_bytes()
            second=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(second.returncode,2)
            self.assertEqual(output.read_bytes(),before)
            self.assertNotIn("fixture-cloud",second.stderr)
if __name__ == "__main__":
    unittest.main()

"""Render first-lab control candidates and exercise execution/ownership holds.

These checks contact no cluster and do not prove admission or runtime safety.
"""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZE = os.environ.get("KUSTOMIZE", shutil.which("kustomize") or "kustomize")
PATHS = ("clusters/ocp-lab/bootstrap", "clusters/ocp-lab/root",
         "clusters/ocp-lab/reuse", "clusters/ocp-lab/new-namespace",
         "platform/ocp-lab/new-namespace", "operations/ocp-lab/migration")


class OCPControlBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renders = {}
        for path in PATHS:
            output = subprocess.run([KUSTOMIZE, "build", str(ROOT / path)],
                                    check=True, capture_output=True, text=True).stdout
            cls.renders[path] = list(yaml.safe_load_all(output))

    def resources(self):
        return [x for rows in self.renders.values() for x in rows]

    def test_default_root_does_not_adopt_namespace_or_platform(self):
        root = self.renders["clusters/ocp-lab/root"]
        self.assertEqual({x["kind"] for x in root}, {"AppProject", "Application"})
        apps = [x for x in root if x["kind"] == "Application"]
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["spec"]["source"]["path"], "apps/overlays/lab")
        self.assertFalse(any(x["kind"] in {"Namespace", "Secret", "Job"} for x in root))

    def test_all_applications_are_manual_pinned_input_and_non_cascading(self):
        apps = [(path, x) for path, rows in self.renders.items()
                for x in rows if x["kind"] == "Application"]
        self.assertEqual(len(apps), 4)
        for path, app in apps:
            with self.subTest(path=path, app=app["metadata"]["name"]):
                # Protections apply to every Application, registered or not.
                self.assertNotIn("automated", app["spec"]["syncPolicy"])
                options = app["spec"]["syncPolicy"]["syncOptions"]
                self.assertIn("FailOnSharedResource=true", options)
                if path == "clusters/ocp-lab/root":
                    # Application-level defaults protect every resource this Application manages.
                    # The metadata sync-options annotation only affects the Application object itself.
                    self.assertEqual(set(options),
                                     {"FailOnSharedResource=true", "Prune=false", "Delete=false"})
                else:
                    self.assertEqual(options, ["FailOnSharedResource=true"])
                self.assertFalse(app["metadata"].get("finalizers"))
                self.assertEqual(app["spec"]["source"]["repoURL"],
                                 "https://github.com/seokpan/seokpan-hybrid-gitops.git")
                self.assertTrue((ROOT / app["spec"]["source"]["path"]).is_dir())
                if path == "clusters/ocp-lab/root":
                    continue  # registered inputs are asserted below
                self.assertEqual(app["metadata"]["namespace"], "gitops-controller-input-required")
                self.assertEqual(app["spec"]["source"]["targetRevision"],
                                 "GITOPS_REVISION_INPUT_REQUIRED")

    def test_registered_root_targets_shared_controller_project_and_pinned_sha(self):
        # Only clusters/ocp-lab/root carries real registration inputs (path A, restricted
        # Project); the other candidate paths keep their input-required placeholders.
        root = self.renders["clusters/ocp-lab/root"]
        project = next(x for x in root if x["kind"] == "AppProject")
        app = next(x for x in root if x["kind"] == "Application")
        self.assertEqual(project["metadata"]["namespace"], "openshift-gitops")
        self.assertEqual(app["metadata"]["namespace"], "openshift-gitops")
        for control in (project, app):
            self.assertEqual(control["metadata"]["annotations"]["seokpan.io/release-state"],
                             "source-reviewed-runtime-unverified")
        self.assertEqual(app["spec"]["project"], project["metadata"]["name"])
        self.assertEqual(app["spec"]["destination"],
                         {"server": "https://kubernetes.default.svc", "namespace": "seokpan-argotest"})
        # A full commit SHA, never a branch/tag or the placeholder.
        self.assertRegex(app["spec"]["source"]["targetRevision"], r"^[0-9a-f]{40}$")

    def test_app_project_cannot_own_secret_namespace_operator_or_migration(self):
        app = next(x for x in self.renders["clusters/ocp-lab/root"] if x["kind"] == "AppProject")
        self.assertEqual(app["spec"]["clusterResourceWhitelist"], [])
        self.assertEqual(app["spec"]["clusterResourceBlacklist"], [{"group": "*", "kind": "*"}])
        allowed = {(x["group"], x["kind"]) for x in app["spec"]["namespaceResourceWhitelist"]}
        # StatefulSet is allowed only for the held lab Valkey (lab-redis); no wildcard.
        self.assertEqual(allowed, {("apps", "Deployment"), ("apps", "StatefulSet"),
                                   ("", "Service"), ("", "ConfigMap"),
                                   ("route.openshift.io", "Route")})
        self.assertEqual(app["spec"]["destinations"],
                         [{"server": "https://kubernetes.default.svc", "namespace": "seokpan-argotest"}])
        for project in [x for x in self.resources() if x["kind"] == "AppProject"]:
            self.assertNotIn("*", str(project["spec"]["sourceRepos"]))
            self.assertNotIn("*", str(project["spec"]["destinations"]))
            self.assertNotIn("*", str(project["spec"]["clusterResourceWhitelist"]))
            self.assertNotIn("*", str(project["spec"]["namespaceResourceWhitelist"]))
            self.assertNotIn("roles", project["spec"])

    def test_namespace_creation_requires_separate_protected_path(self):
        namespaces = [x for x in self.resources() if x["kind"] == "Namespace"]
        self.assertEqual(len(namespaces), 1)
        ns = namespaces[0]
        self.assertEqual(ns["metadata"]["name"], "seokpan-argotest")
        self.assertNotIn("labels", ns["metadata"])
        self.assertNotIn("namespace", ns["metadata"])
        project = next(x for x in self.renders["clusters/ocp-lab/new-namespace"]
                       if x["kind"] == "AppProject")
        self.assertEqual(project["spec"]["clusterResourceWhitelist"], [{"group": "", "kind": "Namespace"}])
        self.assertEqual(project["spec"]["namespaceResourceWhitelist"], [])
        self.assertEqual(project["spec"]["namespaceResourceBlacklist"], [{"group": "*", "kind": "*"}])

    def test_argocd_prune_delete_controls_and_owner_separation_are_explicit(self):
        for resource in self.resources():
            options = resource["metadata"]["annotations"]["argocd.argoproj.io/sync-options"]
            self.assertEqual(set(options.split(",")), {"Prune=false", "Delete=false"})
            self.assertNotIn("argocd.argoproj.io/hook", resource["metadata"]["annotations"])
        self.assertFalse({"Secret", "Subscription", "OperatorGroup", "PersistentVolumeClaim"}
                         & {x["kind"] for x in self.resources()})
        reuse = self.renders["clusters/ocp-lab/reuse"]
        self.assertEqual(len(reuse), 1)
        self.assertEqual(reuse[0]["spec"]["project"], "existing-project-input-required")

    def test_migration_is_separate_suspended_read_only_no_auto_retry(self):
        job, = self.renders["operations/ocp-lab/migration"]
        self.assertEqual(job["kind"], "Job")
        self.assertTrue(job["spec"]["suspend"])
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 300)
        self.assertEqual((job["spec"]["parallelism"], job["spec"]["completions"],
                          job["spec"]["backoffLimit"]), (1, 1, 0))
        pod = job["spec"]["template"]["spec"]
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertFalse(pod["automountServiceAccountToken"])
        container, = pod["containers"]
        self.assertEqual(container["command"], ["seokpan-migration-gate"])
        self.assertEqual(container["args"][0], "current")
        self.assertNotIn("--execute", container["args"])
        self.assertNotIn("--approval-ref", container["args"])
        lab_output = subprocess.run([KUSTOMIZE, "build", str(ROOT / "apps/overlays/lab")],
                                    check=True, capture_output=True, text=True).stdout
        backend = next(r for r in yaml.safe_load_all(lab_output)
                       if r["kind"] == "Deployment" and r["metadata"]["name"] == "backend")
        backend_pod = backend["spec"]["template"]["spec"]
        self.assertEqual(container["image"], backend_pod["containers"][0]["image"])
        self.assertNotIn("imagePullSecrets", pod)
        self.assertNotIn("imagePullSecrets", backend_pod)
        self.assertEqual(container["env"], [{"name": "SEOKPAN_MIGRATION_DATABASE_URL",
            "valueFrom": {"secretKeyRef": {"name": "backend-db-migration",
                                            "key": "SEOKPAN_MIGRATION_DATABASE_URL"}}}])
        self.assertEqual(container["envFrom"], [{"configMapRef": {"name": "backend-config-input-required"}}])
        self.assertNotIn("runAsUser", container["securityContext"])
        self.assertNotIn("hostAliases", pod)
        paths = [x["spec"]["source"]["path"] for x in self.resources() if x["kind"] == "Application"]
        self.assertFalse(any(p.startswith("operations/") for p in paths))


if __name__ == "__main__":
    unittest.main()

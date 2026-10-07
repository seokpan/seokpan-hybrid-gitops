"""Synthetic path-A registration checks; no active Workload or Controller acceptance."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

from check_ocp_lab_registration import CONTROLLER, KINDS, NAME, registration_blockers

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40  # Synthetic identity, never a deployment recommendation.


def candidate():
    objects = [yaml.safe_load((ROOT / "clusters/ocp-lab/root" / name).read_text())
               for name in ("app-project.yaml", "app.yaml")]
    for obj in objects:
        obj["metadata"]["namespace"] = CONTROLLER
    objects[1]["spec"]["source"]["targetRevision"] = SHA
    return objects


def check(objects, sha=SHA):
    return registration_blockers(yaml.safe_dump_all(objects), sha)


class RegistrationBoundaries(unittest.TestCase):
    def test_selected_two_object_synthetic_candidate_passes(self):
        self.assertEqual(check(candidate()), [])

    def test_current_checked_in_placeholders_are_not_registration_ready(self):
        objects = [yaml.safe_load((ROOT / "clusters/ocp-lab/root" / name).read_text())
                   for name in ("app-project.yaml", "app.yaml")]
        self.assertTrue(check(objects))

    def test_extra_root_namespace_or_job_is_rejected(self):
        for kind in ("Application", "Namespace", "Job", "Secret"):
            with self.subTest(kind=kind):
                self.assertTrue(check(candidate() + [{"kind": kind}]))

    def test_both_control_objects_require_exact_name_and_controller_namespace(self):
        for index in (0, 1):
            for field, value in (("name", "default"), ("namespace", "seokpan-argotest")):
                with self.subTest(index=index, field=field):
                    objects = candidate(); objects[index]["metadata"][field] = value
                    self.assertTrue(check(objects))

    def test_default_project_and_other_destination_are_rejected(self):
        for field, value in (("project", "default"),
                             ("destination", {"server": "*", "namespace": "*"})):
            with self.subTest(field=field):
                objects = candidate(); objects[1]["spec"][field] = value
                self.assertTrue(check(objects))

    def test_project_repository_destination_and_cluster_permissions_stay_restricted(self):
        for field, value in (("sourceRepos", ["*"]), ("destinations", []),
                             ("clusterResourceWhitelist", [{"group": "*", "kind": "*"}]),
                             ("clusterResourceBlacklist", []), ("roles", [])):
            with self.subTest(field=field):
                objects = candidate(); objects[0]["spec"][field] = value
                self.assertTrue(check(objects))

    def test_only_five_namespaced_kinds_are_allowed(self):
        for kind in ("Secret", "Job", "PersistentVolumeClaim", "*", "Namespace"):
            with self.subTest(kind=kind):
                objects = candidate()
                objects[0]["spec"]["namespaceResourceWhitelist"].append({"group": "", "kind": kind})
                self.assertTrue(check(objects))
        objects = candidate(); objects[0]["spec"]["namespaceResourceWhitelist"].pop()
        self.assertTrue(check(objects))
        self.assertEqual(len(KINDS), 5)

    def test_pinned_prior_workload_sha_not_main_short_or_different_revision(self):
        for value in ("main", "INPUT_REQUIRED", SHA[:12], "b" * 40):
            with self.subTest(value=value):
                objects = candidate(); objects[1]["spec"]["source"]["targetRevision"] = value
                self.assertTrue(check(objects))
        for value in (None, True, 1, "main", "A" * 40):
            self.assertTrue(check(candidate(), value))

    def test_source_overrides_and_multiple_sources_are_rejected(self):
        objects = candidate(); objects[1]["spec"]["source"]["kustomize"] = {"images": ["changed"]}
        self.assertTrue(check(objects))
        objects = candidate(); objects[1]["spec"]["sources"] = []
        self.assertTrue(check(objects))

    def test_automated_sync_force_prune_and_initial_operation_are_rejected(self):
        for policy in ({"automated": {}}, {"automated": {"selfHeal": True, "prune": True}},
                       {"syncOptions": ["Force=true"]}):
            objects = candidate(); objects[1]["spec"]["syncPolicy"] = policy
            self.assertTrue(check(objects))
        objects = candidate(); objects[1]["operation"] = {"sync": {"revision": SHA}}
        self.assertTrue(check(objects))

    def test_cascade_or_external_owner_and_missing_protections_are_rejected(self):
        for index in (0, 1):
            for field, value in (("finalizers", ["resources-finalizer.argocd.argoproj.io"]),
                                 ("ownerReferences", [{"name": "other-root"}]), ("annotations", {})):
                objects = candidate(); objects[index]["metadata"][field] = value
                self.assertTrue(check(objects))

    def test_malformed_missing_and_duplicate_mapping_keys_are_rejected(self):
        for text in ("", "[]", "[", "---\n---", "kind: AppProject\nkind: Application\n"):
            self.assertTrue(registration_blockers(text, SHA))
        objects = candidate(); del objects[1]["spec"]["source"]
        self.assertTrue(check(objects))

    def test_validation_does_not_mutate_input_or_create_outputs(self):
        objects = candidate(); before = deepcopy(objects)
        self.assertEqual(check(objects), [])
        self.assertEqual(objects, before)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registration.yaml"
            path.write_text(yaml.safe_dump_all(objects))
            before = path.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / "tools/check_ocp_lab_registration.py"),
                                     "--manifest", str(path), "--workload-sha", SHA],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("NOT VERIFIED", result.stdout)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()

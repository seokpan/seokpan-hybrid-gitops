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

    def test_checked_in_workload_sha_must_match_the_explicit_comparison_input(self):
        objects = [yaml.safe_load((ROOT / "clusters/ocp-lab/root" / name).read_text())
                   for name in ("app-project.yaml", "app.yaml")]
        self.assertTrue(check(objects))

    def test_checked_in_registered_source_matches_its_pinned_workload_sha(self):
        objects = [yaml.safe_load((ROOT / "clusters/ocp-lab/root" / name).read_text())
                   for name in ("app-project.yaml", "app.yaml")]
        self.assertEqual(check(objects, objects[1]["spec"]["source"]["targetRevision"]), [])

    def test_legacy_hold_or_runtime_pass_annotation_is_not_registration_ready(self):
        for index in (0, 1):
            for state in ("input-required-no-runtime-validation", "runtime-pass"):
                with self.subTest(index=index, state=state):
                    objects = candidate()
                    objects[index]["metadata"]["annotations"]["seokpan.io/release-state"] = state
                    self.assertTrue(check(objects))

    def test_prune_delete_and_shared_resource_controls_are_all_required(self):
        controls = ["FailOnSharedResource=true", "Prune=false", "Delete=false"]
        for missing in controls:
            with self.subTest(missing=missing):
                objects = candidate()
                objects[1]["spec"]["syncPolicy"] = {"syncOptions": [x for x in controls if x != missing]}
                self.assertTrue(check(objects))
        for extra in ("Prune=true", "Delete=true", "Force=true", "Replace=true"):
            with self.subTest(extra=extra):
                objects = candidate()
                objects[1]["spec"]["syncPolicy"]["syncOptions"].append(extra)
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

    def test_skip_reconcile_annotation_is_rejected(self):
        for index in (0, 1):
            for value in ("true", "false", True):
                with self.subTest(index=index, value=value):
                    objects = candidate()
                    objects[index]["metadata"]["annotations"]["argocd.argoproj.io/skip-reconcile"] = value
                    self.assertTrue(check(objects))

    def test_unreviewed_argocd_and_other_annotations_are_rejected(self):
        for index in (0, 1):
            for key in ("argocd.argoproj.io/sync-wave", "argocd.argoproj.io/hook", "example.org/policy"):
                with self.subTest(index=index, key=key):
                    objects = candidate(); objects[index]["metadata"]["annotations"][key] = "unreviewed"
                    self.assertTrue(check(objects))

    def test_unexpected_metadata_labels_are_rejected(self):
        for index in (0, 1):
            for labels in ({"argocd.argoproj.io/instance": "other-root"},
                           {"app.kubernetes.io/part-of": "other-policy"}, None, [], "invalid"):
                with self.subTest(index=index, labels=labels):
                    objects = candidate(); objects[index]["metadata"]["labels"] = labels
                    self.assertTrue(check(objects))

    def test_annotation_values_and_extra_metadata_fields_are_rejected(self):
        for index in (0, 1):
            for annotations in ({}, None, [], "invalid"):
                objects = candidate(); objects[index]["metadata"]["annotations"] = annotations
                self.assertTrue(check(objects))
            objects = candidate()
            objects[index]["metadata"]["annotations"]["seokpan.io/release-state"] = "runtime-pass"
            self.assertTrue(check(objects))
            objects = candidate(); objects[index]["metadata"]["generateName"] = "unreviewed-"
            self.assertTrue(check(objects))

    def test_explicit_empty_labels_preserve_the_reviewed_candidate(self):
        objects = candidate()
        for obj in objects:
            obj["metadata"]["labels"] = {}
        self.assertEqual(check(objects), [])

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

"""Static Cloud candidate/target checks using actual Kustomize output.

The target build is a preview of approved settings, not a Runtime or rollout.
No cluster, registry or AWS calls are made. Requires Kustomize and PyYAML.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import urlsplit

import yaml

from render_release import app_manifest_blockers
from test_app_manifests import load_release_candidates, overlay_images


ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZE = os.environ.get("KUSTOMIZE", shutil.which("kustomize") or "kustomize")

CLOUD_ECR = {
    "backend": "847835841591.dkr.ecr.ap-northeast-2.amazonaws.com/seokpan-fnd-backend",
    "frontend": "847835841591.dkr.ecr.ap-northeast-2.amazonaws.com/seokpan-fnd-frontend",
}
PLACEHOLDER = "INPUT_REQUIRED"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def cloud_release_state(images, candidates):
    """Return "placeholder" while both digests are INPUT_REQUIRED.

    Otherwise return the cloud release ids whose ecr_digest (never harbor_digest)
    equals BOTH overlay digests. Fixed newName, digest (not newTag) and a
    sha256 form are enforced; a half-filled overlay is rejected.
    """
    wanted = {}
    for component in ("backend", "frontend"):
        entry = images.get("seokpan-" + component)
        if not isinstance(entry, dict):
            raise AssertionError("seokpan-%s image entry is missing" % component)
        if "newTag" in entry:
            raise AssertionError("seokpan-%s must use digest, not newTag" % component)
        if entry.get("newName") != CLOUD_ECR[component]:
            raise AssertionError("seokpan-%s newName is not the approved ECR repository" % component)
        digest = entry.get("digest")
        if digest != PLACEHOLDER and not (isinstance(digest, str) and DIGEST.match(digest)):
            raise AssertionError("seokpan-%s digest must be INPUT_REQUIRED or sha256:<64 hex>" % component)
        wanted[component] = digest
    placeholders = [c for c in wanted if wanted[c] == PLACEHOLDER]
    if len(placeholders) == 2:
        return "placeholder"
    if placeholders:
        raise AssertionError("Cloud digests must be both INPUT_REQUIRED or both sha256 digests")
    return sorted(release_id for release_id, document in candidates.items()
                  if all(document["images"][c]["ecr_digest"] == wanted[c] for c in wanted))


class CloudManifestBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renders = {}
        for name, path in (("held", "apps/overlays/cloud"),
                           ("target", "apps/overlays/cloud/activation-target")):
            rendered = subprocess.run([KUSTOMIZE, "build", str(ROOT / path)],
                                      check=True, capture_output=True, text=True).stdout
            cls.renders[name] = list(yaml.safe_load_all(rendered))

    def resources(self, preview, kind):
        return [r for r in self.renders[preview] if r["kind"] == kind]

    def test_default_cloud_stays_held_and_target_does_not_hide_input_blockers(self):
        self.assertEqual(self.resources("held", "PodDisruptionBudget"), [])
        for preview, replicas in (("held", 0), ("target", 3)):
            deployments = self.resources(preview, "Deployment")
            self.assertEqual({d["metadata"]["name"] for d in deployments},
                             {"frontend", "backend"})
            for deployment in deployments:
                self.assertEqual(deployment["spec"]["replicas"], replicas)
                self.assertIn("input-required", deployment["metadata"]["annotations"][
                    "seokpan.io/release-state"])
                container = deployment["spec"]["template"]["spec"]["containers"][0]
                # Held until Promotion fills it; once filled, the digest is covered by
                # test_cloud_images_use_fixed_ecr_names_and_ecr_digest_from_one_cloud_candidate.
                repository, _, reference = container["image"].partition("@")
                self.assertEqual(repository, CLOUD_ECR[deployment["metadata"]["name"]])
                self.assertTrue(reference == "INPUT_REQUIRED" or DIGEST.match(reference))

    def test_cloud_images_use_fixed_ecr_names_and_ecr_digest_from_one_cloud_candidate(self):
        images = overlay_images(ROOT / "apps/overlays/cloud/runtime/kustomization.yaml")
        candidates = load_release_candidates(ROOT / "releases", "cloud")
        state = cloud_release_state(images, candidates)
        self.assertTrue(state == "placeholder" or state,
                        "Cloud digests must be INPUT_REQUIRED or match one cloud release candidate's ecr_digest")

    def test_cloud_requires_explicit_lifecycle_rollout_input_before_multi_replica_release(self):
        for preview in self.renders:
            data = self.resources(preview, "ConfigMap")[0]["data"]
            self.assertEqual(data["SEOKPAN_GAME_LIFECYCLE_MODE"], "INPUT_REQUIRED")
        blockers = app_manifest_blockers(yaml.safe_dump_all(self.renders["target"]), "cloud")
        self.assertIn("multi-replica Cloud activation requires reviewed captured lifecycle configuration", blockers)
        # This keeps a rollout decision unresolved instead of silently inheriting
        # legacy or enabling captured. Actual Data/old-writer/2-Pod/Gateway gates
        # remain the App rollout owner's responsibility.

    def test_target_pdb_selectors_namespace_and_rollout_match_each_workload(self):
        workloads = {r["metadata"]["name"]: r for r in self.resources("target", "Deployment")}
        budgets = self.resources("target", "PodDisruptionBudget")
        self.assertEqual(len(budgets), 2)
        for budget in budgets:
            workload = workloads[budget["metadata"]["name"]]
            self.assertEqual(budget["metadata"]["namespace"], workload["metadata"]["namespace"])
            self.assertEqual(budget["spec"]["minAvailable"], 2)
            self.assertEqual(budget["spec"]["selector"]["matchLabels"],
                             workload["spec"]["template"]["metadata"]["labels"])
            self.assertEqual(workload["spec"]["strategy"]["rollingUpdate"],
                             {"maxSurge": 1, "maxUnavailable": 0})

    def test_target_zone_and_host_spread_remain_soft_and_app_specific(self):
        for deployment in self.resources("target", "Deployment"):
            pod = deployment["spec"]["template"]["spec"]
            labels = deployment["spec"]["template"]["metadata"]["labels"]
            spread, = pod["topologySpreadConstraints"]
            self.assertEqual(spread["topologyKey"], "topology.kubernetes.io/zone")
            self.assertEqual(spread["maxSkew"], 1)
            self.assertEqual(spread["whenUnsatisfiable"], "ScheduleAnyway")
            self.assertEqual(spread["labelSelector"]["matchLabels"], labels)
            anti = pod["affinity"]["podAntiAffinity"]
            self.assertNotIn("requiredDuringSchedulingIgnoredDuringExecution", anti)
            term, = anti["preferredDuringSchedulingIgnoredDuringExecution"]
            self.assertEqual(term["podAffinityTerm"]["topologyKey"], "kubernetes.io/hostname")
            self.assertEqual(term["podAffinityTerm"]["labelSelector"]["matchLabels"], labels)

    def test_cloud_does_not_own_namespace_secret_data_or_pull_auth(self):
        forbidden = {"Namespace", "Secret", "ServiceAccount", "Role", "RoleBinding",
                     "ClusterRole", "ClusterRoleBinding", "NetworkPolicy", "Application",
                     "AppProject", "Job", "CronJob", "StatefulSet", "PersistentVolumeClaim",
                     "HorizontalPodAutoscaler"}
        for preview in self.renders:
            self.assertFalse(forbidden & {r["kind"] for r in self.renders[preview]})
            keys = [(r["apiVersion"], r["kind"], r["metadata"].get("namespace"),
                     r["metadata"]["name"]) for r in self.renders[preview]]
            self.assertEqual(len(keys), len(set(keys)))
            for deployment in self.resources(preview, "Deployment"):
                pod = deployment["spec"]["template"]["spec"]
                self.assertNotIn("imagePullSecrets", pod)
                self.assertNotIn("hostAliases", pod)
                self.assertFalse(pod["automountServiceAccountToken"])
                for context in [pod["securityContext"],
                                *(c["securityContext"] for c in pod["containers"])]:
                    self.assertFalse({"runAsUser", "runAsGroup", "fsGroup"} & context.keys())

    def test_cloud_tls_targets_auth_ca_are_explicit_and_separate(self):
        for preview in self.renders:
            data = self.resources(preview, "ConfigMap")[0]["data"]
            self.assertEqual(data["SEOKPAN_CONNECTION_PROFILE"], "cloud")
            self.assertIn("rds-endpoint-input-required", data["SEOKPAN_DATABASE_EXPECTED_HOST"])
            self.assertNotIn("SEOKPAN_REDIS_AUTH_TOKEN", data)
            redis = urlsplit(data["SEOKPAN_REDIS_URL"])
            self.assertEqual(redis.scheme, "rediss")
            self.assertIsNone(redis.username)
            self.assertIsNone(redis.password)
            self.assertEqual(redis.query, "")
            self.assertEqual(redis.hostname, data["SEOKPAN_REDIS_EXPECTED_HOST"])
            self.assertEqual(str(redis.port), data["SEOKPAN_REDIS_EXPECTED_PORT"])
            self.assertEqual(redis.path, "/" + data["SEOKPAN_REDIS_EXPECTED_DATABASE"])
            self.assertIn("redis-primary-endpoint", redis.hostname)
            backend = next(d for d in self.resources(preview, "Deployment")
                           if d["metadata"]["name"] == "backend")
            pod = backend["spec"]["template"]["spec"]
            values = {e["name"]: e for e in pod["containers"][0]["env"]}
            for name in ("SEOKPAN_IDENTITY_DATABASE_URL", "SEOKPAN_GAME_DATABASE_URL",
                         "SEOKPAN_REDIS_AUTH_TOKEN"):
                self.assertIn("secretKeyRef", values[name]["valueFrom"])
                self.assertNotIn("value", values[name])
            volumes = {v["name"]: v for v in pod["volumes"]}
            self.assertEqual(volumes["database-ca"]["configMap"]["name"], "backend-database-ca")
            self.assertEqual(volumes["redis-ca"]["configMap"]["name"], "backend-redis-ca")

    def test_cloud_same_origin_edge_routes_exclude_public_probes(self):
        for preview in self.renders:
            data = self.resources(preview, "ConfigMap")[0]["data"]
            origin, = json.loads(data["SEOKPAN_ALLOWED_ORIGINS"])
            self.assertEqual(urlsplit(origin).scheme, "https")
            routes = self.resources(preview, "Route")
            self.assertEqual(len(routes), 3)
            self.assertEqual({r["spec"]["host"] for r in routes}, {urlsplit(origin).hostname})
            self.assertEqual({r["spec"].get("path", "/") for r in routes},
                             {"/", "/api/v1", "/ws/v1"})
            for route in routes:
                self.assertEqual(route["spec"]["tls"],
                                 {"termination": "edge", "insecureEdgeTerminationPolicy": "Redirect"})
                self.assertNotIn("health", route["spec"].get("path", ""))
                self.assertNotIn("haproxy.router.openshift.io/timeout-tunnel",
                                 route["metadata"].get("annotations", {}))

    def test_reviewed_cloud_config_change_changes_backend_template_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            copied_apps = Path(directory) / "apps"
            shutil.copytree(ROOT / "apps", copied_apps)

            def render():
                result = subprocess.run(
                    [KUSTOMIZE, "build", str(copied_apps / "overlays/cloud")],
                    check=True, capture_output=True, text=True,
                )
                resources = list(yaml.safe_load_all(result.stdout))
                config = next(r for r in resources if r["kind"] == "ConfigMap")
                backend = next(r for r in resources if r["kind"] == "Deployment"
                               and r["metadata"]["name"] == "backend")
                return config, backend["spec"]["template"]

            before_config, before_template = render()
            runtime = copied_apps / "overlays/cloud/runtime/runtime.env"
            old_host = before_config["data"]["SEOKPAN_DATABASE_EXPECTED_HOST"]
            new_host = "cloud-db-revised.example.test"
            runtime.write_text(runtime.read_text(encoding="utf-8").replace(
                "SEOKPAN_DATABASE_EXPECTED_HOST=" + old_host,
                "SEOKPAN_DATABASE_EXPECTED_HOST=" + new_host,
            ), encoding="utf-8")
            after_config, after_template = render()
            self.assertNotEqual(before_config["metadata"]["name"], after_config["metadata"]["name"])
            self.assertNotEqual(before_template, after_template)
            for config, template in ((before_config, before_template),
                                     (after_config, after_template)):
                self.assertEqual(template["spec"]["containers"][0]["envFrom"],
                                 [{"configMapRef": {"name": config["metadata"]["name"]}}])

    def test_release_gate_blocks_actual_cloud_draft_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cloud.yaml"
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/render_release.py"), "cloud",
                 "--output", str(output), "--kustomize", KUSTOMIZE],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("INPUT_REQUIRED", result.stderr)
            self.assertIn("zero-replica activation hold", result.stderr)
            self.assertFalse(output.exists())


class CloudDigestFromReleaseCandidate(unittest.TestCase):
    """Cloud digests come from ecr_digest of ONE cloud candidate; Harbor is never a substitute."""

    A = {"backend": "sha256:" + "a" * 64, "frontend": "sha256:" + "b" * 64}
    B = {"backend": "sha256:" + "c" * 64, "frontend": "sha256:" + "d" * 64}

    @staticmethod
    def images(digests, names=CLOUD_ECR):
        return {"seokpan-" + c: {"name": "seokpan-" + c, "newName": names[c], "digest": digests[c]}
                for c in ("backend", "frontend")}

    @staticmethod
    def candidate(ecr, harbor):
        return {"images": {c: {"ecr_digest": ecr[c], "harbor_digest": harbor[c]}
                           for c in ("backend", "frontend")}}

    def test_placeholders_are_accepted_until_the_first_promotion(self):
        both = {c: PLACEHOLDER for c in ("backend", "frontend")}
        self.assertEqual(cloud_release_state(self.images(both), {}), "placeholder")

    def test_both_digests_matching_one_candidate_ecr_digest_pass(self):
        candidates = {"rel-cloud-a": self.candidate(self.A, self.B)}
        self.assertEqual(cloud_release_state(self.images(self.A), candidates), ["rel-cloud-a"])

    def test_harbor_digest_can_never_stand_in_for_ecr_digest(self):
        candidates = {"rel-cloud-a": self.candidate(self.A, self.B)}
        self.assertEqual(cloud_release_state(self.images(self.B), candidates), [])

    def test_frontend_and_backend_from_different_candidates_are_rejected(self):
        candidates = {"rel-cloud-a": self.candidate(self.A, self.A),
                      "rel-cloud-b": self.candidate(self.B, self.B)}
        mixed = {"backend": self.A["backend"], "frontend": self.B["frontend"]}
        self.assertEqual(cloud_release_state(self.images(mixed), candidates), [])

    def test_half_filled_overlay_new_tag_wrong_name_and_bad_digest_are_rejected(self):
        half = {"backend": self.A["backend"], "frontend": PLACEHOLDER}
        with self.assertRaises(AssertionError):
            cloud_release_state(self.images(half), {})
        with_tag = self.images(self.A)
        with_tag["seokpan-backend"]["newTag"] = "v1"
        with self.assertRaises(AssertionError):
            cloud_release_state(with_tag, {})
        for bad_name in ("harbor.seokpan.soldesk.store/seokpan-hybrid/%s",
                         "ecr-input-required.invalid/seokpan-fnd-%s"):
            names = {c: bad_name % c for c in ("backend", "frontend")}
            with self.subTest(newName=bad_name), self.assertRaises(AssertionError):
                cloud_release_state(self.images(self.A, names=names), {})
        with self.assertRaises(AssertionError):
            cloud_release_state(self.images({"backend": "sha256:abc", "frontend": self.A["frontend"]}), {})


if __name__ == "__main__":
    unittest.main()

# 작성자: 최유준 / 작성 날짜: 2026/10/14
"""Consistency checks for the release-source annotations (hybrid-gitops#50).

An environment that carries `release-source.yaml` claims "these Images were built from App SHA X and
promoted by Release Y". These checks keep that claim true: the annotation must match the environment's
release candidate (Release ID, App SHA, both Digests and the Registry), and the real Kustomize build must
differ from the build without the patch ONLY by the two Deployment metadata annotations (never the Pod
template, so no rollout).

The checker functions are pure so the mismatch cases are exercised with synthetic data, the same way the
Recovery Digest checks are. Requires kustomize v5.7.1 and PyYAML. No cluster or external service is
contacted. These tests are not a Runtime, deployment or Sync result.
"""

import copy
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

from test_app_manifests import (
    COMPONENTS, KUSTOMIZE, RECOVERY_REGISTRY, ROOT, load_release_candidates, overlay_images,
    recovery_release_matches)
from test_cloud_manifests import CLOUD_ECR, cloud_release_state

APP_SHA_KEY = "seokpan.io/app-source-sha"
RELEASE_ID_KEY = "seokpan.io/release-id"
SOURCE_FILE = "release-source.yaml"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ENV_DIRS = {"recovery": "apps/overlays/recovery", "cloud": "apps/overlays/cloud/runtime"}


def source_values(docs):
    """Validate the shape of release-source.yaml and return (app_sha, release_id)."""
    if len(docs) != len(COMPONENTS):
        raise AssertionError("release-source.yaml must hold exactly one Deployment per component")
    names, values = [], set()
    for doc in docs:
        if not isinstance(doc, dict) or set(doc) != {"apiVersion", "kind", "metadata"}:
            raise AssertionError("each document may only hold apiVersion, kind and metadata (no spec / Pod template)")
        if doc["apiVersion"] != "apps/v1" or doc["kind"] != "Deployment":
            raise AssertionError("only apps/v1 Deployment metadata patches are allowed")
        metadata = doc["metadata"]
        if not isinstance(metadata, dict) or set(metadata) != {"name", "annotations"}:
            raise AssertionError("metadata may only hold name and annotations")
        annotations = metadata["annotations"]
        if not isinstance(annotations, dict) or set(annotations) != {APP_SHA_KEY, RELEASE_ID_KEY}:
            raise AssertionError("annotations must be exactly %s and %s" % (APP_SHA_KEY, RELEASE_ID_KEY))
        if not all(isinstance(value, str) for value in annotations.values()):
            raise AssertionError("annotation values must be strings")
        names.append(metadata["name"])
        values.add((annotations[APP_SHA_KEY], annotations[RELEASE_ID_KEY]))
    if sorted(names) != sorted(COMPONENTS):
        raise AssertionError("release-source.yaml must patch backend and frontend once each")
    if len(values) != 1:
        raise AssertionError("backend and frontend must carry the same App SHA and Release ID")
    return values.pop()


def source_registrations(kustomization_text):
    """The `patches:` entries that reference release-source.yaml (expected: one plain `path:` entry)."""
    document = yaml.safe_load(kustomization_text) or {}
    return [entry for entry in document.get("patches") or []
            if isinstance(entry, dict) and entry.get("path") == SOURCE_FILE]


def check_source_matches_candidate(env, app_sha, release_id, images, candidates):
    """The annotation's claim: this overlay's Images are Release `release_id`'s, built from `app_sha`."""
    if not SHA40.match(app_sha):
        raise AssertionError("app-source-sha must be a 40-hex commit SHA")
    candidate = candidates.get(release_id)
    if candidate is None:
        raise AssertionError("release-id %s has no %s release candidate" % (release_id, env))
    if candidate["source"].get("app_sha") != app_sha:
        raise AssertionError("app-source-sha differs from the candidate's source.app_sha")
    if env == "recovery":
        matched = recovery_release_matches(images, {release_id: candidate})
    else:
        matched = cloud_release_state(images, {release_id: candidate})
    if matched != [release_id]:
        raise AssertionError("%s overlay Digests/Registry do not match release candidate %s" % (env, release_id))


def check_build_difference(with_docs, without_docs, app_sha, release_id):
    """The build with the patch may differ from the build without it ONLY by the two Deployment annotations."""
    def key(doc):
        return doc["kind"], doc["metadata"]["name"]

    built = {key(doc): doc for doc in with_docs}
    base = {key(doc): doc for doc in without_docs}
    if len(built) != len(with_docs) or len(base) != len(without_docs):
        raise AssertionError("rendered objects must have unique kind/name")
    if set(built) != set(base):
        raise AssertionError("the source patch must not add or remove objects")
    expected = {APP_SHA_KEY: app_sha, RELEASE_ID_KEY: release_id}
    changed = []
    for ident in sorted(built):
        after, before = built[ident], base[ident]
        if after == before:
            continue
        changed.append(ident)
        if after.get("spec") != before.get("spec"):
            raise AssertionError("%s %s: Pod template / spec changed (would roll out)" % ident)
        stripped = copy.deepcopy(after)
        annotations = stripped["metadata"].get("annotations") or {}
        for name, value in expected.items():
            if annotations.get(name) != value:
                raise AssertionError("%s %s: annotation %s is missing or differs" % (ident + (name,)))
            del annotations[name]
        if annotations:
            stripped["metadata"]["annotations"] = annotations
        else:
            stripped["metadata"].pop("annotations", None)
        if stripped != before:
            raise AssertionError("%s %s changed outside the two annotations" % ident)
    if changed != sorted(("Deployment", name) for name in COMPONENTS):
        raise AssertionError("exactly the backend and frontend Deployments must gain the annotations, got %s" % changed)


def build(directory):
    rendered_text = subprocess.run([KUSTOMIZE, "build", str(directory)],
                                   check=True, capture_output=True, text=True).stdout
    return [doc for doc in yaml.safe_load_all(rendered_text) if doc is not None]


def build_without_source(env):
    """Build a copy of the repository whose kustomization does not register release-source.yaml."""
    with tempfile.TemporaryDirectory() as tmp:
        copy_root = Path(tmp) / "repo"
        shutil.copytree(ROOT, copy_root, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__"))
        path = copy_root / ENV_DIRS[env] / "kustomization.yaml"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        kept = [entry for entry in document.get("patches") or []
                if not (isinstance(entry, dict) and entry.get("path") == SOURCE_FILE)]
        if kept:
            document["patches"] = kept
        else:
            document.pop("patches", None)
        path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
        return build(copy_root / ENV_DIRS[env])


def read_source_docs(env):
    text = (ROOT / ENV_DIRS[env] / SOURCE_FILE).read_text(encoding="utf-8")
    return [doc for doc in yaml.safe_load_all(text) if doc is not None]


class ReleaseSourceInRepository(unittest.TestCase):
    """The committed release-source files, checked against the committed candidates and a real build."""

    def test_source_files_have_only_the_annotation_shape_and_are_registered_once(self):
        for env, directory in ENV_DIRS.items():
            with self.subTest(env=env):
                source_values(read_source_docs(env))
                registered = source_registrations(
                    (ROOT / directory / "kustomization.yaml").read_text(encoding="utf-8"))
                self.assertEqual(registered, [{"path": SOURCE_FILE}])

    def test_annotations_match_the_environment_release_candidate(self):
        for env, directory in ENV_DIRS.items():
            with self.subTest(env=env):
                app_sha, release_id = source_values(read_source_docs(env))
                check_source_matches_candidate(
                    env, app_sha, release_id,
                    overlay_images(ROOT / directory / "kustomization.yaml"),
                    load_release_candidates(ROOT / "releases", env))

    def test_build_adds_only_the_two_annotations_to_the_two_deployments(self):
        for env, directory in ENV_DIRS.items():
            with self.subTest(env=env):
                app_sha, release_id = source_values(read_source_docs(env))
                check_build_difference(build(ROOT / directory), build_without_source(env), app_sha, release_id)


# ---------------------------------------------------------------- synthetic mismatch cases
SHA = "a1" * 20
OTHER_SHA = "b2" * 20
REC_ID = "rel-recovery-20261014T000000Z-%s-abcdef12" % SHA[:12]
CLD_ID = "rel-cloud-20261014T000000Z-%s-abcdef12" % SHA[:12]
OLD = {"backend": "sha256:" + "1" * 64, "frontend": "sha256:" + "2" * 64}
ECR = {"backend": "sha256:" + "3" * 64, "frontend": "sha256:" + "4" * 64}


def candidate(app_sha=SHA):
    return {"source": {"app_sha": app_sha},
            "images": {c: {"harbor_digest": OLD[c], "ecr_digest": ECR[c]} for c in COMPONENTS}}


def recovery_images(digests=OLD):
    return {"seokpan-" + c: {"name": "seokpan-" + c, "newName": "%s/%s" % (RECOVERY_REGISTRY, c),
                             "digest": digests[c]} for c in COMPONENTS}


def cloud_images(digests=ECR):
    return {"seokpan-" + c: {"name": "seokpan-" + c, "newName": CLOUD_ECR[c],
                             "digest": digests[c]} for c in COMPONENTS}


def source_docs(app_sha=SHA, release_id=REC_ID):
    return [{"apiVersion": "apps/v1", "kind": "Deployment",
             "metadata": {"name": c, "annotations": {APP_SHA_KEY: app_sha, RELEASE_ID_KEY: release_id}}}
            for c in COMPONENTS]


def rendered(annotated=False):
    docs = []
    for name in COMPONENTS:
        metadata = {"name": name, "labels": {"app": name}}
        if annotated:
            metadata["annotations"] = {APP_SHA_KEY: SHA, RELEASE_ID_KEY: REC_ID}
        docs.append({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata,
                     "spec": {"replicas": 0, "template": {"spec": {
                         "containers": [{"name": name, "image": "x@" + OLD[name]}]}}}})
    docs.append({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "backend-config-abc"},
                 "data": {"A": "1"}})
    return docs


class SourceShapeChecks(unittest.TestCase):
    def rejected(self, docs):
        with self.assertRaises(AssertionError):
            source_values(docs)

    def test_valid_shape_returns_sha_and_release_id(self):
        self.assertEqual(source_values(source_docs()), (SHA, REC_ID))

    def test_pod_template_or_spec_is_rejected(self):
        docs = source_docs()
        docs[0]["spec"] = {"template": {"metadata": {"labels": {"x": "y"}}}}
        self.rejected(docs)
        docs = source_docs()
        docs[1]["spec"] = {"replicas": 3}
        self.rejected(docs)

    def test_extra_missing_or_wrong_keys_are_rejected(self):
        cases = {
            "extra annotation": lambda d: d[0]["metadata"]["annotations"].update(extra="x"),
            "missing release id": lambda d: d[0]["metadata"]["annotations"].pop(RELEASE_ID_KEY),
            "extra metadata key": lambda d: d[0]["metadata"].update(labels={"a": "b"}),
            "wrong kind": lambda d: d[0].update(kind="StatefulSet"),
            "wrong apiVersion": lambda d: d[0].update(apiVersion="v1"),
            "non-string value": lambda d: d[0]["metadata"]["annotations"].update({APP_SHA_KEY: 12345}),
        }
        for label, mutate in cases.items():
            docs = source_docs()
            mutate(docs)
            with self.subTest(case=label):
                self.rejected(docs)

    def test_components_must_be_one_backend_and_one_frontend(self):
        duplicated = source_docs()
        duplicated[1]["metadata"]["name"] = "backend"
        renamed = source_docs()
        renamed[1]["metadata"]["name"] = "worker"
        cases = {"no documents": [], "only backend": source_docs()[:1],
                 "backend twice": duplicated, "unknown name": renamed}
        for label, docs in cases.items():
            with self.subTest(case=label):
                self.rejected(docs)

    def test_both_deployments_must_carry_the_same_values(self):
        docs = source_docs()
        docs[1]["metadata"]["annotations"][RELEASE_ID_KEY] = REC_ID[:-1] + "0"
        self.rejected(docs)
        docs = source_docs()
        docs[1]["metadata"]["annotations"][APP_SHA_KEY] = OTHER_SHA
        self.rejected(docs)

    def test_registration_must_be_one_plain_path_entry(self):
        plain = "patches:\n  - path: release-source.yaml\n"
        self.assertEqual(source_registrations(plain), [{"path": SOURCE_FILE}])
        cases = {
            "not registered": "images: []\n",
            "registered twice": plain + "  - path: release-source.yaml\n",
            "with a target selector": "patches:\n  - target: {kind: Deployment}\n    path: release-source.yaml\n",
            "another file only": "patches:\n  - path: resources.yaml\n",
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                self.assertNotEqual(source_registrations(text), [{"path": SOURCE_FILE}])


class CandidateMatchChecks(unittest.TestCase):
    @staticmethod
    def good(env):
        if env == "recovery":
            return REC_ID, recovery_images()
        return CLD_ID, cloud_images()

    def test_matching_candidate_passes_for_both_environments(self):
        for env in ("recovery", "cloud"):
            release_id, images = self.good(env)
            with self.subTest(env=env):
                check_source_matches_candidate(env, SHA, release_id, images, {release_id: candidate()})

    def test_app_sha_mismatch_unknown_release_or_bad_sha_is_rejected(self):
        for env in ("recovery", "cloud"):
            release_id, images = self.good(env)
            cases = {
                "annotation SHA differs from the candidate": (OTHER_SHA, release_id, {release_id: candidate()}),
                "unknown release id": (SHA, release_id[:-1] + "0", {release_id: candidate()}),
                "no candidates": (SHA, release_id, {}),
                "short SHA": (SHA[:12], release_id, {release_id: candidate()}),
                "uppercase SHA": (SHA.upper(), release_id, {release_id: candidate()}),
            }
            for label, (app_sha, rid, candidates) in cases.items():
                with self.subTest(env=env, case=label):
                    with self.assertRaises(AssertionError):
                        check_source_matches_candidate(env, app_sha, rid, images, candidates)

    def test_digest_mismatch_is_rejected_for_either_component(self):
        other = "sha256:" + "9" * 64
        for env in ("recovery", "cloud"):
            release_id, _ = self.good(env)
            for component in COMPONENTS:
                digests = dict(OLD if env == "recovery" else ECR)
                digests[component] = other
                images = recovery_images(digests) if env == "recovery" else cloud_images(digests)
                with self.subTest(env=env, component=component):
                    with self.assertRaises(AssertionError):
                        check_source_matches_candidate(env, SHA, release_id, images, {release_id: candidate()})

    def test_placeholder_cross_registry_digest_or_wrong_registry_is_rejected(self):
        wrong_registry = recovery_images()
        wrong_registry["seokpan-backend"]["newName"] = "harbor.example.test/other/backend"
        cases = {
            "cloud overlay still INPUT_REQUIRED": ("cloud", CLD_ID, cloud_images({c: "INPUT_REQUIRED" for c in COMPONENTS})),
            "cloud overlay pins the Harbor digests": ("cloud", CLD_ID, cloud_images(OLD)),
            "recovery overlay pins the ECR digests": ("recovery", REC_ID, recovery_images(ECR)),
            "recovery newName is not the Harbor repository": ("recovery", REC_ID, wrong_registry),
        }
        for label, (env, release_id, images) in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(AssertionError):
                    check_source_matches_candidate(env, SHA, release_id, images, {release_id: candidate()})


class BuildDifferenceChecks(unittest.TestCase):
    def check(self, after, before=None):
        check_build_difference(after, rendered() if before is None else before, SHA, REC_ID)

    def test_only_the_two_annotations_pass(self):
        self.check(rendered(annotated=True))

    def test_pod_template_change_is_rejected(self):
        cases = {
            "image": lambda d: d[0]["spec"]["template"]["spec"]["containers"][0].update(image="y@" + ECR["backend"]),
            "template metadata": lambda d: d[1]["spec"]["template"].update(metadata={"labels": {"a": "b"}}),
            "replicas": lambda d: d[0]["spec"].update(replicas=2),
        }
        for label, mutate in cases.items():
            after = rendered(annotated=True)
            mutate(after)
            with self.subTest(case=label):
                with self.assertRaises(AssertionError):
                    self.check(after)

    def test_other_object_or_field_change_is_rejected(self):
        cases = {
            "ConfigMap data": lambda d: d[2]["data"].update(A="2"),
            "ConfigMap gets the annotations": lambda d: d[2]["metadata"].update(
                annotations={APP_SHA_KEY: SHA, RELEASE_ID_KEY: REC_ID}),
            "Deployment label": lambda d: d[0]["metadata"]["labels"].update(app="other"),
            "object removed": lambda d: d.pop(),
            "object added": lambda d: d.append({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "s"}}),
        }
        for label, mutate in cases.items():
            after = rendered(annotated=True)
            mutate(after)
            with self.subTest(case=label):
                with self.assertRaises(AssertionError):
                    self.check(after)

    def test_missing_or_wrong_annotation_is_rejected(self):
        cases = {
            "frontend has none": lambda d: d[1]["metadata"].pop("annotations"),
            "wrong App SHA": lambda d: d[0]["metadata"]["annotations"].update({APP_SHA_KEY: OTHER_SHA}),
            "wrong Release ID": lambda d: d[0]["metadata"]["annotations"].update({RELEASE_ID_KEY: REC_ID[:-1] + "0"}),
            "no annotations at all": lambda d: [doc["metadata"].pop("annotations") for doc in d[:2]],
        }
        for label, mutate in cases.items():
            after = rendered(annotated=True)
            mutate(after)
            with self.subTest(case=label):
                with self.assertRaises(AssertionError):
                    self.check(after)

    def test_existing_annotations_are_preserved(self):
        before = rendered()
        before[0]["metadata"]["annotations"] = {"example.test/keep": "1"}
        after = copy.deepcopy(before)
        for doc in after[:2]:
            doc["metadata"].setdefault("annotations", {}).update({APP_SHA_KEY: SHA, RELEASE_ID_KEY: REC_ID})
        self.check(after, before)
        after[0]["metadata"]["annotations"].pop("example.test/keep")
        with self.assertRaises(AssertionError):
            self.check(after, before)


if __name__ == "__main__":
    unittest.main()

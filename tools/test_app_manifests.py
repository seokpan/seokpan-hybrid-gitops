"""Exercise actual Kustomize and safety boundaries of the input-required source.

Requires kustomize v5.7.1 and PyYAML. No cluster or external service is contacted.
These tests are not an SCC, admission, image, connection or Recovery Run result.
"""

import copy
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

from render_release import recovery_manifest_blockers


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

    def backend_config(self, env):
        return next(r for r in self.by_kind(env, "ConfigMap")
                    if r["metadata"]["name"].startswith("backend-config-"))

    def workloads(self, env):
        return [r for r in self.renders[env] if r["kind"] in ("Deployment", "StatefulSet")]

    def test_builds_have_unique_objects_and_no_owned_secrets_or_namespace(self):
        forbidden = {"Secret", "Namespace", "Job", "CronJob", "Application",
                     "AppProject", "PersistentVolumeClaim"}
        for env, resources in self.renders.items():
            with self.subTest(env=env):
                keys = [(r["apiVersion"], r["kind"], r["metadata"].get("namespace"),
                         r["metadata"]["name"]) for r in resources]
                self.assertEqual(len(keys), len(set(keys)))
                self.assertFalse(forbidden & {r["kind"] for r in resources})
                statefulsets = self.by_kind(env, "StatefulSet")
                self.assertEqual([r["metadata"]["name"] for r in statefulsets],
                                 ["recovery-redis"] if env == "recovery" else [])

    def test_no_candidate_can_start_pods_with_missing_release_inputs(self):
        for env in self.renders:
            for dep in self.workloads(env):
                with self.subTest(env=env, app=dep["metadata"]["name"]):
                    self.assertEqual(dep["spec"]["replicas"], 0)
                    container = dep["spec"]["template"]["spec"]["containers"][0]
                    if env in {"lab", "recovery"} and dep["kind"] == "Deployment":
                        approved = {
                            "backend": "harbor.seokpan.soldesk.store/seokpan-hybrid/backend@sha256:cbb7452c28f1dfe3533358916e8d0432cd65aa10865842451ab026972b55dae6",
                            "frontend": "harbor.seokpan.soldesk.store/seokpan-hybrid/frontend@sha256:e9fb167a9afd753f5ca4ef1644efd9d0a310b82cc42d4331ebaa65bbf4bfa4d9",
                        }
                        if env == "lab":
                            approved = {name: image.replace(
                                "harbor.seokpan.soldesk.store/seokpan-hybrid/",
                                "image-registry.openshift-image-registry.svc:5000/seokpan-argotest/")
                                for name, image in approved.items()}
                        self.assertEqual(container["image"], approved[dep["metadata"]["name"]])
                    else:
                        self.assertIn("INPUT_REQUIRED", container["image"])
                    self.assertIn("input-required", dep["metadata"]["annotations"][
                        "seokpan.io/release-state"])

    def test_fixed_uid_gid_and_lab_dns_bypass_are_absent(self):
        for env in self.renders:
            for dep in self.workloads(env):
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
            data = self.backend_config(env)["data"]
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

    def test_runtime_config_change_changes_backend_pod_template_reference(self):
        # Render an isolated copy with the actual pinned tool. A ConfigMap
        # envFrom value change alone does not update a running process's env;
        # its generated name and consuming Pod template must change together.
        for env in ("lab", "recovery"):
            with self.subTest(env=env), tempfile.TemporaryDirectory() as directory:
                copied_apps = Path(directory) / "apps"
                shutil.copytree(ROOT / "apps", copied_apps)

                def render():
                    result = subprocess.run(
                        [KUSTOMIZE, "build", str(copied_apps / "overlays" / env)],
                        check=True, capture_output=True, text=True,
                    )
                    resources = list(yaml.safe_load_all(result.stdout))
                    config = next(r for r in resources if r["kind"] == "ConfigMap"
                                  and r["metadata"]["name"].startswith("backend-config-"))
                    deployments = {r["metadata"]["name"]: r for r in resources
                                   if r["kind"] == "Deployment"}
                    return config, deployments

                before_config, before_deployments = render()
                runtime_env = copied_apps / "overlays" / env / "runtime.env"
                old_host = before_config["data"]["SEOKPAN_DATABASE_EXPECTED_HOST"]
                new_host = env + "-db-new.example.test"
                runtime_env.write_text(runtime_env.read_text(encoding="utf-8").replace(
                    "SEOKPAN_DATABASE_EXPECTED_HOST=" + old_host,
                    "SEOKPAN_DATABASE_EXPECTED_HOST=" + new_host,
                ), encoding="utf-8")
                after_config, after_deployments = render()

                self.assertEqual(after_config["data"]["SEOKPAN_DATABASE_EXPECTED_HOST"],
                                 new_host)
                self.assertNotEqual(before_config["metadata"]["name"],
                                    after_config["metadata"]["name"])
                for config, deployments in ((before_config, before_deployments),
                                            (after_config, after_deployments)):
                    self.assertTrue(config["metadata"]["name"].startswith("backend-config-"))
                    pod = deployments["backend"]["spec"]["template"]["spec"]
                    self.assertEqual(pod["containers"][0]["envFrom"],
                                     [{"configMapRef": {"name": config["metadata"]["name"]}}])
                    self.assertEqual({v["configMap"]["name"] for v in pod["volumes"]
                                      if "configMap" in v},
                                     {"backend-database-ca", "backend-redis-ca"})
                self.assertNotEqual(before_deployments["backend"]["spec"]["template"],
                                    after_deployments["backend"]["spec"]["template"])
                self.assertEqual(before_deployments["frontend"],
                                 after_deployments["frontend"])

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

    def test_registry_pull_secret_references_are_explicit_and_environment_specific(self):
        for dep in self.by_kind("base", "Deployment"):
            self.assertNotIn("imagePullSecrets", dep["spec"]["template"]["spec"])
        for dep in self.workloads("lab"):
            spec = dep["spec"]["template"]["spec"]
            self.assertNotIn("imagePullSecrets", spec)
            for container in spec["containers"]:
                self.assertTrue(container["image"].startswith(
                    "image-registry.openshift-image-registry.svc:5000/seokpan-argotest/"))
        for dep in self.workloads("recovery"):
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
        config = self.backend_config("lab")["data"]
        origin, = json.loads(config["SEOKPAN_ALLOWED_ORIGINS"])
        host = urlsplit(origin).hostname
        routes = self.by_kind("lab", "Route")
        self.assertEqual(len(routes), 3)
        self.assertEqual({r["spec"]["host"] for r in routes}, {host})
        self.assertEqual({r["spec"].get("path", "/") for r in routes},
                         {"/", "/api/v1", "/ws/v1"})
        self.assertEqual(self.by_kind("recovery", "Route"), [])
        self.assertEqual(self.by_kind("recovery", "Ingress"), [])
        recovery = self.backend_config("recovery")["data"]
        self.assertIn("recovery-direct-db", recovery["SEOKPAN_DATABASE_EXPECTED_HOST"])
        self.assertEqual(recovery["SEOKPAN_REDIS_EXPECTED_HOST"],
                         "recovery-redis.recovery-input-required.svc")

    def test_recovery_redis_source_is_held_isolated_and_uses_external_tls_auth(self):
        redis, = self.by_kind("recovery", "StatefulSet")
        pod = redis["spec"]["template"]["spec"]
        container, = pod["containers"]
        self.assertEqual(redis["spec"]["replicas"], 0)
        self.assertEqual(container["command"], ["redis-server"])
        self.assertEqual(container["args"], ["/etc/seokpan/redis/redis.conf"])
        self.assertNotIn("env", container)
        self.assertNotIn("volumeClaimTemplates", redis["spec"])
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertIn("input-required", volumes["runtime-data"]["persistentVolumeClaim"]["claimName"])
        self.assertIn("input-required", volumes["runtime-config"]["configMap"]["name"])
        for name in ("server-tls", "server-auth"):
            self.assertFalse(volumes[name]["secret"].get("optional", False))
            self.assertTrue(next(m for m in container["volumeMounts"] if m["name"] == name)["readOnly"])
        service = next(r for r in self.by_kind("recovery", "Service")
                       if r["metadata"]["name"] == "recovery-redis")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(service["spec"]["clusterIP"], "None")
        self.assertEqual(service["spec"]["ports"][0]["port"], 6379)
        config = next(r["data"]["redis.conf"] for r in self.by_kind("recovery", "ConfigMap")
                      if r["metadata"]["name"].startswith("recovery-redis-config-"))
        self.assertIn("\nport 0\n", config)
        self.assertIn("\ntls-port 6379\n", config)
        self.assertIn("\ntls-auth-clients no\n", config)
        for directive in ("requirepass ", "aclfile ", "user ", "appendonly ", "maxmemory "):
            self.assertFalse(any(line.startswith(directive) for line in config.splitlines()))

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
            manifest = yaml.safe_dump_all([
                {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": name},
                 "spec": {"replicas": 1, "template": {"spec": {"containers": [{
                     "name": name, "image": "harbor.fixture.test/" + name + "@sha256:" + "a" * 64}]}}}}
                for name in ("backend", "frontend")])
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


class RecoveryReleaseBoundaries(unittest.TestCase):
    """Controlled manifest fixtures exercise semantics without faking a Build.

    Actual Kustomize composition and hash/name transformations are exercised by
    AppManifestBoundaries above. Fixture inputs are declarations, not real
    Image/Secret/CA/storage or independently reviewed Runtime acceptance.
    """

    namespace = "isolated-recovery"
    registry = "harbor.recovery.test"

    def fixture(self):
        resources = []
        for path in ("apps/base/backend.yaml", "apps/base/frontend.yaml",
                     "apps/base/services.yaml", "apps/overlays/recovery/redis.yaml"):
            resources.extend(yaml.safe_load_all((ROOT / path).read_text(encoding="utf-8")))
        config = {}
        for path in ("apps/base/runtime.env", "apps/overlays/recovery/runtime.env"):
            for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
                if line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    config[key] = value
        config.update({
            "SEOKPAN_REDIS_URL": f"rediss://recovery-redis.{self.namespace}.svc:6379/0",
            "SEOKPAN_REDIS_EXPECTED_HOST": f"recovery-redis.{self.namespace}.svc",
            "SEOKPAN_ALLOWED_ORIGINS": '["https://recovery.example.test"]',
            "SEOKPAN_DATABASE_EXPECTED_HOST": "isolated-db.recovery.test",
            "SEOKPAN_DATABASE_EXPECTED_NAME": "reviewed_db",
        })
        resources.extend([
            {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "backend-config"},
             "data": config},
            {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "recovery-redis-config"},
             "data": {"redis.conf": (ROOT / "apps/overlays/recovery/redis.conf").read_text(encoding="utf-8")}},
        ])
        for r in resources:
            r["metadata"]["namespace"] = self.namespace
            if r["kind"] in ("Deployment", "StatefulSet"):
                r["metadata"]["annotations"]["seokpan.io/release-state"] = "source-reviewed-runtime-unverified"
                r["spec"]["replicas"] = 1
                pod = r["spec"]["template"]["spec"]
                pod["imagePullSecrets"] = [{"name": "recovery-harbor-pull"}]
                for c in pod["containers"]:
                    c["image"] = f"{self.registry}/{c['name']}@sha256:" + "a" * 64
                if r["kind"] == "StatefulSet":
                    self.volume(r, "runtime-data")["persistentVolumeClaim"]["claimName"] = "reviewed-isolated-volume"
                    self.volume(r, "runtime-config")["configMap"]["name"] = "reviewed-redis-runtime"
        return resources

    @staticmethod
    def resource(resources, kind, name):
        return next(r for r in resources if r["kind"] == kind and r["metadata"]["name"] == name)

    @staticmethod
    def volume(workload, name):
        return next(v for v in workload["spec"]["template"]["spec"]["volumes"] if v["name"] == name)

    @staticmethod
    def mount(workload, name):
        return next(m for m in workload["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
                    if m["name"] == name)

    def blockers(self, resources, namespace=None, registry=None):
        return recovery_manifest_blockers(yaml.safe_dump_all(resources),
                                          namespace or self.namespace, registry or self.registry)

    def test_reviewed_source_keeps_storage_technology_an_owner_choice(self):
        resources = self.fixture()
        self.assertEqual(self.blockers(resources), [])
        redis = self.resource(resources, "StatefulSet", "recovery-redis")
        volume = self.volume(redis, "runtime-data")
        volume.pop("persistentVolumeClaim")
        volume["emptyDir"] = {}
        self.assertEqual(self.blockers(resources), [])
        # These are Source interfaces; neither variant proves empty data or UID
        # write permission, and no final persistence policy is selected here.

    def test_redis_directive_names_follow_case_insensitive_allowlist_without_overrides(self):
        resources = self.fixture()
        data = self.resource(resources, "ConfigMap", "recovery-redis-config")["data"]
        # Redis accepts uppercase names. A valid case-only edit remains valid;
        # an added override must not evade duplicate or transport restrictions.
        original = data["redis.conf"]
        data["redis.conf"] = "\n".join(
            line.split(maxsplit=1)[0].upper() + " " + line.split(maxsplit=1)[1]
            if line.strip() and not line.lstrip().startswith("#") else line
            for line in original.splitlines()
        )
        self.assertEqual(self.blockers(resources), [])
        for appended in (
                "PORT 6379", "REQUIREPASS SYNTHETIC_REVIEW_ONLY",
                "REPLICAOF cloud-example.test 6379", "PrOtEcTeD-MoDe no",
                "TLS-PORT 6380", "port 0"):
            with self.subTest(directive=appended.split()[0]):
                data["redis.conf"] = original + "\n" + appended + "\n"
                self.assertTrue(self.blockers(resources))

    def test_backend_effective_configuration_cannot_override_reviewed_targets(self):
        def container(rs):
            return self.resource(rs, "Deployment", "backend")["spec"]["template"]["spec"]["containers"][0]

        mutations = [
            ("extra envFrom", lambda rs: container(rs)["envFrom"].append({"configMapRef": {"name": "unreviewed-cloud-overrides"}})),
            ("prefixed envFrom", lambda rs: container(rs)["envFrom"][0].update(prefix="OTHER_")),
            ("optional config", lambda rs: container(rs)["envFrom"][0]["configMapRef"].update(optional=True)),
            ("secret envFrom", lambda rs: container(rs).update(envFrom=[{"secretRef": {"name": "unreviewed-targets"}}])),
            ("duplicate AUTH", lambda rs: container(rs)["env"].append({"name": "SEOKPAN_REDIS_AUTH_TOKEN", "valueFrom": {"secretKeyRef": {"name": "wrong-secret", "key": "SEOKPAN_REDIS_AUTH_TOKEN"}}})),
        ]
        # Kubernetes explicit env wins over envFrom, including valueFrom. Test
        # every generated key so checking the first ConfigMap cannot disguise
        # a different effective host, profile, CA path or TLS connection value.
        config_keys = self.resource(self.fixture(), "ConfigMap", "backend-config")["data"]
        for key in config_keys:
            mutations.append(("explicit " + key, lambda rs, key=key: container(rs)["env"].append({
                "name": key, "value": "UNREVIEWED_OVERRIDE"})))
        mutations.append(("valueFrom override", lambda rs: container(rs)["env"].append({
            "name": "SEOKPAN_REDIS_URL", "valueFrom": {"configMapKeyRef": {"name": "unreviewed", "key": "url"}}})))
        for label, mutate in mutations:
            with self.subTest(boundary=label):
                resources = self.fixture()
                mutate(resources)
                self.assertTrue(self.blockers(resources))

    def test_wrong_namespace_redis_target_or_managed_owner_objects_are_withheld(self):
        def wrong_host(resources):
            data = self.resource(resources, "ConfigMap", "backend-config")["data"]
            data["SEOKPAN_REDIS_URL"] = "rediss://cloud-redis.example.test:6379/0"
            data["SEOKPAN_REDIS_EXPECTED_HOST"] = "cloud-redis.example.test"

        mutations = [
            ("wrong namespace", lambda rs: rs[0]["metadata"].update(namespace="shared-app")),
            ("wrong Redis target", wrong_host),
            ("old Redis identity", lambda rs: self.resource(rs, "StatefulSet", "recovery-redis")["metadata"].update(name="first-redis")),
            ("wrong selector", lambda rs: self.resource(rs, "Service", "recovery-redis")["spec"].update(selector={"app": "first-redis"})),
            ("external Service", lambda rs: self.resource(rs, "Service", "recovery-redis")["spec"].update(type="LoadBalancer")),
            ("zero Redis hold", lambda rs: self.resource(rs, "StatefulSet", "recovery-redis")["spec"].update(replicas=0)),
            ("owned PVC template", lambda rs: self.resource(rs, "StatefulSet", "recovery-redis")["spec"].update(volumeClaimTemplates=[])),
            ("duplicated object", lambda rs: rs.append(copy.deepcopy(rs[0]))),
        ]
        for kind in ("Namespace", "Secret", "PersistentVolumeClaim", "Application"):
            mutations.append(("managed " + kind, lambda rs, kind=kind: rs.append({
                "apiVersion": "v1", "kind": kind,
                "metadata": {"name": "not-owned", "namespace": self.namespace}})))
        for label, mutate in mutations:
            with self.subTest(boundary=label):
                resources = self.fixture()
                mutate(resources)
                self.assertTrue(self.blockers(resources))

    def test_plaintext_auth_ca_or_image_boundary_changes_are_withheld(self):
        def backend(rs):
            return self.resource(rs, "Deployment", "backend")

        def redis(rs):
            return self.resource(rs, "StatefulSet", "recovery-redis")

        def redis_container(rs):
            return redis(rs)["spec"]["template"]["spec"]["containers"][0]

        def alter_config(rs, old, new):
            data = self.resource(rs, "ConfigMap", "recovery-redis-config")["data"]
            data["redis.conf"] = data["redis.conf"].replace(old, new)

        def move_auth_include_after_tls(rs):
            data = self.resource(rs, "ConfigMap", "recovery-redis-config")["data"]
            include = "include /etc/seokpan/redis-server-auth/redis-auth.conf"
            data["redis.conf"] = data["redis.conf"].replace(include, "# moved") + "\n" + include + "\n"

        def wrong_backend_auth(rs):
            c = backend(rs)["spec"]["template"]["spec"]["containers"][0]
            auth = next(e for e in c["env"] if e["name"] == "SEOKPAN_REDIS_AUTH_TOKEN")
            auth["valueFrom"]["secretKeyRef"]["name"] = "first-redis-auth"

        mutations = [
            ("plaintext port", lambda rs: alter_config(rs, "\nport 0\n", "\nport 6379\n")),
            ("missing AUTH include", lambda rs: alter_config(rs, "include /etc/seokpan/redis-server-auth/redis-auth.conf", "# removed")),
            ("owner include after TLS", move_auth_include_after_tls),
            ("inline public AUTH", lambda rs: alter_config(rs, "\nport 0\n", "\nrequirepass UNREVIEWED_LITERAL\nport 0\n")),
            ("unexpected include", lambda rs: alter_config(rs, "\nport 0\n", "\ninclude /unreviewed.conf\nport 0\n")),
            ("mTLS mismatch", lambda rs: alter_config(rs, "tls-auth-clients no", "tls-auth-clients yes")),
            ("wrong TLS Secret", lambda rs: self.volume(redis(rs), "server-tls")["secret"].update(secretName="first-redis-tls")),
            ("wrong AUTH Secret", lambda rs: self.volume(redis(rs), "server-auth")["secret"].update(secretName="first-redis-auth")),
            ("missing TLS key", lambda rs: self.volume(redis(rs), "server-tls")["secret"].update(items=[])),
            ("writable AUTH mount", lambda rs: self.mount(redis(rs), "server-auth").update(readOnly=False)),
            ("AUTH argv", lambda rs: redis_container(rs).update(args=["--requirepass", "UNREVIEWED_LITERAL"])),
            ("Backend public AUTH", lambda rs: self.resource(rs, "ConfigMap", "backend-config")["data"].update(SEOKPAN_REDIS_AUTH_TOKEN="UNREVIEWED_LITERAL")),
            ("wrong Backend AUTH", wrong_backend_auth),
            ("wrong Backend CA name", lambda rs: self.volume(backend(rs), "redis-ca")["configMap"].update(name="first-redis-ca")),
            ("wrong Backend CA item", lambda rs: self.volume(backend(rs), "redis-ca")["configMap"].update(items=[{"key": "other.crt", "path": "ca.crt"}])),
            ("wrong Backend CA mount", lambda rs: self.mount(backend(rs), "redis-ca").update(mountPath="/wrong")),
            ("writable Backend CA", lambda rs: self.mount(backend(rs), "redis-ca").update(readOnly=False)),
            ("missing Backend CA file", lambda rs: self.resource(rs, "ConfigMap", "backend-config")["data"].update(SEOKPAN_REDIS_CA_FILE="/wrong/ca.crt")),
            ("mutable local image", lambda rs: redis_container(rs).update(image=self.registry + "/redis:latest")),
            ("outside local Harbor", lambda rs: redis_container(rs).update(image="public.example.test/redis@sha256:" + "a" * 64)),
            ("fixed UID", lambda rs: redis_container(rs)["securityContext"].update(runAsUser=1000)),
        ]
        for label, mutate in mutations:
            with self.subTest(boundary=label):
                resources = self.fixture()
                mutate(resources)
                self.assertTrue(self.blockers(resources))
        self.assertTrue(recovery_manifest_blockers("not: [valid", self.namespace, self.registry))
        self.assertTrue(recovery_manifest_blockers("kind: Deployment\nmetadata: not-a-mapping\n", self.namespace, self.registry))
        self.assertTrue(recovery_manifest_blockers(yaml.safe_dump_all(self.fixture()), None, self.registry))
        self.assertTrue(recovery_manifest_blockers(yaml.safe_dump_all(self.fixture()), self.namespace, None))

    def test_recovery_cli_requires_independent_inputs_and_preserves_previous_output(self):
        # This controlled tool response isolates the Recovery CLI semantic gate.
        # It is not the actual overlay Build or any external input acceptance.
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            fixture = directory / "kustomize-fixture"
            manifest = yaml.safe_dump_all(self.fixture())
            fixture.write_text(
                "#!" + sys.executable + "\nimport sys\n"
                "print('v5.7.1' if sys.argv[1] == 'version' else " + repr(manifest) + ", end='' if sys.argv[1] != 'version' else '\\n')\n",
                encoding="utf-8",
            )
            fixture.chmod(0o755)
            output = directory / "new.yaml"

            def render(reviewed_inputs):
                return subprocess.run(
                    [sys.executable, str(ROOT / "tools/render_release.py"), "recovery",
                     "--output", str(output), "--kustomize", str(fixture), *reviewed_inputs],
                    capture_output=True, text=True,
                    env={key: value for key, value in os.environ.items()
                         if key not in ("RECOVERY_NAMESPACE", "RECOVERY_REGISTRY")},
                )

            self.assertEqual(render([]).returncode, 2)
            self.assertFalse(output.exists())
            reviewed = ["--recovery-namespace", self.namespace, "--recovery-registry", self.registry]
            self.assertEqual(render(reviewed).returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), manifest)
            output.write_text("preserved reviewed artifact", encoding="utf-8")
            self.assertEqual(render(reviewed).returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserved reviewed artifact")


if __name__ == "__main__":
    unittest.main()

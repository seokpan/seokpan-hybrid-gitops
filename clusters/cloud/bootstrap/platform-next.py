"""Configure the held Cloud namespace after project registration; never start an app."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

NS = 'seokpan-cloud'
ARGO = 'openshift-gitops'
ROLE = 'seokpan-cloud-application-controller'
WRITES = [('apps', 'deployments'), ('', 'services'), ('', 'configmaps'),
          ('route.openshift.io', 'routes'), ('policy', 'poddisruptionbudgets')]
READS = [('', 'pods'), ('apps', 'replicasets'), ('', 'events'),
         ('', 'endpoints'), ('discovery.k8s.io', 'endpointslices')]
WRITE_VERBS = ['get', 'list', 'watch', 'create', 'update', 'patch']
READ_VERBS = ['get', 'list', 'watch']


class Stop(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Stop(reason)


def controller_role(sa):
    require(sa == 'openshift-gitops-argocd-application-controller', 'CONTROLLER_SA_CHANGED')
    metadata = {'name': ROLE, 'namespace': NS,
                'annotations': {'seokpan.io/bootstrap-owner': 'cloud-platform'}}
    role = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'Role',
            'metadata': metadata, 'rules': [
                {'apiGroups': [g], 'resources': [r], 'verbs': WRITE_VERBS}
                for g, r in WRITES] + [
                {'apiGroups': [g], 'resources': [r], 'verbs': READ_VERBS}
                for g, r in READS] + [{'apiGroups': ['route.openshift.io'],
                'resources': ['routes/custom-host'], 'verbs': ['create']}]}
    binding = {'apiVersion': role['apiVersion'], 'kind': 'RoleBinding',
               'metadata': metadata, 'roleRef': {'apiGroup': 'rbac.authorization.k8s.io',
               'kind': 'Role', 'name': ROLE},
               'subjects': [{'kind': 'ServiceAccount', 'name': sa, 'namespace': ARGO}]}
    return [role, binding]


def ingress_policies(router):
    require(router.get('namespace') == 'openshift-ingress' and
            router.get('host_network') is False and router.get('pod_labels') == {
                'ingresscontroller.operator.openshift.io/deployment-ingresscontroller': 'default'},
            'OBSERVED_ROUTER_CONTRACT_CHANGED')
    peer = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': router['namespace']}},
            'podSelector': {'matchLabels': router['pod_labels']}}
    def policy(name, spec):
        return {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
                'metadata': {'name': name, 'namespace': NS,
                             'annotations': {'seokpan.io/bootstrap-owner': 'cloud-platform'}},
                'spec': spec}
    result = []
    for name, port in [('frontend', 8080), ('backend', 8000)]:
        result.append(policy('seokpan-router-to-' + name, {
            'podSelector': {'matchLabels': {'app.kubernetes.io/name': name}},
            'policyTypes': ['Ingress'], 'ingress': [{'from': [peer],
                'ports': [{'protocol': 'TCP', 'port': port}]}]}))
    result.append(policy('seokpan-frontend-to-backend', {
        'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'backend'}},
        'policyTypes': ['Ingress'], 'ingress': [{'from': [{'podSelector': {
            'matchLabels': {'app.kubernetes.io/name': 'frontend'}}}],
            'ports': [{'protocol': 'TCP', 'port': 8000}]}]}))
    # Create the allows before the default deny. Partial failure never starts an app.
    result.append(policy('seokpan-deny-ingress', {
        'podSelector': {}, 'policyTypes': ['Ingress'], 'ingress': []}))
    return result


def same_object(candidate, existing):
    if candidate['kind'] == 'Role':
        return candidate['rules'] == existing.get('rules')
    if candidate['kind'] == 'RoleBinding':
        subjects = [{**s, 'apiGroup': s.get('apiGroup', '')} for s in existing.get('subjects', [])]
        wanted = [{**s, 'apiGroup': s.get('apiGroup', '')} for s in candidate['subjects']]
        return candidate['roleRef'] == existing.get('roleRef') and wanted == subjects
    def policy_spec(spec):
        spec = dict(spec or {})
        # Kubernetes omits empty rule lists when returning NetworkPolicy JSON.
        for field in ('ingress', 'egress'):
            if spec.get(field) == []:
                spec.pop(field)
        return spec
    return policy_spec(candidate['spec']) == policy_spec(existing.get('spec'))


class Runner:
    def __init__(self, folder):
        self.folder = folder
        self.count = 0
        self.created = []

    def save(self, name, value):
        (self.folder / name).write_text(json.dumps(value, indent=2) + '\n')

    def oc(self, args, *, optional=False):
        self.count += 1
        result = subprocess.run(['oc', *args, '--request-timeout=25s'],
                                capture_output=True, text=True, timeout=45)
        stem = f'{self.count:03d}'
        (self.folder / (stem + '.stdout')).write_text(result.stdout)
        (self.folder / (stem + '.stderr')).write_text(result.stderr)
        require(result.returncode == 0, 'OC_COMMAND_FAILED_PRIVATE_LOG_' + stem)
        if optional and not result.stdout.strip():
            return None
        return json.loads(result.stdout)

    def get(self, kind, name=None, namespace=NS, optional=False):
        args = ['get', kind, *([name] if name else []), '-n', namespace, '-o', 'json']
        if optional:
            args.append('--ignore-not-found=true')
        return self.oc(args, optional=optional)

    def can(self, sa, verb, resource):
        self.count += 1
        parts = resource.split('/', 1)
        args = ['oc', 'auth', 'can-i', verb, parts[0], '-n', NS,
                '--as=system:serviceaccount:' + ARGO + ':' + sa,
                '--as-group=system:serviceaccounts',
                '--as-group=system:serviceaccounts:' + ARGO,
                '--as-group=system:authenticated', '--request-timeout=25s']
        if len(parts) == 2:
            args.append('--subresource=' + parts[1])
        result = subprocess.run(args, capture_output=True, text=True, timeout=45)
        (self.folder / f'{self.count:03d}.auth.stderr').write_text(result.stderr)
        value = result.stdout.strip()
        require((result.returncode, value) in [(0, 'yes'), (1, 'no')],
                'IMPERSONATED_AUTHORIZATION_QUERY_FAILED')
        return value == 'yes'


def main():
    import pwd  # Controller only; pure declaration/auth tests also run on Windows.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('project_result', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    runner = None
    phase = 'LOCAL_ACCEPTED_PROJECT'
    try:
        require(pwd.getpwuid(os.getuid()).pw_name == 'jth', 'USE_JTH_CONTROLLER')
        root, previous = args.root.resolve(strict=True), args.project_result.resolve(strict=True)
        require(previous.parent == root and previous.name.startswith('cloud-project-registration-'),
                'EXISTING_PROJECT_RESULT_REQUIRED')
        accepted = json.loads((previous / 'receipt.json').read_text())
        require(accepted.get('status') == 'PASS_CLOUD_PROJECT_REGISTERED_PLATFORM_INPUTS_COLLECTED'
                and accepted.get('project') == 'seokpan-cloud-app' and accepted.get('namespace') == NS,
                'PROJECT_REGISTRATION_NOT_ACCEPTED')
        require(len(accepted['router']) == 1 and len(accepted['controller']) == 1,
                'UNIQUE_OBSERVED_ROUTER_AND_CONTROLLER_REQUIRED')
        controller = accepted['controller'][0]
        require(controller == {'kind': 'StatefulSet', 'name': 'openshift-gitops-application-controller',
                               'service_account': 'openshift-gitops-argocd-application-controller'},
                'OBSERVED_CONTROLLER_CHANGED')
        policies = ingress_policies(accepted['router'][0])
        sa = controller['service_account']
        marker = previous / 'platform-next-attempt.json'
        require(not marker.exists() and not marker.is_symlink(), 'PREVIOUS_PLATFORM_APPLY_ATTEMPT_REVIEW_REQUIRED')
        folder = Path(tempfile.mkdtemp(prefix='cloud-platform-next-', dir=root))
        runner = Runner(folder)
        handoffs = [json.loads(p.read_text()) for p in root.glob('management/*/data-platform-handoff.json')]
        handoffs = [h for h in handoffs if h.get('binding_enabled') is True]
        require(len(handoffs) == 1, 'UNIQUE_BOUND_CLUSTER_REQUIRED')
        result = subprocess.run(['oc', 'whoami', '--show-server', '--request-timeout=20s'],
                                capture_output=True, text=True, timeout=35)
        require(result.returncode == 0 and result.stdout.strip().rstrip('/') == handoffs[0]['api_url'].rstrip('/'),
                'CURRENT_CLUSTER_MISMATCH_OR_SESSION_EXPIRED')

        phase = 'CURRENT_PLATFORM_AND_HELD_WORKLOAD_GUARDS'
        router = runner.get('deployment', 'router-default', namespace='openshift-ingress')
        require(router['spec']['selector']['matchLabels'] == accepted['router'][0]['pod_labels'] and
                router['spec']['template']['spec'].get('hostNetwork', False) is False and
                router.get('status', {}).get('readyReplicas', 0) > 0, 'CURRENT_ROUTER_CHANGED_OR_UNAVAILABLE')
        current_controller = runner.get('statefulset', controller['name'], namespace=ARGO)
        require(current_controller['spec']['template']['spec']['serviceAccountName'] == sa,
                'CURRENT_CONTROLLER_SA_CHANGED')
        deployments = runner.get('deployments')
        require(all(d.get('spec', {}).get('replicas', 1) == 0 for d in deployments['items']),
                'ACTIVE_DEPLOYMENT_REQUIRES_TRAFFIC_REVIEW')
        existing_policies = runner.get('networkpolicies')['items']
        require(all(p['metadata']['name'] in {c['metadata']['name'] for c in policies}
                    for p in existing_policies), 'OTHER_INGRESS_POLICIES_REQUIRE_COMBINED_REVIEW')

        phase = 'CONTROLLER_NAMESPACE_AUTHORIZATION'
        checks = [(v, r + ('.' + g if g else ''))
                  for g, r in WRITES + READS for v in (WRITE_VERBS if (g, r) in WRITES else READ_VERBS)]
        checks.append(('create', 'routes.route.openshift.io/custom-host'))
        missing = [(v, r) for v, r in checks if not runner.can(sa, v, r)]
        objects = (controller_role(sa) if missing else []) + policies
        new = []
        for obj in objects:
            old = runner.get(obj['kind'], obj['metadata']['name'], optional=True)
            if old:
                metadata = old.get('metadata', {})
                require(not metadata.get('ownerReferences') and
                        not metadata.get('annotations', {}).get('argocd.argoproj.io/tracking-id') and
                        not metadata.get('labels', {}).get('argocd.argoproj.io/instance'),
                        'EXISTING_OBJECT_HAS_OTHER_OWNER')
                require(same_object(obj, old), 'EXISTING_PLATFORM_OBJECT_SCOPE_CONFLICT')
            else:
                new.append(obj)
        runner.save('candidates.json', {'apiVersion': 'v1', 'kind': 'List', 'items': objects})
        phase = 'ALL_NEW_OBJECT_SERVER_ADMISSION'
        for index, obj in enumerate(new):
            name = f'new-{index}.json'
            runner.save(name, obj)
            runner.oc(['create', '--dry-run=server', '-f', str(folder / name), '-o', 'json'])
        if not args.apply:
            print(json.dumps({'status': 'PASS_PLATFORM_PREFLIGHT_ONLY', 'new_objects': len(new),
                              'missing_controller_permissions': len(missing), 'mutations': 0}))
            return 0
        require(all(d.get('spec', {}).get('replicas', 1) == 0
                    for d in runner.get('deployments')['items']),
                'DEPLOYMENT_ACTIVATED_DURING_PREFLIGHT')
        if new:
            with marker.open('x') as stream:
                json.dump({'result_directory': str(folder), 'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}, stream)
        phase = 'CREATE_REVIEWED_NAMESPACE_OBJECTS'
        for index, obj in enumerate(new):
            runner.oc(['create', '-f', str(folder / f'new-{index}.json'), '-o', 'json'])
            runner.created.append({'kind': obj['kind'], 'name': obj['metadata']['name']})
            runner.save('created.json', runner.created)
        phase = 'CONFIRM_NAMESPACE_CONFIGURATION'
        for obj in objects:
            require(same_object(obj, runner.get(obj['kind'], obj['metadata']['name'])),
                    'CREATED_OBJECT_SCOPE_NOT_CONFIRMED')
        for verb, resource in missing:
            for attempt in range(4):
                if runner.can(sa, verb, resource):
                    break
                time.sleep(1)
            else:
                raise Stop('CONTROLLER_AUTHORIZATION_NOT_CONFIRMED')
        extras = {r + ':' + v: runner.can(sa, v, r) for v, r in
                  [('get', 'secrets'), ('create', 'pods'), ('create', 'rolebindings'), ('delete', 'deployments.apps')]}
        receipt = {'status': 'PASS_CLOUD_INGRESS_AND_CONTROLLER_NAMESPACE_CONFIGURATION',
                   'namespace': NS, 'created': runner.created, 'ingress_policies': 4,
                   'controller_required_checks': len(checks), 'controller_required_permissions': 'PASS',
                   'preexisting_or_external_extra_controller_permissions': extras,
                   'new_role_allows_secret_pod_rbac_or_delete': False,
                   'ingress_actual_allow_deny_traffic': 'NOT_TESTED', 'egress_policy': 'NOT_CONFIGURED',
                   'application_created': False, 'sync_started': False, 'database_writes': 0,
                   'completed_tests_repeated': False, 'personal_argo_browser_acceptance': 'NOT_RECEIVED',
                   'oc_commands': runner.count}
        runner.save('receipt.json', receipt)
        print(json.dumps(receipt), flush=True)
        return 0
    except (Stop, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        receipt = {'status': 'STOP_CLOUD_PLATFORM_NEXT', 'phase': phase,
                   'reason': str(exc) if isinstance(exc, Stop) else type(exc).__name__,
                   'created': runner.created if runner else [], 'automatic_mutation_retry': False,
                   'application_started': False, 'raw_output': 'PRIVATE_NOT_PRINTED'}
        if runner:
            runner.save('receipt.json', receipt)
        print(json.dumps(receipt), flush=True)
        return 1
    finally:
        if runner:
            print('Private Cloud platform result directory: ' + str(runner.folder), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())


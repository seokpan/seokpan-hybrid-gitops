"""Add only the missing Cloud Route custom-host permission; never rerun platform setup."""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('cloud_platform', Path(__file__).with_name('platform-next.py'))
platform = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platform)
SA = 'openshift-gitops-argocd-application-controller'
API = 'https://api.seokpan-cloud.8zrv.p1.openshiftapps.com:6443'
CUSTOM = {'apiGroups': ['route.openshift.io'], 'resources': ['routes/custom-host'], 'verbs': ['create']}


def require(ok, reason):
    platform.require(ok, reason)


def validate_owner(obj):
    meta = obj.get('metadata', {})
    require(meta.get('namespace') == platform.NS and meta.get('name') == platform.ROLE,
            'TARGET_ROLE_OR_BINDING_CHANGED')
    require(meta.get('annotations', {}).get('seokpan.io/bootstrap-owner') == 'cloud-platform'
            and not meta.get('ownerReferences')
            and not meta.get('annotations', {}).get('argocd.argoproj.io/tracking-id')
            and not meta.get('labels', {}).get('argocd.argoproj.io/instance'),
            'PLATFORM_OBJECT_OWNERSHIP_CHANGED')
    require(not meta.get('deletionTimestamp'), 'PLATFORM_OBJECT_DELETING')


def make_patch(role):
    validate_owner(role)
    expected = platform.controller_role(SA)[0]['rules']
    require(expected[-1] == CUSTOM, 'REPAIR_SOURCE_CONTRACT_CHANGED')
    if role.get('rules') == expected:
        return []
    require(role.get('rules') == expected[:-1], 'EXISTING_ROLE_HAS_UNEXPECTED_SCOPE')
    meta = role['metadata']
    require(bool(meta.get('uid')) and bool(meta.get('resourceVersion')), 'ROLE_IDENTITY_REQUIRED')
    return [
        {'op': 'test', 'path': '/metadata/uid', 'value': meta['uid']},
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': meta['resourceVersion']},
        {'op': 'test', 'path': '/rules', 'value': role['rules']},
        {'op': 'add', 'path': '/rules/-', 'value': CUSTOM},
    ]


def validate_binding(binding):
    validate_owner(binding)
    require(platform.same_object(platform.controller_role(SA)[1], binding),
            'CONTROLLER_ROLE_BINDING_CHANGED')


def run(root, apply):
    import pwd
    require(pwd.getpwuid(os.getuid()).pw_name == 'jth', 'USE_JTH_CONTROLLER')
    root = root.resolve(strict=True)
    folder = Path(tempfile.mkdtemp(prefix='cloud-route-custom-host-', dir=root))
    runner = platform.Runner(folder)
    attempted = False
    try:
        result = subprocess.run(['oc', 'whoami', '--show-server', '--request-timeout=20s'],
                                capture_output=True, text=True, timeout=35)
        require(result.returncode == 0 and result.stdout.strip().rstrip('/') == API,
                'CURRENT_CLUSTER_MISMATCH_OR_SESSION_EXPIRED')
        controller = runner.get('statefulset', 'openshift-gitops-application-controller',
                                namespace=platform.ARGO)
        require(controller['spec']['template']['spec']['serviceAccountName'] == SA,
                'CONTROLLER_SERVICE_ACCOUNT_CHANGED')
        role = runner.get('role', platform.ROLE)
        binding = runner.get('rolebinding', platform.ROLE)
        validate_binding(binding)
        patch = make_patch(role)
        if patch:
            runner.save('patch.json', patch)
            marker = root / 'cloud-route-custom-host-attempt.json'
            require(not marker.exists() and not marker.is_symlink(),
                    'PREVIOUS_PATCH_ATTEMPT_REQUIRES_RESULT_REVIEW')
            runner.oc(['patch', 'role', platform.ROLE, '-n', platform.NS,
                       '--type=json', '-p', json.dumps(patch),
                       '--dry-run=server', '-o', 'json'])
            if not apply:
                receipt = {'status': 'PASS_CUSTOM_HOST_PATCH_PREFLIGHT', 'role_patches': 0}
                runner.save('receipt.json', receipt)
                print(json.dumps(receipt))
                return 0
            with marker.open('x') as stream:
                json.dump({'result_directory': str(folder), 'role_uid': role['metadata']['uid'],
                           'started_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}, stream)
            attempted = True
            runner.oc(['patch', 'role', platform.ROLE, '-n', platform.NS,
                       '--type=json', '-p', json.dumps(patch), '-o', 'json'])
        accepted = runner.get('role', platform.ROLE)
        require(make_patch(accepted) == [], 'CUSTOM_HOST_ROLE_NOT_CONFIRMED')
        require(accepted['metadata']['uid'] == role['metadata']['uid'], 'ROLE_REPLACED')
        validate_binding(runner.get('rolebinding', platform.ROLE))
        allowed = runner.can(SA, 'create', 'routes.route.openshift.io/custom-host')
        require(allowed, 'CUSTOM_HOST_AUTHORIZATION_NOT_YET_CONFIRMED_NO_RETRY')
        receipt = {'status': 'PASS_CLOUD_ROUTE_CUSTOM_HOST', 'namespace': platform.NS,
                   'role_patches': int(attempted), 'added_rule': CUSTOM,
                   'route_custom_host_allowed': True, 'controller_45_checks_repeated': False,
                   'ingress_apply_repeated': False, 'operator_clusterrole_changes': 0,
                   'application_started': False, 'sync_started': False, 'database_writes': 0}
        runner.save('receipt.json', receipt)
        print(json.dumps(receipt))
        return 0
    except (platform.Stop, OSError, KeyError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        receipt = {'status': 'STOP_CLOUD_CUSTOM_HOST', 'reason': str(exc) if isinstance(exc, platform.Stop)
                   else type(exc).__name__, 'role_patch_attempted': attempted,
                   'automatic_retry': False, 'application_started': False, 'raw_output': 'PRIVATE_NOT_PRINTED'}
        runner.save('receipt.json', receipt)
        print(json.dumps(receipt))
        return 1
    finally:
        print('Private custom-host result directory: ' + str(folder), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        return run(args.root, args.apply)
    except (platform.Stop, OSError) as exc:
        print(json.dumps({'status': 'STOP_CLOUD_CUSTOM_HOST_LOCAL_CONTEXT',
                          'reason': str(exc) if isinstance(exc, platform.Stop) else type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())


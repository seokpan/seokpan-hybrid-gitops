import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('custom_host', Path(__file__).with_name('route-custom-host.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def role():
    obj = copy.deepcopy(m.platform.controller_role(m.SA)[0])
    obj['metadata'].update(uid='role-uid', resourceVersion='10')
    obj['rules'].pop()
    return obj


class PatchBoundary(unittest.TestCase):
    def test_only_append_rule_with_identity_version_and_rules_tests(self):
        old = role()
        operations = m.make_patch(old)
        self.assertEqual([x['path'] for x in operations],
                         ['/metadata/uid', '/metadata/resourceVersion', '/rules', '/rules/-'])
        self.assertEqual([x['op'] for x in operations], ['test', 'test', 'test', 'add'])
        self.assertEqual(operations[-1]['value'], m.CUSTOM)
        self.assertEqual(operations[2]['value'], old['rules'])

    def test_same_complete_role_needs_no_patch(self):
        obj = role()
        obj['rules'].append(copy.deepcopy(m.CUSTOM))
        self.assertEqual(m.make_patch(obj), [])

    def test_changed_owner_or_identity_refused(self):
        variants = [
            {'namespace': 'default'}, {'name': 'another-role'},
            {'annotations': {}}, {'ownerReferences': [{'uid': 'operator'}]},
            {'labels': {'argocd.argoproj.io/instance': 'other'}},
            {'deletionTimestamp': '2026-10-15T00:00:00Z'},
            {'uid': ''}, {'resourceVersion': ''},
        ]
        for changes in variants:
            with self.subTest(changes=changes), self.assertRaises(m.platform.Stop):
                obj = role()
                obj['metadata'].update(changes)
                m.make_patch(obj)

    def test_unreviewed_permission_changes_refused(self):
        for field, value in [('verbs', ['*']), ('resources', ['secrets']), ('apiGroups', ['*'])]:
            with self.subTest(field=field), self.assertRaises(m.platform.Stop):
                obj = role()
                obj['rules'][0][field] = value
                m.make_patch(obj)

    def test_extra_rule_refused(self):
        obj = role()
        obj['rules'].append({'apiGroups': [''], 'resources': ['secrets'], 'verbs': ['get']})
        with self.assertRaises(m.platform.Stop):
            m.make_patch(obj)

    def test_changed_subject_or_role_reference_refused(self):
        for subject in [True, False]:
            with self.subTest(subject=subject), self.assertRaises(m.platform.Stop):
                obj = copy.deepcopy(m.platform.controller_role(m.SA)[1])
                if subject:
                    obj['subjects'][0]['namespace'] = 'default'
                else:
                    obj['roleRef']['name'] = 'other-role'
                m.validate_binding(obj)


class ExecutionBoundary(unittest.TestCase):
    def exercise(self, mode='success', apply=True):
        with tempfile.TemporaryDirectory() as temp:
            state = {'role': role(), 'patches': [], 'gets': [], 'can': []}
            binding = copy.deepcopy(m.platform.controller_role(m.SA)[1])
            class Runner:
                def __init__(self, folder):
                    self.folder = folder
                def save(self, name, value):
                    (self.folder / name).write_text(json.dumps(value))
                def get(self, kind, name=None, namespace=None):
                    state['gets'].append(kind)
                    if kind == 'statefulset':
                        return {'spec': {'template': {'spec': {'serviceAccountName': m.SA}}}}
                    if kind == 'rolebinding':
                        return copy.deepcopy(binding)
                    return copy.deepcopy(state['role'])
                def oc(self, args, **kwargs):
                    state['patches'].append(args)
                    operations = json.loads(args[args.index('-p') + 1])
                    if '--dry-run=server' not in args:
                        if mode == 'conflict':
                            raise m.platform.Stop('OC_COMMAND_FAILED_PRIVATE_LOG')
                        state['role']['rules'].append(operations[-1]['value'])
                        if mode == 'lost-response':
                            raise m.platform.Stop('OC_COMMAND_FAILED_PRIVATE_LOG')
                        if mode == 'uid-replaced':
                            state['role']['metadata']['uid'] = 'replacement'
                    return copy.deepcopy(state['role'])
                def can(self, sa, verb, resource):
                    state['can'].append((sa, verb, resource))
                    return mode != 'auth-denied'
            pwd = types.SimpleNamespace(getpwuid=lambda uid: types.SimpleNamespace(pw_name='jth'))
            completed = subprocess.CompletedProcess([], 0, m.API + '\n', '')
            with patch.dict(sys.modules, {'pwd': pwd}), patch.object(m.os, 'getuid', create=True, return_value=1000), \
                 patch.object(m.platform, 'Runner', Runner), patch.object(m.subprocess, 'run', return_value=completed), \
                 patch('builtins.print'):
                result = m.run(Path(temp), apply)
            marker = Path(temp) / 'cloud-route-custom-host-attempt.json'
            state['marker'] = marker.exists()
            state['result'] = result
            return state

    def test_success_only_patches_role_then_checks_new_permission(self):
        state = self.exercise()
        self.assertEqual(state['result'], 0)
        self.assertEqual(len(state['patches']), 2)
        self.assertIn('--dry-run=server', state['patches'][0])
        self.assertNotIn('--dry-run=server', state['patches'][1])
        self.assertTrue(state['marker'])
        self.assertEqual(state['can'], [(m.SA, 'create', 'routes.route.openshift.io/custom-host')])
        self.assertFalse(set(state['gets']) & {'networkpolicies', 'secrets', 'deployments'})

    def test_preflight_never_mutates_or_creates_attempt_marker(self):
        state = self.exercise(apply=False)
        self.assertEqual(state['result'], 0)
        self.assertEqual(len(state['patches']), 1)
        self.assertFalse(state['marker'])
        self.assertFalse(state['can'])

    def test_server_conflict_or_lost_response_never_retries(self):
        for mode in ['conflict', 'lost-response']:
            with self.subTest(mode=mode):
                state = self.exercise(mode)
                self.assertEqual(state['result'], 1)
                self.assertEqual(len(state['patches']), 2)
                self.assertTrue(state['marker'])
                self.assertFalse(state['can'])

    def test_role_replacement_after_patch_refused(self):
        state = self.exercise('uid-replaced')
        self.assertEqual(state['result'], 1)
        self.assertFalse(state['can'])

    def test_permission_not_propagated_stops_without_repatch(self):
        state = self.exercise('auth-denied')
        self.assertEqual(state['result'], 1)
        self.assertEqual(len(state['patches']), 2)
        self.assertEqual(len(state['can']), 1)


if __name__ == '__main__':
    unittest.main()


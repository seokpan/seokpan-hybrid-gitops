import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('platform_next', Path(__file__).with_name('platform-next.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ROUTER = {'namespace': 'openshift-ingress', 'host_network': False, 'pod_labels': {
    'ingresscontroller.operator.openshift.io/deployment-ingresscontroller': 'default'}}
SA = 'openshift-gitops-argocd-application-controller'


class Boundaries(unittest.TestCase):
    def test_writer_resources_and_verbs(self):
        role, binding = m.controller_role(SA)
        self.assertEqual(role['metadata']['namespace'], 'seokpan-cloud')
        for rule in role['rules']:
            self.assertNotIn('*', rule['apiGroups'] + rule['resources'] + rule['verbs'])
            self.assertNotIn('delete', rule['verbs'])
            self.assertFalse(set(rule['resources']) & {'secrets', 'rolebindings', 'roles', 'pods/exec'})
        pods = next(r for r in role['rules'] if r['resources'] == ['pods'])
        self.assertEqual(pods['verbs'], ['get', 'list', 'watch'])
        self.assertEqual(binding['subjects'], [{'kind': 'ServiceAccount', 'name': SA,
                                               'namespace': 'openshift-gitops'}])

    def test_custom_host_create_only_in_namespace_role(self):
        role = m.controller_role(SA)[0]
        rule = next(r for r in role['rules'] if r['resources'] == ['routes/custom-host'])
        self.assertEqual(rule, {'apiGroups': ['route.openshift.io'],
                               'resources': ['routes/custom-host'], 'verbs': ['create']})

    def test_custom_host_auth_uses_explicit_subresource(self):
        with tempfile.TemporaryDirectory() as path, patch.object(m.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'yes\n', '')
            self.assertTrue(m.Runner(Path(path)).can(SA, 'create', 'routes.route.openshift.io/custom-host'))
            args = run.call_args.args[0]
            self.assertIn('routes.route.openshift.io', args)
            self.assertIn('--subresource=custom-host', args)

    def test_unknown_sa_refused(self):
        with self.assertRaises(m.Stop):
            m.controller_role('other-controller')

    def test_router_namespace_and_pod_are_one_peer(self):
        policies = m.ingress_policies(ROUTER)
        for p in policies[:2]:
            peer = p['spec']['ingress'][0]['from']
            self.assertEqual(len(peer), 1)
            self.assertEqual(set(peer[0]), {'namespaceSelector', 'podSelector'})
            self.assertEqual(peer[0]['podSelector']['matchLabels'], ROUTER['pod_labels'])

    def test_host_network_refused(self):
        r = copy.deepcopy(ROUTER); r['host_network'] = True
        with self.assertRaises(m.Stop):
            m.ingress_policies(r)

    def test_broad_or_changed_router_refused(self):
        for labels in ({}, {'app': 'router'}, {'ingresscontroller.operator.openshift.io/deployment-ingresscontroller': 'other'}):
            with self.subTest(labels=labels), self.assertRaises(m.Stop):
                m.ingress_policies({**ROUTER, 'pod_labels': labels})

    def test_ingress_only_and_deny_last(self):
        policies = m.ingress_policies(ROUTER)
        self.assertEqual(len(policies), 4)
        self.assertEqual(policies[-1]['metadata']['name'], 'seokpan-deny-ingress')
        self.assertEqual(policies[-1]['spec'], {'podSelector': {}, 'policyTypes': ['Ingress'], 'ingress': []})
        for p in policies:
            self.assertEqual(p['spec']['policyTypes'], ['Ingress'])
            self.assertNotIn('egress', p['spec'])
            self.assertEqual(p['metadata']['namespace'], 'seokpan-cloud')

    def test_only_app_ports_and_internal_peer(self):
        policies = m.ingress_policies(ROUTER)
        self.assertEqual([p['spec']['ingress'][0]['ports'][0]['port'] for p in policies[:3]],
                         [8080, 8000, 8000])
        self.assertEqual(policies[2]['spec']['ingress'][0]['from'],
                         [{'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'frontend'}}}])

    def test_existing_policy_spec_conflict_not_equal(self):
        p = m.ingress_policies(ROUTER)[0]; old = copy.deepcopy(p)
        old['spec']['ingress'][0]['ports'][0]['port'] = 9999
        self.assertFalse(m.same_object(p, old))

    def test_api_omitted_empty_ingress_list_is_same_deny(self):
        p = m.ingress_policies(ROUTER)[-1]; old = copy.deepcopy(p)
        old['spec'].pop('ingress')
        self.assertTrue(m.same_object(p, old))

    def test_added_allow_on_default_deny_is_not_empty_representation(self):
        p = m.ingress_policies(ROUTER)[-1]; old = copy.deepcopy(p)
        old['spec']['ingress'] = [{}]
        self.assertFalse(m.same_object(p, old))

    def test_existing_binding_subject_namespace_conflict(self):
        binding = m.controller_role(SA)[1]; old = copy.deepcopy(binding)
        old['subjects'][0]['namespace'] = 'other'
        self.assertFalse(m.same_object(binding, old))

    def test_service_account_empty_api_group_representation(self):
        binding = m.controller_role(SA)[1]; old = copy.deepcopy(binding)
        old['subjects'][0]['apiGroup'] = ''
        self.assertTrue(m.same_object(binding, old))

    def test_role_extra_permission_refused(self):
        role = m.controller_role(SA)[0]; old = copy.deepcopy(role)
        old['rules'].append({'apiGroups': [''], 'resources': ['secrets'], 'verbs': ['get']})
        self.assertFalse(m.same_object(role, old))

    def check_auth(self, code, stdout, stderr=''):
        with tempfile.TemporaryDirectory() as path, patch.object(m.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], code, stdout, stderr)
            result = m.Runner(Path(path)).can(SA, 'get', 'pods')
            args = run.call_args.args[0]
            for group in ['system:serviceaccounts', 'system:serviceaccounts:openshift-gitops', 'system:authenticated']:
                self.assertIn('--as-group=' + group, args)
            return result

    def test_auth_positive(self):
        self.assertTrue(self.check_auth(0, 'yes\n'))

    def test_auth_denied(self):
        self.assertFalse(self.check_auth(1, 'no\n'))

    def test_auth_error_is_not_permission_denial(self):
        with self.assertRaises(m.Stop):
            self.check_auth(1, '', 'cannot impersonate')

    def test_auth_unexpected_success_output_refused(self):
        with self.assertRaises(m.Stop):
            self.check_auth(0, 'other')


if __name__ == '__main__':
    unittest.main()


import copy
import json
from pathlib import Path
import unittest
from validate_release_record import load_record, validate

ROOT=Path(__file__).resolve().parent.parent
class RecordBoundaries(unittest.TestCase):
    def template(self):
        return copy.deepcopy({'schema_version': 1, 'record_kind': 'run', 'completeness': 'INCOMPLETE', 'release_id': None, 'source': {'app_sha': None, 'infra_sha': None, 'gitops_sha': None}, 'images': {'frontend': {'ecr_digest': None, 'harbor_digest': None, 'platform': None}, 'backend': {'ecr_digest': None, 'harbor_digest': None, 'platform': None}}, 'revisions': {'schema': None, 'config': None, 'secret': None, 'tool_manifest': None, 'recovery_bundle': None}, 'review_refs': [], 'verification': {'render': 'NOT RUN', 'deployment': 'NOT RUN', 'acceptance': 'NOT RUN'}, 'missing_inputs': ['SOURCE_COMMITS', 'ARTIFACT_DIGESTS_AND_PLATFORMS', 'CONFIGURATION_REVISIONS', 'RENDER_AND_REVIEW'], 'run_id': None, 'test_id': None, 'case_ids': [], 'requirement_ids': [], 'environment': None, 'scope': None, 'previous_run_ref': None, 'next_run_ref': None, 'render_ref': None, 'assigned_execution_owner': None, 'actual_operator': None, 'reviewer': None, 'collaborators': [], 'observed_principal_ref': None, 'account_management_owner_ref': None, 'borrowing_handover_ref': None, 'started_at_utc': None, 'finished_at_utc': None, 'started_at_kst': None, 'finished_at_kst': None, 'conditions_ref': None, 'measurements_ref': 'metrics.csv', 'timeline_ref': 'timeline.csv', 'recovery': {'backup_id': None, 'encrypted_backup_sha256': None, 'data_reference_time_utc': None, 'data_reference_level': None, 'incident_at_utc': None, 'dump_started_at_utc': None, 'dump_finished_at_utc': None, 'import_started_at_utc': None, 'import_finished_at_utc': None, 'business_resumed_at_utc': None, 'rto_seconds': None, 'rpo_seconds': None, 'persistent_data_losses': None, 'redis_runtime_losses': None}, 'raw_artifact_ref': None, 'custodian_ref': None, 'access_policy_ref': None, 'retention_ref': None, 'availability_integrity': None})
    def candidate(self):
        value=self.template();value['record_kind']='candidate';value['source'].pop('gitops_sha')
        return value
    def test_duplicate_json_fields_are_rejected(self):
        for raw in (b'{"schema_version":1,"schema_version":1}',
                    b'{"source":{"app_sha":null,"app_sha":null}}'):
            with self.assertRaises(ValueError):
                load_record(raw)
    def test_bounded_json_reader_preserves_incomplete(self):
        value=self.template()
        self.assertEqual(load_record(json.dumps(value).encode()), value)
        with self.assertRaises(ValueError):
            load_record(b' ' * 262145)
    def test_unfilled_template_is_valid_and_remains_incomplete(self):
        value=self.template();self.assertEqual(validate(value),[]);self.assertEqual(value['completeness'],'INCOMPLETE')
    def test_candidate_cannot_insert_self_sha(self):
        value=self.candidate();value['source']['gitops_sha']='a'*40;self.assertTrue(validate(value))
    def test_short_sha_rejected_even_for_incomplete_record(self):
        value=self.candidate();value['source']['app_sha']='a'*7;self.assertTrue(validate(value))
    def test_mutable_image_rejected(self):
        value=self.candidate();value['images']['frontend']['harbor_digest']='latest';self.assertTrue(validate(value))
    def test_empty_complete_record_rejected(self):
        value=self.template();value['completeness']='COMPLETE';self.assertTrue(validate(value,'lab'))
    def test_pass_without_evidence_rejected(self):
        value=self.template();value['verification']['render']='PASS';self.assertTrue(validate(value))
    def test_na_without_reason_rejected(self):
        value=self.template();value['verification']['acceptance']='N/A';self.assertTrue(validate(value))
    def test_candidate_cannot_claim_runtime_pass(self):
        value=self.candidate();value['verification']['acceptance']='PASS';value['verification_evidence']={'acceptance':'prior-ref'}
        self.assertTrue(validate(value))
    def test_explicit_clock_pair_matches(self):
        value=self.template();value['started_at_utc']='2026-10-12T00:00:00Z';value['started_at_kst']='2026-10-12T09:00:00+09:00'
        self.assertEqual(validate(value),[])
    def test_mismatched_clock_or_reversed_window_rejected(self):
        for change in ({'started_at_utc':'2026-10-12T00:00:00Z','started_at_kst':'2026-10-12T10:00:00+09:00'},
           {'started_at_utc':'2026-10-12T00:00:00Z','finished_at_utc':'2026-10-11T00:00:00Z'}):
            value=self.template();value.update(change);self.assertTrue(validate(value))
    def test_secret_revision_is_allowed_credential_values_are_not(self):
        value=self.template();value['revisions']['secret']='protected-revision-ref';self.assertEqual(validate(value),[])
        value['password']='must-never-print';self.assertTrue(validate(value))
    def test_authenticated_url_rejected(self):
        value=self.template();value['render_ref']='https://user:password@example.test/result';self.assertTrue(validate(value))
    def test_boolean_schema_is_not_integer(self):
        value=self.template();value['schema_version']=True;self.assertTrue(validate(value))
    def test_invalid_field_shapes_do_not_crash_or_become_references(self):
        for field,changed in (('verification',{'render':[]}),('verification_evidence',{'render':True}),
          ('revisions',{'secret':True}),('release_id',True)):
            value=self.template();value[field]=changed
            if field=='verification_evidence': value['verification']['render']='PASS'
            self.assertTrue(validate(value))
    def test_complete_candidate_is_input_ready_only(self):
        value=self.candidate();value.update(completeness='COMPLETE',release_id='candidate-fixture',missing_inputs=[])
        value['source']={'app_sha':'a'*40,'infra_sha':'b'*40}
        for image in value['images'].values():image.update(harbor_digest='sha256:'+'c'*64,platform='linux/amd64')
        value['revisions'].update(schema='schema-ref',config='config-ref',secret='secret-ref',tool_manifest='tool-ref')
        self.assertEqual(validate(value,'lab'),[])

if __name__=='__main__':unittest.main()

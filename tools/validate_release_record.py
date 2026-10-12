"""Validate Docs candidate/run declarations without promotion.

No network, promotion, cluster operation or output write. A valid INCOMPLETE
record remains incomplete; PASS references are declarations, not inspected proof.
"""
import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

RESULTS={'NOT RUN','PASS','PARTIAL','FAIL','N/A'}
SHA=re.compile(r'[a-f0-9]{40}\Z')
DIGEST=re.compile(r'sha256:[a-f0-9]{64}\Z')

def load_record(raw):
    if len(raw) > 262144:
        raise ValueError("record size limit")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    try:
        document = json.loads(raw, object_pairs_hook=unique)
    except RecursionError:
        raise ValueError("record nesting limit") from None
    pending = [(document, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 64:
            raise ValueError("record nesting limit")
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    return document

def check_records(directory):
    """Check candidate/run declarations; reject every symlink under releases."""
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Release directory must be a regular source directory")
    if not directory.exists():
        return 0
    if not directory.is_dir():
        raise ValueError("Release directory must be a regular source directory")
    records = []
    def failed_walk(error):
        raise ValueError("Release directory cannot be read; no raw input output")
    for parent, directories, filenames in os.walk(directory, followlinks=False, onerror=failed_walk):
        for name in directories + filenames:
            if (Path(parent) / name).is_symlink():
                raise ValueError("Release source tree must not contain symlinks")
        for name in filenames:
            path = Path(parent) / name
            if path.suffix != '.json':
                continue
            if not path.is_file() or path.stat().st_size > 262144:
                raise ValueError("Release record is not a bounded regular source file")
            records.append(path)
    for path in sorted(records):
        try:
            errors = validate(load_record(path.read_bytes()))
        except (ValueError, OSError, RecursionError):
            raise ValueError("Release record JSON cannot be read; no raw input output") from None
        if errors:
            raise ValueError("Release record format failed: " + ", ".join(errors))
    return len(records)

def validate(document, environment=None):
    errors=[]
    if not isinstance(document,dict): return ['record must be an object']
    if type(document.get('schema_version')) is not int or document['schema_version']!=1:
        errors.append('schema_version must be integer 1')
    kind=document.get('record_kind')
    if kind not in ('candidate','run'): errors.append('record_kind must be candidate or run')
    complete=document.get('completeness')=='COMPLETE'
    if document.get('completeness') not in ('COMPLETE','INCOMPLETE'): errors.append('unknown completeness')
    if complete and document.get('missing_inputs'): errors.append('COMPLETE cannot retain missing_inputs')
    if not isinstance(document.get('missing_inputs'),list): errors.append('missing_inputs must be a list')
    excluded=document.get('out_of_scope',{})
    if not isinstance(excluded,dict): excluded={}; errors.append('out_of_scope must be an object')
    def required(path,value):
        if complete and (value is None or value=='' or value==[]):
            if not isinstance(excluded.get(path),str) or not excluded[path].strip():
                errors.append(path+' needs a value or a stated scope exclusion')
    required('release_id',document.get('release_id'))
    if document.get('release_id') is not None and (not isinstance(document['release_id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',document['release_id'])):
        errors.append('release_id is invalid')
    source=document.get('source')
    if not isinstance(source,dict): source={};errors.append('source must be an object')
    if kind=='candidate' and 'gitops_sha' in source: errors.append('candidate cannot contain its own GitOps commit SHA')
    for field in ('app_sha','infra_sha')+(('gitops_sha',) if kind=='run' else ()):
        value=source.get(field)
        required('source.'+field,value)
        if value is not None and (not isinstance(value,str) or not SHA.fullmatch(value)):
            errors.append('source.'+field+' must be a full SHA')
    env=environment or document.get('environment')
    if complete and env not in ('lab','cloud','recovery'): errors.append('completed record needs an explicit lab/cloud/recovery scope')
    images=document.get('images')
    if not isinstance(images,dict): images={};errors.append('images must be an object')
    for component in ('frontend','backend'):
        image=images.get(component)
        if not isinstance(image,dict): image={};errors.append('images.'+component+' must be an object')
        for field in ('harbor_digest','ecr_digest'):
            value=image.get(field)
            if value is not None and (not isinstance(value,str) or not DIGEST.fullmatch(value)):
                errors.append('images.'+component+'.'+field+' must be an immutable digest')
        selected='ecr_digest' if env=='cloud' else 'harbor_digest'
        required('images.'+component+'.'+selected,image.get(selected))
        value=image.get('platform')
        required('images.'+component+'.platform',value)
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'linux/(?:amd64|arm64)(?:/v[0-9]+)?',value)):
            errors.append('images.'+component+'.platform is invalid')
    revisions=document.get('revisions')
    if not isinstance(revisions,dict): revisions={};errors.append('revisions must be an object')
    for field in ('schema','config','secret','tool_manifest'):
        required('revisions.'+field,revisions.get(field))
    for field,value in revisions.items():
        if value is not None and (not isinstance(value,str) or not value.strip()): errors.append('revisions.'+field+' must be a logical revision reference')
    if env=='recovery': required('revisions.recovery_bundle',revisions.get('recovery_bundle'))
    verification=document.get('verification')
    if not isinstance(verification,dict): verification={};errors.append('verification must be an object')
    evidence=document.get('verification_evidence',{})
    reasons=document.get('verification_exclusions',{})
    if not isinstance(evidence,dict): evidence={};errors.append('verification_evidence must be an object')
    if not isinstance(reasons,dict): reasons={};errors.append('verification_exclusions must be an object')
    for stage in ('render','deployment','acceptance'):
        outcome=verification.get(stage)
        if not isinstance(outcome,str) or outcome not in RESULTS: errors.append('verification.'+stage+' is invalid')
        if outcome=='PASS' and (not isinstance(evidence.get(stage),str) or not evidence[stage].strip()): errors.append('verification.'+stage+' PASS needs an evidence reference')
        if outcome=='N/A' and (not isinstance(reasons.get(stage),str) or not reasons[stage].strip()): errors.append('verification.'+stage+' N/A needs a reason')
        if kind=='candidate' and stage in ('deployment','acceptance') and outcome not in ('NOT RUN','N/A'):
            errors.append('candidate runtime results belong in a separate run record')
    def stamp(field):
        value=document.get(field)
        if value is None: return None
        try:
            parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            assert parsed.tzinfo is not None
            wanted=dt.timedelta(hours=9 if field.endswith('_kst') else 0)
            assert parsed.utcoffset()==wanted
            return parsed
        except (ValueError,TypeError,AttributeError,AssertionError):
            errors.append(field+' requires a valid explicit '+('KST' if field.endswith('_kst') else 'UTC')+' timestamp')
            return None
    if kind=='run':
        for field in ('run_id','test_id','case_ids','requirement_ids','actual_operator','conditions_ref','render_ref'):
            required(field,document.get(field))
        for name in ('started_at','finished_at'):
            utc=stamp(name+'_utc');kst=stamp(name+'_kst')
            required(name+'_utc',document.get(name+'_utc'));required(name+'_kst',document.get(name+'_kst'))
            if utc and kst and utc!=kst: errors.append(name+' UTC/KST must identify the same instant')
        start=stamp('started_at_utc');end=stamp('finished_at_utc')
        if start and end and end<start: errors.append('finish precedes start')
    def private_scan(value,path='record'):
        if isinstance(value,dict):
            for key,child in value.items():
                if re.search(r'password|passwd|bearer.?token|authorization|private.?key|secret_value',str(key),re.I):
                    errors.append(path+'.'+str(key)+' contains a prohibited credential field')
                private_scan(child,path+'.'+str(key))
        elif isinstance(value,list):
            for child in value: private_scan(child,path)
        elif isinstance(value,str):
            if '-----BEGIN ' in value and 'PRIVATE KEY-----' in value: errors.append(path+' contains private key material')
            if '://' in value:
                try:
                    url=urlsplit(value)
                    if url.username is not None or any(re.search(r'token|secret|password',k,re.I) for k in parse_qs(url.query)):
                        errors.append(path+' contains an authenticated URL')
                except ValueError: errors.append(path+' contains an invalid URL')
    private_scan(document)
    return list(dict.fromkeys(errors))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record',type=Path);parser.add_argument('--environment',choices=('lab','cloud','recovery'))
    args=parser.parse_args()
    try:
        raw=args.record.read_bytes()
        if len(raw)>262144: raise ValueError('record size limit')
        document=load_record(raw)
        errors=validate(document,args.environment)
    except (OSError,ValueError,RecursionError):
        print('INVALID_RECORD; no raw input/error output');return 2
    print(json.dumps({'format_valid':not errors,'completeness':document.get('completeness') if isinstance(document,dict) else None,
        'errors':errors,'scope':'DECLARATIONS_ONLY_NOT_RUNTIME_OR_EVIDENCE_INSPECTION'}))
    return 2 if errors else 0

if __name__=='__main__': raise SystemExit(main())

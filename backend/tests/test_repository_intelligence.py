import io
import json
import tarfile
import time

import httpx
import pytest
from fastapi import HTTPException

from core_ai import db, repository_intelligence as intelligence, skills


def test_scan_analyse_and_record_verification(signed, monkeypatch):
    archive = io.BytesIO()
    readme = b'# Validate slides\nRun `python tools/validate.py sample.pptx`.\n'
    with tarfile.open(fileobj=archive, mode='w:gz') as bundle:
        for name, content in [('README.md',readme),('tools/validate.py',b'print("fixture")'),
                              ('pyproject.toml',b'[project]\nname="fixture"'),('assets/sample.pptx',b'\x00\x01')]:
            member = tarfile.TarInfo('root/'+name)
            member.size = len(content)
            bundle.addfile(member, io.BytesIO(content))
    archive.seek(0)
    files = []
    entries, invalid = skills.discover(archive,time.monotonic()+5,inventory=files)
    assert not entries and not invalid
    assert {file['kind'] for file in files} == {'program','documentation','manifest','asset'}
    assert next(file for file in files if file['kind']=='asset').get('text') is None
    sha = 'b'*40
    monkeypatch.setattr(skills,'fetch_collection',lambda *_:(sha,[],[],[],files))
    imported = signed.post('/api/v1/skills/import',json={'repository':'example/programs'}).json()
    assert imported['count']==0 and imported['file_count']==4
    root = '/api/v1/skills/collections/'+imported['id']+'/intelligence'
    params = {'commit':sha}
    db.query('UPDATE skill_releases SET repository_inventory=NULL WHERE collection_id=%s', (imported['id'],))
    assert not signed.get(root,params=params).json()['available']
    assert signed.post(root+'/rescan',params=params).status_code==200
    catalog = signed.get(root,params={**params,'kind':'program'}).json()
    assert catalog['total']==1 and catalog['files'][0]['path']=='tools/validate.py'
    assert 'text' not in catalog['files'][0]
    assert 'fixture' in signed.get(root+'/file',params={**params,'path':'tools/validate.py'}).json()['text']
    proposal = intelligence.Plan(summary='One validator found.',capabilities=[
        intelligence.Capability(name='Slide validator',kind='Task tool',decision='Install tool',reason='Documented in README.',
            sources=['README.md'],steps=[intelligence.InstallStep(instruction='Run against a sample.',
                command='python tools/validate.py sample.pptx',source='README.md')],
            test_input='sample.pptx',expected_result='Validation result.')
    ])
    def fake_model(endpoint, model, payload):
        assert payload['commit']==sha and payload['evidence'][0]['path']=='README.md'
        return proposal
    monkeypatch.setattr(intelligence,'proposed_plan',fake_model)
    created = signed.post(root+'/analyse',params=params,json={'paths':['README.md'],'focus':'Validate slides'})
    assert created.status_code==201,created.text
    report = root+'/reports/'+created.json()['id']
    assert signed.get(report).json()['report']['capabilities'][0]['decision']=='Install tool'
    assert signed.post(report+'/verify/0',json={'state':'Verified','evidence':''}).status_code==422
    assert signed.post(report+'/verify/0',json={'state':'Verified','evidence':'Sample passed.'}).status_code==200
    assert signed.get(report).json()['verification'][0]['evidence']=='Sample passed.'
    assert signed.post(report+'/verify/1',json={'state':'Failed','evidence':'Outside index'}).status_code==404


def test_rejects_model_commands_missing_from_evidence(monkeypatch):
    original = httpx.Client
    def respond(request):
        assert json.loads(request.content)['stream'] is False
        result = {'summary':'Report','capabilities':[{'name':'Tool','kind':'Task tool','decision':'Install tool',
          'reason':'Read the guide.','sources':['README.md'],'steps':[{'instruction':'Install','source':'README.md',
          'command':'install never-documented'}],'test_input':'Fixture','expected_result':'Success'}]}
        return httpx.Response(200,json={'message':{'content':json.dumps(result)}})
    monkeypatch.setattr(intelligence.httpx,'Client',lambda **opts:original(transport=httpx.MockTransport(respond),**opts))
    with pytest.raises(HTTPException,match='could not be verified'):
        intelligence.proposed_plan('http://127.0.0.1:11434','fixture',{'evidence':[{'path':'README.md','text':'A guide.'}]})

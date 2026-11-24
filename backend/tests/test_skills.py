import io
import tarfile
import time
import uuid

from core_ai import skills


def bundle():
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as tar:
        for index in range(125):
            name = f'skill-{index:03}'
            content = f'---\nname: {name}\ndescription: Investigate case {index:03}.\n---\nCheck facts for {name}.\n'.encode()
            member = tarfile.TarInfo(f'fixture/skills/{name}/SKILL.md')
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
        executable = tarfile.TarInfo('fixture/skills/skill-000/scripts/test.sh')
        tar.addfile(executable, io.BytesIO())
    archive.seek(0)
    return archive


def test_catalog_bulk_activation_update_rollback_and_run_provenance(signed, work, monkeypatch):
    discovered, invalid = skills.discover(bundle(), time.monotonic() + 5)
    assert len(discovered) == 125 and not invalid
    assert discovered[0]['scripts'] is True
    assert skills.parse_skill('broken/SKILL.md', b'---\nname: []\ndescription: Invalid\n---\ntext') is None
    sha = 'a' * 40
    updated_sha = 'b' * 40
    location = {'repository': 'https://github.com/example/skills?utm_source=chatgpt.com#readme', 'ref': 'main'}
    monkeypatch.setattr(skills, 'fetch_collection', lambda repository, ref: (sha, discovered, [], [], []))
    imported = signed.post('/api/v1/skills/import', json=location)
    assert imported.status_code == 200, imported.text
    ident = imported.json()['id']
    path = '/api/v1/skills/collections/' + ident
    initial = signed.get(path).json()
    assert initial['active_commit'] is None
    assert len(initial['changes']['added']) == 125 and 'body' not in initial['skills'][0]
    assert signed.get(path+'/skill', params={'commit': sha, 'path': discovered[0]['path']}).json()['body'].startswith('Check facts')
    assignment = signed.put('/api/v1/skills/agents/'+work['agent_id'], json={'collections': [ident]})
    assert assignment.status_code == 200, assignment.text
    manual = {**work, 'prompt': '/skill example/skills:skill-000\nReview case 000'}
    assert signed.post('/api/v1/runs', json=manual).status_code == 422

    def activate(commit, current):
        return signed.put(path+'/activate', json={'commit': commit, 'expected_commit': current})

    assert activate(sha, None).status_code == 200
    original = signed.post('/api/v1/runs', json=manual)
    assert original.status_code == 201, original.text
    original_path = '/api/v1/runs/' + original.json()['id']
    assert signed.get(original_path).json()['skill_versions'][0]['commit'] == sha

    changed = [{**discovered[0], 'body': 'Updated instructions.'}, *discovered[1:]]
    monkeypatch.setattr(skills, 'fetch_collection', lambda repository, ref: (updated_sha, changed, [], [], []))
    assert signed.post('/api/v1/skills/import', json=location).json()['id'] == ident
    assert signed.get(path, params={'commit': updated_sha}).json()['changes']['changed'] == [discovered[0]['path']]
    assert activate(updated_sha, None).status_code == 409
    assert activate(updated_sha, sha).status_code == 200
    assert signed.get(original_path).json()['skill_versions'][0]['commit'] == sha
    assert 'Check facts' in signed.get(original_path).json()['skill_context']
    conversation = signed.post('/api/v1/chat/conversations', json={'model': work['model']}).json()['id']
    chat = '/api/v1/chat/conversations/' + conversation
    message = signed.post(chat+'/messages', json={
        'content': manual['prompt'], 'request_id': str(uuid.uuid4()), 'model': work['model'], 'agent_id': work['agent_id']
    })
    assert message.status_code == 201, message.text
    history = signed.get(chat).json()['messages']
    assert history[-1]['skill_versions'][0]['commit'] == updated_sha
    assert activate(sha, updated_sha).status_code == 200
    assert signed.put(path+'/exclusion', json={'path': discovered[0]['path'], 'excluded': True}).status_code == 200
    assert signed.post('/api/v1/runs', json=manual).status_code == 422
    auto = signed.post('/api/v1/runs', json={**work, 'prompt': 'Investigate case 001'})
    assert auto.status_code == 201, auto.text
    auto_result = signed.get('/api/v1/runs/'+auto.json()['id']).json()['skill_versions']
    assert auto_result[0]['name'] == 'skill-001' and auto_result[0]['commit'] == sha
    assert len(auto_result) <= 2


def test_repository_link_normalization():
    assert skills.repository_name('https://github.com/obra/superpowers?utm_source=chatgpt.com') == 'obra/superpowers'
    assert skills.repository_name('Obra/Superpowers') == 'obra/superpowers'
    assert skills.repository_name('https://github.com/obra/superpowers.git/') == 'obra/superpowers'
    for link in ('https://github.com.evil.example/obra/superpowers',
                 'https://github.com@evil.example/obra/superpowers',
                 'https://github.com/obra/superpowers/tree/main',
                 'https://github.com//obra/superpowers', 'obra/..'):
        assert skills.repository_name(link) is None


def test_chat_skill_controls_use_approved_current_versions(signed, work, monkeypatch):
    commit = 'a' * 40
    entries, _ = skills.discover(bundle(), time.monotonic() + 5)
    monkeypatch.setattr(skills, 'fetch_collection', lambda repository, ref: (commit, entries[:3], [], [], []))
    collection = signed.post('/api/v1/skills/import', json={'repository': 'example/skills'}).json()['id']
    catalog = '/api/v1/skills/collections/' + collection
    assert signed.put(catalog+'/activate', json={'commit': commit}).status_code == 200
    preview_path = '/api/v1/skills/chat/preview'
    preview = signed.post(preview_path, json={'prompt': 'Investigate case 001'}).json()
    assert len(preview['available']) == 3
    assert preview['automatic'][0]['name'] == 'skill-001'
    assert 'body' not in preview['automatic'][0]
    agent = work['agent_id']
    assert signed.post(preview_path, json={'agent_id': agent}).json()['available'] == []
    assert signed.put('/api/v1/skills/agents/'+agent, json={'collections': [collection]}).status_code == 200
    assert len(signed.post(preview_path, json={'agent_id': agent}).json()['available']) == 3

    def send(mode, selected=(), content='Investigate case 001'):
        conversation = signed.post('/api/v1/chat/conversations', json={'model': work['model']}).json()['id']
        path = '/api/v1/chat/conversations/' + conversation
        response = signed.post(path+'/messages', json={
            'content': content, 'request_id': str(uuid.uuid4()), 'model': work['model'],
            'skill_selection': {'mode': mode, 'selected': list(selected)},
        })
        return path, response

    choice = {key: preview['available'][0][key] for key in ('collection_id', 'commit', 'path')}
    path, response = send('manual', [choice])
    assert response.status_code == 201, response.text
    generation = response.json()['id']
    versions = signed.get(path+'/reply/'+generation).json()['skill_versions']
    assert [version['name'] for version in versions] == ['skill-000']
    assert signed.get(path).json()['messages'][-1]['skill_versions'] == versions
    assert send('manual', [{**choice, 'commit': 'b'*40}])[1].status_code == 409
    assert send('manual')[1].status_code == 422
    path, response = send('off', [choice], '/skill skill-001')
    assert response.status_code == 201, response.text
    assert signed.get(path).json()['messages'][-1]['skill_versions'] == []


def test_agent_only_repository_import_and_deduplication(signed, monkeypatch):
    destination = io.BytesIO()
    fixtures = {
        '.claude/agents/analyst.md': b'---\nname: analyst\ndescription: Analyse evidence\ntools: Bash\n---\nReview the supplied evidence.',
        '.github/agents/reviewer.agent.md': b'---\ndescription: Review changes\n---\nWrite review notes.',
        'AGENTS.md': b'---\nname: guidance\ndescription: Repository guidance\n---\nRepository-wide guidance.',
    }
    with tarfile.open(fileobj=destination,mode='w:gz') as archive:
        for path, content in fixtures.items():
            entry = tarfile.TarInfo('repo/'+path)
            entry.size = len(content)
            archive.addfile(entry,io.BytesIO(content))
    destination.seek(0)
    definitions = []
    entries, invalid = skills.discover(destination,time.monotonic()+5,definitions=definitions,repository='example/agents')
    assert [entry['name'] for entry in definitions] == ['analyst','reviewer']
    assert not entries and not invalid
    assert skills.parse_agent_definition('engineering/engineer.md',
        b'---\nname: Engineer\ndescription: Implement changes\ncolor: blue\n---\nUse project context.',
        'example/agency-agents')['name']=='Engineer'

    sha = 'e'*40
    monkeypatch.setattr(skills,'fetch_collection',lambda *_:(sha,entries,invalid,definitions,[]))
    result = signed.post('/api/v1/skills/import',json={'repository':'example/agents'}).json()
    assert result['count']==0 and result['agent_count']==2
    base = '/api/v1/skills/collections/'+result['id']
    params = {'commit':sha,'path':definitions[0]['path']}
    assert 'instructions' not in signed.get(base).json()['agent_definitions'][0]
    assert signed.get(base+'/agent',params=params).json()['instructions']=='Review the supplied evidence.'
    created = signed.post(base+'/agent',params=params).json()
    assert created['created']
    existing = signed.post(base+'/agent',params=params).json()
    assert existing == {'id':created['id'],'created':False}
    row, = [item for item in signed.get('/api/v1/agents').json() if item['id']==created['id']]
    assert row['runtime_mode']=='analysis' and not row['enabled'] and row['tools']==[]
    assert row['imported_source']=={'path':params['path'],'commit':sha,'repository':'example/agents'}

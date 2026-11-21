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
    location = {'repository': 'https://github.com/example/skills', 'ref': 'main'}
    monkeypatch.setattr(skills, 'fetch_collection', lambda repository, ref: (sha, discovered, []))
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
    monkeypatch.setattr(skills, 'fetch_collection', lambda repository, ref: (updated_sha, changed, []))
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

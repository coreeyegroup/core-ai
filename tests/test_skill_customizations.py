import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from psycopg.types.json import Jsonb

from core_ai import api, db, skills


@pytest.mark.skipif(not os.getenv('CORE_AI_TEST_SKILLS_DB'), reason='Requires a disposable PostgreSQL database')
def test_collection_and_agent_skill_edits_and_deletion(monkeypatch):
    monkeypatch.setenv('CORE_AI_DATABASE_URL', os.environ['CORE_AI_TEST_SKILLS_DB'])
    db.migrate()
    admin = {'id': uuid4(), 'role': 'ADMIN'}
    owner = {'id': uuid4(), 'role': 'EDITOR'}
    collection, first, second = uuid4(), uuid4(), uuid4()
    commit, path = 'd' * 40, 'market-review/SKILL.md'
    with db.connect() as conn:
        for actor in (admin, owner):
            conn.execute('INSERT INTO users(id,username,password_hash) VALUES (%s,%s,%s)',
                         (actor['id'], str(actor['id']), 'test'))
        for agent in (first, second):
            conn.execute("INSERT INTO agents(id,name,instructions,owner_id) VALUES (%s,'Agent','Test',%s)",
                         (agent, owner['id']))
        conn.execute("INSERT INTO skill_collections(id,repository,git_ref) VALUES (%s,'test/skills','main')", (collection,))
        conn.execute('INSERT INTO skill_releases(collection_id,commit_sha,skills) VALUES (%s,%s,%s)',
                     (collection, commit, Jsonb([dict(path=path,name='market-review',description='Review the market',body='Imported instructions')])))
        conn.execute('UPDATE skill_collections SET active_commit=%s WHERE id=%s', (commit, collection))
    for agent in (first, second):
        skills.assign(agent, skills.Assignment(collections=[collection]), owner)

    def guidance(agent):
        with db.connect() as conn:
            return skills.snapshot(conn, agent, 'market review')

    def agent_change(action, edit=None):
        skills.change_agent_skill(first, collection, commit, path, skills.AgentSkillChange(action=action,edit=edit), owner)

    global_edit = skills.SkillEdit(description='Review the market',body='Collection instructions')
    local_edit = skills.SkillEdit(description='Review the market',body='First agent instructions')
    with pytest.raises(HTTPException) as error:
        skills.edit_collection_skill(collection, owner, commit, path, global_edit)
    assert error.value.status_code == 403
    skills.edit_collection_skill(collection, admin, commit, path, global_edit)
    assert 'Collection instructions' in guidance(first)[0]
    agent_change('edit', local_edit)
    assert 'First agent instructions' in guidance(first)[0]
    assert 'Collection instructions' in guidance(second)[0]
    assert guidance(first)[1][0]['customized']
    agent_change('remove')
    assert guidance(first) == ('', [])
    assert guidance(second)[0]
    agent_change('restore')
    assert 'First agent instructions' in guidance(first)[0]
    skills.exclude(collection, skills.Exclusion(path=path,excluded=True), admin)
    assert guidance(first) == guidance(second) == ('', [])
    assert skills.assigned_skills(first, owner)[0]['collection_removed']
    skills.exclude(collection, skills.Exclusion(path=path,excluded=False), admin)
    agent_change('reset')
    assert 'Collection instructions' in guidance(first)[0]
    skills.reset_collection_skill(collection, admin, commit, path)
    assert 'Imported instructions' in guidance(first)[0]


    renamed = skills.CollectionProfile(title='Market Research Toolkit', description='Shared research skills')
    skills.edit_collection(collection, renamed, admin)
    assert next(row for row in skills.catalog(admin) if row['id']==collection)['title'] == renamed.title
    skills.delete_collection(collection, admin)
    assert collection not in {row['id'] for row in skills.catalog(admin)}
    assert collection in {row['id'] for row in skills.catalog(admin, include_deleted=True)}
    assert guidance(first) == ('', [])
    assert skills.agent_collections(first, owner) == [collection]
    skills.restore_collection(collection, admin)
    assert 'Imported instructions' in guidance(first)[0]

    api.delete_agent(first, owner)
    assert first not in {row['id'] for row in api.agents(owner)}
    archived = next(row for row in api.agents(owner, include_deleted=True) if row['id']==first)
    assert archived['deleted_at'] is not None and not archived['enabled']
    with pytest.raises(HTTPException):
        api.update_agent(first, api.Agent(name='Archived', instructions='Fixture'), owner)
    api.restore_agent(first, owner)
    restored = next(row for row in api.agents(owner) if row['id']==first)
    assert restored['deleted_at'] is None and not restored['enabled']
    assert skills.agent_collections(first, owner) == [collection]

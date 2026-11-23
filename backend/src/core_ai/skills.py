"""Versioned, instruction-only GitHub collections. Archive contents are never executed."""
import io
import re
import tarfile
import time
import uuid
from typing import Annotated, Literal
from urllib.parse import quote, unquote, urlsplit

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import access, auth, db

router = APIRouter(prefix='/api/v1/skills')
User = Annotated[dict, Depends(auth.session)]
REPOSITORY = re.compile(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+')
REF = re.compile(r'[a-zA-Z0-9_][a-zA-Z0-9._/-]{0,199}')
SHA = re.compile(r'[0-9a-f]{40}')
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
ARCHIVE_LIMIT = 24 * 1024 * 1024


class Import(BaseModel):
    repository: str = Field(max_length=250)
    ref: str = Field(default='HEAD', max_length=200)


class Activation(BaseModel):
    commit: str
    expected_commit: str | None = None


class Assignment(BaseModel):
    collections: list[uuid.UUID] = Field(max_length=100)


class Exclusion(BaseModel):
    path: str = Field(max_length=500)
    excluded: bool


class SkillEdit(BaseModel):
    description: str = Field(min_length=1, max_length=1024)
    body: str = Field(min_length=1, max_length=64000)


def parse_skill(path, raw):
    try:
        text = raw.decode('utf-8-sig').replace('\r\n', '\n')
        preamble, metadata, body = re.split(r'^---[ \t]*$', text, maxsplit=2, flags=re.M)
        if preamble or len(metadata) > 8192 or '\x00' in text:
            return None
        # BaseLoader reads scalar strings without constructing tagged Python objects.
        fields = yaml.load(metadata, Loader=yaml.BaseLoader)
        if not isinstance(fields, dict):
            return None
        name, description = fields.get('name'), fields.get('description')
        if (not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name)
                or not isinstance(description, str) or not description.strip() or len(description) > 1024
                or '\x00' in description or not body.strip()):
            return None
        return {'name': name, 'description': description.strip(), 'path': path, 'body': body.strip(),
                **{key: fields[key].replace('\x00', '')[:500] if isinstance(fields.get(key), str) else ''
                   for key in ('license', 'compatibility', 'allowed-tools')}}
    except (UnicodeError, ValueError, yaml.YAMLError, RecursionError):
        return None


def discover(archive, deadline):
    skills, paths, invalid = [], set(), []
    size = 0
    with tarfile.open(fileobj=archive, mode='r|gz') as tar:
        for index, member in enumerate(tar):
            size += member.size
            if index >= 30000 or size > 150 * 1024 * 1024 or time.monotonic() > deadline:
                raise ValueError('Collection archive exceeds inspection limits.')
            path = member.name.partition('/')[2]
            if not member.isfile() or not path or '..' in path.split('/') or len(path) > 500:
                continue
            paths.add(path)
            if path.split('/')[-1] != 'SKILL.md':
                continue
            skill = parse_skill(path, tar.extractfile(member).read()) if member.size <= 96 * 1024 else None
            if skill:
                skills.append(skill)
            else:
                invalid.append(path)
            if len(skills) + len(invalid) > 2000:
                raise ValueError('Collection exceeds 2,000 skill files.')
    if len({skill['path'] for skill in skills}) != len(skills):
        raise ValueError('Archive has duplicate skill paths.')
    for skill in skills:
        root = skill['path'].removesuffix('SKILL.md')
        resources = [path[len(root):] for path in paths if path.startswith(root)]
        skill['scripts'] = any(path.startswith('scripts/') for path in resources)
        skill['references'] = sorted(path for path in resources if path.startswith(('references/', 'assets/')))[:30]
    return sorted(skills, key=lambda skill: (skill['name'], skill['path'])), invalid


def fetch_collection(repository, ref):
    deadline = time.monotonic() + 45
    with httpx.Client(timeout=12, trust_env=False, follow_redirects=False) as client:
        response = client.get(f'https://api.github.com/repos/{repository}/commits/{quote(ref, safe="")}')
        response.raise_for_status()
        sha = response.json().get('sha', '')
        if not SHA.fullmatch(sha):
            raise ValueError('GitHub did not return an immutable commit.')
        with io.BytesIO() as archive, client.stream('GET', f'https://codeload.github.com/{repository}/tar.gz/{sha}') as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(65536):
                if archive.tell() + len(chunk) > ARCHIVE_LIMIT or time.monotonic() > deadline:
                    raise ValueError('Collection archive exceeds download limits.')
                archive.write(chunk)
            archive.seek(0)
            skills, invalid = discover(archive, deadline)
    return sha, skills, invalid


@router.get('')
def catalog(user: User, include_deleted: bool = False):
    return db.query("""
        SELECT c.*, (SELECT count(*) FROM skill_releases r
            CROSS JOIN LATERAL jsonb_array_elements(r.skills) AS s
            WHERE r.collection_id=c.id AND r.commit_sha=c.active_commit
              AND NOT EXISTS (SELECT 1 FROM skill_exclusions e WHERE e.collection_id=c.id AND e.path=s->>'path')) AS skill_count,
            (SELECT r.commit_sha FROM skill_releases r WHERE r.collection_id=c.id
             ORDER BY imported_at DESC LIMIT 1) AS latest_commit
        FROM skill_collections c WHERE c.deleted_at IS NULL OR %s ORDER BY repository,git_ref
    """, (include_deleted and user['role']=='ADMIN',))


class CollectionProfile(BaseModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=2000)


@router.put('/collections/{ident}')
def edit_collection(ident: uuid.UUID, body: CollectionProfile, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute("""UPDATE skill_collections SET title=%s,description=%s
            WHERE id=%s AND deleted_at IS NULL RETURNING id""",
            (body.title.strip(),body.description.strip(),ident)).fetchone()
        if not row:
            raise HTTPException(404, 'Active collection not found.')
        db.event('skills.collection_updated', user['id'], {'collection':str(ident)}, conn=conn)
    return {'ok':True}


@router.delete('/collections/{ident}')
def delete_collection(ident: uuid.UUID, user: User):
    return set_collection_deleted(ident, user, True)


@router.post('/collections/{ident}/restore')
def restore_collection(ident: uuid.UUID, user: User):
    return set_collection_deleted(ident, user, False)


def set_collection_deleted(ident, user, deleted):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute("""UPDATE skill_collections SET deleted_at=CASE WHEN %s THEN COALESCE(deleted_at,now()) END
            WHERE id=%s RETURNING id""", (deleted,ident)).fetchone()
        if not row:
            raise HTTPException(404, 'Collection not found.')
        db.event('skills.collection_deleted' if deleted else 'skills.collection_restored', user['id'],
                 {'collection':str(ident)}, conn=conn)
    return {'ok':True}


def repository_name(value):
    value = value.strip()
    if '://' in value:
        try:
            url = urlsplit(value)
        except ValueError:
            return None
        if url.scheme != 'https' or url.netloc.lower() != 'github.com':
            return None
        value = url.path.removeprefix('/')
    value = value.removesuffix('/').removesuffix('.git')
    if REPOSITORY.fullmatch(value) and all(part not in ('.', '..') for part in value.split('/')):
        return value.lower()
    return None


@router.post('/import')
def import_collection(body: Import, user: User):
    access.admin(user)
    repository = repository_name(body.repository)
    if not repository or not REF.fullmatch(body.ref) or '..' in body.ref:
        raise HTTPException(422, 'Enter a public GitHub owner/repository and a valid branch, tag, or commit.')
    try:
        sha, skills, invalid = fetch_collection(repository, body.ref)
    except (httpx.HTTPError, ValueError, tarfile.TarError, OSError, EOFError):
        raise HTTPException(422, 'GitHub import failed. Check repository access, ref, or archive size.') from None
    if not skills:
        raise HTTPException(422, 'No valid SKILL.md files were found.')
    with db.connect() as conn:
        collection = conn.execute('''
            INSERT INTO skill_collections(id,repository,git_ref) VALUES (%s,%s,%s)
            ON CONFLICT (repository,git_ref) DO UPDATE SET repository=excluded.repository RETURNING id
        ''', (uuid.uuid4(), repository, body.ref)).fetchone()
        ident = collection['id']
        conn.execute('''INSERT INTO skill_releases(collection_id,commit_sha,skills) VALUES (%s,%s,%s)
                     ON CONFLICT DO NOTHING''', (ident, sha, Jsonb(skills)))
        db.event('skills.imported', user['id'], {'collection': str(ident), 'commit': sha, 'count': len(skills)}, conn=conn)
    return {'id': ident, 'commit': sha, 'count': len(skills), 'invalid': invalid}


@router.get('/collections/{ident}')
def collection_detail(ident: uuid.UUID, user: User, commit: str | None = None):
    with db.connect() as conn:
        collection = conn.execute('SELECT * FROM skill_collections WHERE id=%s', (ident,)).fetchone()
        if not collection:
            raise HTTPException(404, 'Collection not found.')
        releases = conn.execute('''SELECT commit_sha,imported_at,jsonb_array_length(skills) AS skill_count
                                 FROM skill_releases WHERE collection_id=%s ORDER BY imported_at DESC''', (ident,)).fetchall()
        chosen = commit or collection['active_commit'] or releases[0]['commit_sha']
        snapshots = conn.execute('''SELECT commit_sha,skills FROM skill_releases
                                    WHERE collection_id=%s AND commit_sha=ANY(%s)''',
                                 (ident, [chosen, collection['active_commit']])).fetchall()
        snapshots = {row['commit_sha']: row['skills'] for row in snapshots}
        if chosen not in snapshots:
            raise HTTPException(404, 'Version not found.')
        effective = {row['path']: row for row in skill_rows(conn, collection_id=ident, commit=chosen)}
        exclusions = conn.execute('SELECT path FROM skill_exclusions WHERE collection_id=%s', (ident,)).fetchall()
    active = {skill['path']: skill for skill in snapshots.get(collection['active_commit'], [])}
    selected = {skill['path']: skill for skill in snapshots[chosen]}
    return {**collection, 'commit': chosen, 'releases': releases, 'skills': [
                {**{key: value for key, value in skill.items() if key != 'body'},
                 'description': effective[skill['path']]['description'],
                 'customized': effective[skill['path']]['customized']}
                for skill in snapshots[chosen]],
            'excluded': [row['path'] for row in exclusions],
            'changes': {'added': sorted(selected.keys()-active.keys()), 'removed': sorted(active.keys()-selected.keys()),
                        'changed': sorted(path for path in active.keys() & selected.keys() if active[path] != selected[path])}}


@router.get('/collections/{ident}/skill')
def skill_detail(ident: uuid.UUID, user: User, commit: str, path: str):
    with db.connect() as conn:
        return find_skill(conn, ident, commit, path)


def find_skill(conn, collection_id, commit, path, agent_id=None):
    rows = skill_rows(conn, agent_id, collection_id, commit, path=path, with_body=True)
    if not rows:
        raise HTTPException(404, 'Skill not found in this version or assignment.')
    return rows[0]


def checked_edit(body):
    description, instructions = body.description.strip(), body.body.strip()
    if not description or not instructions or '\x00' in description or '\x00' in instructions:
        raise HTTPException(422, 'Enter a description and instructions.')
    return description, instructions


@router.put('/collections/{ident}/skill')
def edit_collection_skill(ident: uuid.UUID, user: User, commit: str, path: str, body: SkillEdit):
    access.admin(user)
    with db.connect() as conn:
        find_skill(conn, ident, commit, path)
        conn.execute("""INSERT INTO skill_collection_edits VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (collection_id,commit_sha,path) DO UPDATE SET description=excluded.description,body=excluded.body""",
                     (ident, commit, path, *checked_edit(body)))
        db.event('skills.collection_skill_edited', user['id'], {'collection':str(ident),'commit':commit,'path':path}, conn=conn)
    return {'ok': True}


@router.post('/collections/{ident}/skill/reset')
def reset_collection_skill(ident: uuid.UUID, user: User, commit: str, path: str):
    access.admin(user)
    with db.connect() as conn:
        find_skill(conn, ident, commit, path)
        conn.execute('DELETE FROM skill_collection_edits WHERE collection_id=%s AND commit_sha=%s AND path=%s', (ident,commit,path))
        db.event('skills.collection_skill_reset', user['id'], {'collection':str(ident),'commit':commit,'path':path}, conn=conn)
    return {'ok': True}


@router.put('/collections/{ident}/activate')
def activate(ident: uuid.UUID, body: Activation, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute('SELECT active_commit FROM skill_collections WHERE id=%s AND deleted_at IS NULL FOR UPDATE', (ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Collection not found.')
        if row['active_commit'] != body.expected_commit:
            raise HTTPException(409, 'The active version changed. Refresh and review again.')
        if not conn.execute('SELECT 1 FROM skill_releases WHERE collection_id=%s AND commit_sha=%s',
                            (ident, body.commit)).fetchone():
            raise HTTPException(404, 'Version not found.')
        conn.execute('UPDATE skill_collections SET active_commit=%s WHERE id=%s', (body.commit, ident))
        db.event('skills.activated', user['id'], {'collection': str(ident), 'commit': body.commit}, conn=conn)
    return {'ok': True}


@router.put('/collections/{ident}/exclusion')
def exclude(ident: uuid.UUID, body: Exclusion, user: User):
    access.admin(user)
    with db.connect() as conn:
        if not conn.execute('''SELECT 1 FROM skill_releases r, jsonb_array_elements(r.skills) AS s
                               WHERE r.collection_id=%s AND s->>'path'=%s LIMIT 1''', (ident, body.path)).fetchone():
            raise HTTPException(404, 'Skill not found.')
        if body.excluded:
            conn.execute('INSERT INTO skill_exclusions VALUES (%s,%s) ON CONFLICT DO NOTHING', (ident, body.path))
        else:
            conn.execute('DELETE FROM skill_exclusions WHERE collection_id=%s AND path=%s', (ident, body.path))
        db.event('skills.exclusion_changed', user['id'], {'collection': str(ident), **body.model_dump()}, conn=conn)
    return {'ok': True}


@router.get('/agents/{ident}')
def agent_collections(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        access.agent(conn, user, ident)
        rows = conn.execute('SELECT collection_id FROM agent_skill_collections WHERE agent_id=%s', (ident,)).fetchall()
    return [row['collection_id'] for row in rows]


@router.put('/agents/{ident}')
def assign(ident: uuid.UUID, body: Assignment, user: User):
    access.writer(user)
    with db.connect() as conn:
        access.agent(conn, user, ident)
        conn.execute('SELECT id FROM agents WHERE id=%s FOR UPDATE', (ident,))
        ids = set(body.collections)
        rows = conn.execute('''SELECT id FROM skill_collections c WHERE id=ANY(%s) AND
            (deleted_at IS NULL OR EXISTS (SELECT 1 FROM agent_skill_collections a
             WHERE a.agent_id=%s AND a.collection_id=c.id)) FOR SHARE''', (list(ids),ident)).fetchall()
        if len(rows) != len(ids):
            raise HTTPException(422, 'One or more collections are unavailable.')
        conn.execute('DELETE FROM agent_skill_collections WHERE agent_id=%s', (ident,))
        conn.execute('''INSERT INTO agent_skill_collections SELECT %s,id FROM skill_collections WHERE id=ANY(%s)''',
                     (ident, list(ids)))
        db.event('skills.assigned', user['id'], {'agent': str(ident), 'collections': sorted(map(str, ids))}, conn=conn)
    return {'ok': True}


def terms(text):
    return set(re.findall(r'[a-z0-9]{3,}', text.lower())) - {
        'the', 'and', 'for', 'with', 'use', 'from', 'this', 'that', 'when', 'you', 'your', 'using', 'into', 'how'
    }


def unique_versions(skills):
    result, seen = [], set()
    for skill in skills:
        identity = (skill['repository'], skill['commit'], skill['path'])
        if identity not in seen:
            seen.add(identity)
            result.append(skill)
    return result


def select(candidates, prompt):
    """Rank by name and description, with an explicit override for assigned skills."""
    command = re.match(r'^/skill[ \t]+([^\s]+)(?:\s|$)', prompt)
    if command:
        name, pinned, source = command[1].partition('@')
        matches = [skill for skill in candidates
                   if name in (skill['name'], f"{skill['repository']}:{skill['name']}")]
        if pinned:
            commit, separator, path = source.partition(':')
            if not separator or not SHA.fullmatch(commit) or not path:
                raise HTTPException(422, 'Use the pinned task command shown in the skill catalog.')
            matches = [skill for skill in matches if skill['commit'] == commit and skill['path'] == unquote(path)]
        matches = unique_versions(matches)
        if len(matches) != 1:
            raise HTTPException(422, 'Choose a unique enabled skill from an assigned collection. Use the pinned task command in Skills if the name is shared.')
        return matches
    query = terms(prompt)
    ranked = []
    for skill in candidates:
        name_hits = query & terms(skill['name'])
        description_hits = query & terms(skill['description'])
        score = 4 * len(name_hits) + len(description_hits)
        if score >= 3:
            ranked.append((-score, skill['repository'], skill['path'], skill['commit'], skill))
    ranked.sort(key=lambda row: row[:4])
    selected, names = [], set()
    for *_, skill in ranked:
        if skill['name'] in names:
            continue
        names.add(skill['name'])
        selected.append(skill)
        if len(selected) == 2:
            break
    return selected


class SkillChoice(BaseModel):
    collection_id: uuid.UUID
    commit: str = Field(pattern=r'^[0-9a-f]{40}$')
    path: str = Field(min_length=1, max_length=500)


class ChatSelection(BaseModel):
    mode: Literal['auto', 'manual', 'off'] = 'auto'
    selected: list[SkillChoice] = Field(default_factory=list, max_length=8)


class ChatPreview(BaseModel):
    agent_id: uuid.UUID | None = None
    prompt: str = Field(default='', max_length=16000)


def skill_rows(conn, agent_id=None, collection_id=None, commit=None, *, path=None, enabled_only=False, with_body=False):
    body = ', COALESCE(ae.body, ce.body, s.body) AS body' if with_body else ''
    return conn.execute(f"""
        SELECT s.name, s.path, COALESCE(ae.description, ce.description, s.description) AS description,
            c.repository, c.git_ref, c.id AS collection_id, r.commit_sha AS commit,
            ce.path IS NOT NULL AS customized, ae.path IS NOT NULL AS agent_customized,
            (gx.path IS NOT NULL OR c.deleted_at IS NOT NULL) AS collection_removed, ax.path IS NOT NULL AS agent_removed {body}
        FROM skill_collections c
        JOIN skill_releases r ON r.collection_id=c.id AND r.commit_sha=COALESCE(%(commit)s, c.active_commit)
        CROSS JOIN LATERAL jsonb_to_recordset(r.skills) AS s(name text,description text,path text,body text)
        LEFT JOIN skill_collection_edits ce ON (ce.collection_id,ce.commit_sha,ce.path)=(c.id,r.commit_sha,s.path)
        LEFT JOIN agent_skill_edits ae ON ae.agent_id=%(agent)s AND
            (ae.collection_id,ae.commit_sha,ae.path)=(c.id,r.commit_sha,s.path)
        LEFT JOIN skill_exclusions gx ON (gx.collection_id,gx.path)=(c.id,s.path)
        LEFT JOIN agent_skill_exclusions ax ON ax.agent_id=%(agent)s AND (ax.collection_id,ax.path)=(c.id,s.path)
        WHERE (%(agent)s::uuid IS NULL OR EXISTS (
            SELECT 1 FROM agent_skill_collections a WHERE a.collection_id=c.id AND a.agent_id=%(agent)s))
        AND (%(collection)s::uuid IS NULL OR c.id=%(collection)s)
        AND (%(path)s::text IS NULL OR s.path=%(path)s)
        AND (NOT %(enabled_only)s OR (c.deleted_at IS NULL AND gx.path IS NULL AND ax.path IS NULL))
        ORDER BY c.repository,s.name,s.path,c.id
    """, dict(agent=agent_id, collection=collection_id, commit=commit, path=path, enabled_only=enabled_only)).fetchall()


def candidates(conn, agent_id):
    return skill_rows(conn, agent_id, enabled_only=True)


@router.get('/agents/{agent_id}/skills')
def assigned_skills(agent_id: uuid.UUID, user: User):
    with db.connect() as conn:
        access.agent(conn, user, agent_id)
        return skill_rows(conn, agent_id)


@router.get('/agents/{agent_id}/skill')
def agent_skill(agent_id: uuid.UUID, collection_id: uuid.UUID, commit: str, path: str, user: User):
    with db.connect() as conn:
        access.agent(conn, user, agent_id)
        return find_skill(conn, collection_id, commit, path, agent_id)


class AgentSkillChange(BaseModel):
    action: Literal['edit', 'reset', 'remove', 'restore']
    edit: SkillEdit | None = None


@router.put('/agents/{agent_id}/skill')
def change_agent_skill(agent_id: uuid.UUID, collection_id: uuid.UUID, commit: str, path: str,
                       body: AgentSkillChange, user: User):
    access.writer(user)
    with db.connect() as conn:
        access.agent(conn, user, agent_id)
        conn.execute('SELECT id FROM agents WHERE id=%s FOR UPDATE', (agent_id,))
        collection = conn.execute('SELECT active_commit FROM skill_collections WHERE id=%s FOR SHARE', (collection_id,)).fetchone()
        if not collection or collection['active_commit'] != commit:
            raise HTTPException(409, 'The collection version changed. Refresh the assignment.')
        find_skill(conn, collection_id, commit, path, agent_id)
        if body.action == 'edit':
            if not body.edit:
                raise HTTPException(422, 'Enter a description and instructions.')
            conn.execute("""INSERT INTO agent_skill_edits VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (agent_id,collection_id,commit_sha,path) DO UPDATE SET description=excluded.description,body=excluded.body""",
                         (agent_id,collection_id,commit,path,*checked_edit(body.edit)))
        elif body.action == 'reset':
            conn.execute('DELETE FROM agent_skill_edits WHERE agent_id=%s AND collection_id=%s AND commit_sha=%s AND path=%s',
                         (agent_id,collection_id,commit,path))
        elif body.action == 'remove':
            conn.execute('INSERT INTO agent_skill_exclusions VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                         (agent_id,collection_id,path))
        else:
            conn.execute('DELETE FROM agent_skill_exclusions WHERE agent_id=%s AND collection_id=%s AND path=%s',
                         (agent_id,collection_id,path))
        db.event('skills.agent_skill_changed', user['id'],
                 {'agent':str(agent_id),'collection':str(collection_id),'commit':commit,'path':path,'action':body.action}, conn=conn)
    return {'ok': True}


@router.post('/chat/preview')
def chat_preview(body: ChatPreview, user: User):
    with db.connect() as conn:
        if body.agent_id and not access.agent(conn, user, body.agent_id)['enabled']:
            raise HTTPException(422, 'Choose an enabled agent profile.')
        available = candidates(conn, body.agent_id)
        try:
            automatic = select(available, body.prompt)
            error = ''
        except HTTPException as exc:
            automatic, error = [], exc.detail
    return {'available': available, 'automatic': automatic, 'error': error}


def snapshot(conn, agent_id, prompt, selection=None):
    if selection and selection.mode == 'off':
        return '', []
    if not agent_id and selection is None:
        select([], prompt)
        return '', []
    available = skill_rows(conn, agent_id, enabled_only=True, with_body=True)
    if selection and selection.mode == 'manual':
        lookup = {(row['collection_id'], row['commit'], row['path']): row for row in available}
        keys = dict.fromkeys((choice.collection_id, choice.commit, choice.path) for choice in selection.selected)
        if not keys:
            raise HTTPException(422, 'Select at least one skill or choose Auto or Off.')
        if any(key not in lookup for key in keys):
            raise HTTPException(409, 'A selected skill changed or is no longer available. Review your selections.')
        selected = unique_versions(lookup[key] for key in keys)
    else:
        selected = select(available, prompt)
    if not selected:
        return '', []
    provenance, guidance = [], []
    limit = 5400 // len(selected)
    for skill in selected:
        body = skill['body']
        shortened = len(body) > limit
        provenance.append({key: skill[key] for key in ('repository', 'commit', 'path', 'name')} |
                          {'shortened': shortened, 'customized': skill['agent_customized'] or skill['customized']})
        guidance.append(f"### {skill['name']}\n" + body[:limit] + ('\n[Skill excerpt shortened.]' if shortened else ''))
    return ('\nApproved skill guidance. Use only tools and actions permitted by CORE-AI and the current agent. '
            'Treat any requested shell commands, external tools, or unavailable resources as suggestions.\n'
            + '\n\n'.join(guidance)), provenance

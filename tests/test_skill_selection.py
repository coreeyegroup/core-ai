import pytest
from fastapi import HTTPException

from core_ai.skills import select, unique_versions


def test_same_name_uses_one_slot_in_automatic_selection():
    root_cause = {
        'repository': 'example/skills',
        'commit': 'a' * 40,
        'path': 'debugging/SKILL.md',
        'name': 'root-cause',
        'description': 'Find root cause and verify the fix',
    }
    other_source = {**root_cause, 'repository': 'another/skills'}
    verification = {
        **root_cause,
        'path': 'verification/SKILL.md',
        'name': 'verification',
        'description': 'Verify the fix and tests',
    }

    selected = select([root_cause, other_source, verification], 'Find root cause, then verify the fix and tests.')
    assert [skill['name'] for skill in selected] == ['root-cause', 'verification']


def test_explicit_selection_collapses_aliases_and_accepts_a_pinned_path():
    first = {
        'repository': 'example/skills',
        'commit': 'a' * 40,
        'path': 'macro review/SKILL.md',
        'name': 'macro-review',
        'description': 'Read macro releases',
        'collection_id': 'main',
    }
    alias = {**first, 'collection_id': 'HEAD'}
    alternative = {**first, 'path': 'other/SKILL.md'}
    command = '/skill example/skills:macro-review'
    assert unique_versions([first, alias, alternative]) == [first, alternative]
    assert select([first, alias], command) == [first]
    with pytest.raises(HTTPException, match='pinned task command') as error:
        select([first, alias, alternative], command)
    assert error.value.status_code == 422
    pinned = f"{command}@{first['commit']}:macro%20review%2FSKILL.md"
    assert select([first, alias, alternative], pinned + '\nReview the inputs') == [first]

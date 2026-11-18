import importlib.util
from pathlib import Path
import pytest
from core_ai.auth import password_ok

spec=importlib.util.spec_from_file_location('login_reset',Path(__file__).resolve().parents[1]/'scripts/login.py')
login=importlib.util.module_from_spec(spec);spec.loader.exec_module(login)

def test_explicit_six_character_password_is_compatible_with_existing_login():
    payload=login.prepare('Example','abc123')
    assert payload['username']=='example'
    assert password_ok('abc123',payload['password_hash'])
    assert not password_ok('incorrect',payload['password_hash'])
    assert 'password' not in payload
    assert 'abc123' not in repr(payload)
    assert login.prepare('example','abc123')['password_hash']!=payload['password_hash']

@pytest.mark.parametrize('username,password',[('bad username','abc123'),('valid','short'),('valid','abc\n123')])
def test_invalid_reset_does_not_prepare_credentials(username,password):
    with pytest.raises(ValueError):login.prepare(username,password)

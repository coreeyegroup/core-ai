import base64
import socket
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from core_ai import external_connections as external


@pytest.mark.parametrize('provider, endpoint, method, mode', [
    ('http', 'http://api.example.org/data', 'GET', 'none'),
    ('http', 'https://user:password@api.example.org/data', 'GET', 'none'),
    ('http', 'https://api.example.org/data?access_token=secret', 'GET', 'bearer'),
    ('http', 'https://api.example.org:8080/data', 'GET', 'none'),
    ('upstox', 'https://api.upstox.com/v2/order/place', 'POST', 'bearer'),
    ('corei', 'https://example.org/api/md/latest', 'GET', 'bearer'),
    ('instagram', 'https://other.example.org/v27.0/me/media', 'GET', 'bearer'),
])
def test_validate_provider_operation(provider, endpoint, method, mode):
    with pytest.raises(HTTPException) as error:
        external.validated_url(provider, endpoint, method, mode, '')
    assert error.value.status_code == 422


@pytest.mark.parametrize('host', ['127.0.0.1', '169.254.169.254', '10.0.0.1', '::1', '::ffff:127.0.0.1'])
def test_pinning_rejects_non_public_addresses(monkeypatch, host):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *_a, **_k: [(0, 0, 0, '', (host, 443))])
    with pytest.raises(external.UpstreamError) as error:
        external.public_address('example.org')
    assert error.value.outcome == 'destination_blocked'


def test_encrypted_credentials_support_long_values_and_are_bound_to_connection(monkeypatch):
    monkeypatch.setenv(external.key_storage.ENV_KEY, base64.b64encode(b'test key material' * 16).decode())
    ident = uuid4()
    value = 'synthetic-credential-' * 90
    encrypted = external.encrypt(ident, value)
    assert value.encode() not in encrypted
    assert external.decrypt(ident, encrypted) == value
    with pytest.raises(HTTPException):
        external.decrypt(uuid4(), encrypted)


def test_request_uses_checked_ip_and_preserves_tls_name(monkeypatch):
    monkeypatch.setattr(external, 'public_address', lambda _: '93.184.215.14')
    real_client = httpx.Client

    def respond(request):
        assert request.url.host == '93.184.215.14'
        assert request.headers['host'] == 'api.twelvedata.com'
        assert request.extensions['sni_hostname'] == 'api.twelvedata.com'
        assert request.headers['authorization'] == 'apikey fixture-token'
        return httpx.Response(200, stream=httpx.ByteStream(b'{"close":1.25,"access_token":"other","echo":"fixture-token"}'))

    monkeypatch.setattr(external.httpx, 'Client', lambda **settings: real_client(transport=httpx.MockTransport(respond), **settings))
    url = external.validated_url('twelvedata', 'https://api.twelvedata.com/time_series?symbol=EUR%2FUSD', 'GET', 'apikey', '')
    status, data = external.send(url, 'GET', external.request_headers('apikey', '', 'fixture-token'), 'fixture-token', None)
    assert status == 200
    assert data == {'close': 1.25, 'access_token': '[redacted]', 'echo': '[redacted]'}


def test_snapshot_selector_limits_a_nested_array():
    data = {'payload': {'items': [{'price': 1}, {'price': 2}]}}
    assert external.source_payload(data, 'payload.items', 1) == [{'price': 1}]
    with pytest.raises(ValueError, match='path'):
        external.source_payload(data, 'payload.missing', 1)
    with pytest.raises(ValueError, match='array'):
        external.source_payload(data, 'payload', 1)


@pytest.mark.parametrize('path', [
    '/v3/market-quote/ltp?instrument_key=NSE_INDEX%7CNifty%2050',
    '/v3/market-quote/quotes?instrument_key=NSE_EQ%7CTEST',
    '/v3/market-quote/option-greek?instrument_key=NSE_FO%7C123',
    '/v3/historical-candle/intraday/NSE_INDEX%7CNifty%2050/minutes/5',
    '/v3/historical-candle/NSE_EQ%7CTEST/days/1/2026-11-23',
    '/v2/order/retrieve-all', '/v2/portfolio/short-term-positions',
])
def test_upstox_read_recipes(path):
    result = external.validated_url('upstox', 'https://api.upstox.com'+path, 'GET', 'bearer', '')
    assert result.host == 'api.upstox.com'


def test_saved_requests_share_one_encrypted_token_and_can_rotate_it(monkeypatch):
    monkeypatch.setenv(external.key_storage.ENV_KEY, base64.b64encode(b'fixture encryption key' * 4).decode())
    ident = uuid4()
    body = external.ExternalConnection(
        name='Trading data', provider='upstox', auth='bearer',
        endpoint='https://api.upstox.com/v2/user/profile', secret='fixture-upstox-access',
        requests=[
            {'name': 'LTP', 'endpoint': 'https://api.upstox.com/v3/market-quote/ltp?instrument_key=NSE_EQ%7CTEST'},
            {'name': 'Positions', 'endpoint': 'https://api.upstox.com/v2/portfolio/short-term-positions'},
        ],
    )
    original = external.save_fields(ident, body)
    assert [row['name'] for row in original[-1].obj] == ['LTP', 'Positions']
    assert external.decrypt(ident, original[6]) == 'fixture-upstox-access'
    previous = dict(zip(('name', 'provider', 'endpoint', 'method', 'auth', 'header_name', 'secret', 'paused'), original))
    previous['requests'] = original[-1].obj
    replacement = body.model_copy(update={'secret': external.SecretStr('new-upstox-access'), 'requests': None})
    rotated = external.save_fields(ident, replacement, previous)
    assert rotated[-1].obj == original[-1].obj
    assert external.decrypt(ident, rotated[6]) == 'new-upstox-access'


def test_generic_read_credential_is_not_shared_with_other_hosts(monkeypatch):
    monkeypatch.setenv(external.key_storage.ENV_KEY, base64.b64encode(b'fixture encryption key' * 4).decode())
    body = external.ExternalConnection(
        name='Public service', provider='http', auth='bearer',
        endpoint='https://api.example.org/read', secret='fixture-access-token',
        requests=[{'name': 'Other service', 'endpoint': 'https://other.example.org/read'}],
    )
    with pytest.raises(HTTPException, match='hostname'):
        external.save_fields(uuid4(), body)


def test_kite_key_and_token_match_provider_contract():
    url = external.validated_url('zerodha', 'https://api.kite.trade/quote?i=NSE%3AINFY', 'GET', 'kite', '')
    assert url.host == 'api.kite.trade'
    headers = external.request_headers('kite', '', '["fixture-api-key","fixture-access"]')
    assert headers['Authorization'] == 'token fixture-api-key:fixture-access'
    assert headers['X-Kite-Version'] == '3'
    with pytest.raises(HTTPException):
        external.validated_url('zerodha', 'https://api.kite.trade/orders/regular', 'POST', 'kite', '')


def test_angel_read_post_and_network_headers_are_explicit(monkeypatch):
    for key, value in {'LOCAL_IP': '192.0.2.2', 'PUBLIC_IP': '198.51.100.5', 'MAC': '02:00:00:00:01:03'}.items():
        monkeypatch.setenv('CORE_AI_ANGEL_' + key, value)
    endpoint = 'https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote'
    assert external.request_method('angelone', endpoint) == 'POST'
    assert external.validated_url('angelone', endpoint, 'POST', 'angel', '').host == 'apiconnect.angelone.in'
    headers = external.request_headers('angel', '', '["fixture-api-key","fixture-access"]')
    assert headers['X-PrivateKey'] == 'fixture-api-key'
    assert headers['Authorization'] == 'Bearer fixture-access'
    assert headers['X-ClientPublicIP'] == '198.51.100.5'
    order_endpoint = 'https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder'
    with pytest.raises(HTTPException):
        external.validated_url('angelone', order_endpoint, 'POST', 'angel', '')


def test_mt5_bridge_is_an_independent_read_provider():
    endpoint = 'https://bridge.example.org/bars'
    assert external.validated_url('mt5', endpoint, 'GET', 'bearer', '').host == 'bridge.example.org'
    with pytest.raises(HTTPException):
        external.validated_url('mt5', endpoint, 'POST', 'bearer', '')



def test_angel_quote_body_keeps_exchange_instrument_tokens(monkeypatch):
    monkeypatch.setenv(external.key_storage.ENV_KEY, base64.b64encode(b'fixture encryption key' * 4).decode())
    request = {
        'name': 'NSE quote', 'endpoint': 'https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote',
        'body': {'mode': 'FULL', 'exchangeTokens': {'NSE': ['123']}},
    }
    profile = external.ExternalConnection(
        name='Angel data', provider='angelone', auth='angel',
        endpoint='https://apiconnect.angelone.in/rest/secure/angelbroking/user/v1/getProfile',
        api_key='fixture-app-key', secret='fixture-session-token', requests=[request],
    )
    assert external.save_fields(uuid4(), profile)[-1].obj == [request]
    result = {'data': {'symbolToken': '123'}, 'accessToken': 'not-an-instrument'}
    assert external.redact(result, '') == {'data': {'symbolToken': '123'}, 'accessToken': '[redacted]'}

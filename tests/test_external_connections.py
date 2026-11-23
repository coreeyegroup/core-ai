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

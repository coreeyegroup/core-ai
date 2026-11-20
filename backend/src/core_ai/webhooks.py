"""Deliver signed job events to HTTPS destinations provisioned by the server operator."""
import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlsplit

import httpx

from . import db

PREFIX = 'CORE_AI_WEBHOOK_'
DESTINATION_PATTERN = r'^[A-Z][A-Z0-9_]{0,63}$'
MAX_ATTEMPTS = 3


def destinations():
    configured = {}
    for name, url in os.environ.items():
        if not name.startswith(PREFIX) or not name.endswith('_URL'):
            continue
        destination = name[len(PREFIX):-4]
        secret = os.environ.get(f'{PREFIX}{destination}_SECRET', '')
        if not re.fullmatch(DESTINATION_PATTERN, destination) or len(secret) < 32:
            continue
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.fragment or parsed.port not in (None,443)):
                continue
            parsed_url = httpx.URL(url)
            if parsed_url.scheme == 'https' and parsed_url.host:
                configured[destination] = (parsed_url, secret)
        except (ValueError,httpx.InvalidURL):
            continue
    return configured


def claim():
    with db.connect() as conn:
        item = conn.execute("""
            SELECT d.run_id,d.destination,d.attempts,r.connection_id,r.request_id,r.model,
                   r.status AS job_status,r.finished_at,
                   coalesce(c.revoked_at IS NULL AND NOT c.paused AND c.webhook_destination=d.destination
                       AND (c.expires_at IS NULL OR c.expires_at>now()) AND u.enabled AND u.role='ADMIN',false) AS enabled
            FROM automation_webhook_deliveries d JOIN runs r ON r.id=d.run_id
            LEFT JOIN automation_connections c ON c.id=r.connection_id LEFT JOIN users u ON u.id=c.created_by
            WHERE d.status='PENDING' AND d.next_attempt_at<=now()
              AND r.status IN ('SUCCEEDED','FAILED','CANCELLED')
            ORDER BY d.next_attempt_at,d.run_id LIMIT 1 FOR UPDATE OF d SKIP LOCKED
        """).fetchone()
        if item is None:
            return None
        if not item['enabled']:
            conn.execute("UPDATE automation_webhook_deliveries SET status='CANCELLED',updated_at=now() WHERE run_id=%s",
                         (item['run_id'],))
            return None
        if item['attempts'] >= MAX_ATTEMPTS:
            conn.execute("UPDATE automation_webhook_deliveries SET status='FAILED',updated_at=now() WHERE run_id=%s",
                         (item['run_id'],))
            return None
        item['attempts'] += 1
        conn.execute("""
            UPDATE automation_webhook_deliveries
            SET attempts=%s,next_attempt_at=now()+interval '30 seconds',updated_at=now() WHERE run_id=%s
        """,(item['attempts'],item['run_id']))
        return item


def deliver(item, configured):
    destination = configured.get(item['destination'])
    if destination is None:
        return 'FAILED'
    url, secret = destination
    job_id = str(item['run_id'])
    event = {
        'id': job_id, 'type': 'job.finished',
        'data': {'id': job_id, 'request_id': item['request_id'], 'model': item['model'],
                 'status': item['job_status'], 'finished_at': item['finished_at'].isoformat()},
    }
    payload = json.dumps(event, separators=(',', ':')).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), stamp.encode()+b'.'+payload, hashlib.sha256).hexdigest()
    headers = {'Content-Type':'application/json', 'X-Core-AI-Timestamp':stamp, 'X-Core-AI-Signature':'sha256='+signature}
    try:
        # Do not follow redirects or read response bodies. URLs and secrets are provisioned outside the API.
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            with client.stream('POST',url,content=payload,headers=headers) as response:
                if response.is_success:
                    return 'DELIVERED'
                if response.status_code not in (408,429) and response.status_code<500:
                    return 'FAILED'
    except httpx.RequestError:
        pass
    return 'FAILED' if item['attempts'] >= MAX_ATTEMPTS else 'PENDING'


def run(stopping):
    while not stopping.is_set():
        try:
            item = claim()
            if item is not None:
                status = deliver(item,destinations())
                db.query("""
                    UPDATE automation_webhook_deliveries SET status=%s,updated_at=now()
                    WHERE run_id=%s AND attempts=%s AND status='PENDING'
                """,(status,item['run_id'],item['attempts']))
                continue
        except Exception:
            # Database interruptions can be retried. Never log callback URLs, signing keys or bodies.
            pass
        stopping.wait(2)

"""Run against a disposable PostgreSQL database with simulated broker responses."""
import base64
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException

from core_ai import db, external_connections as broker


@pytest.mark.skipif(not os.getenv('CORE_AI_TEST_BROKER_DB'), reason='Requires a disposable PostgreSQL database')
def test_independent_broker_task_and_order(monkeypatch):
    monkeypatch.setenv('CORE_AI_DATABASE_URL', os.environ['CORE_AI_TEST_BROKER_DB'])
    monkeypatch.setenv(broker.key_storage.ENV_KEY, base64.b64encode(os.urandom(32)).decode())
    db.migrate()
    user = {'id': uuid4(), 'role': 'ADMIN'}
    project, lead, specialist = uuid4(), uuid4(), uuid4()
    with db.connect() as conn:
        conn.execute('INSERT INTO users(id,username,password_hash) VALUES (%s,%s,%s)', (user['id'],str(user['id']),'fixture'))
        conn.execute("INSERT INTO projects(id,name) VALUES (%s,'fixture')", (project,))
        for agent in (lead, specialist):
            conn.execute("INSERT INTO agents(id,name,instructions,owner_id) VALUES (%s,'fixture','fixture',%s)", (agent,user['id']))
    profile = broker.ExternalConnection(name='Broker fixture', provider='upstox', auth='bearer',
        endpoint='https://api.upstox.com/v2/user/profile', upstox_app_key='sample-app-id',
        upstox_app_secret='sample-app-secret', secret='sample-session-token')
    ident = broker.create_external(profile,user)['id']
    keys = ['NSE_EQ|INE000000001','NSE_EQ|INE000000002']
    orders = []
    def transport(url, method, headers, credential, payload):
        if url.path.endswith('/quotes'):
            assert url.params['instrument_key'] == ','.join(keys)
            return 200, {'data':{key:{'last_price':123,'instrument_token':key} for key in keys}}
        if url.path.endswith('/retrieve-all'):
            return 200, {'data':[{'order_id':'fixture-order','instrument_token':keys[0],
                                   'status':'complete','filled_quantity':1,'average_price':123}]}
        if url.path.endswith('/profile'):
            return 200, {'data':{'user_id':'fixture-account'}}
        assert url.host == 'api-hft.upstox.com' and method == 'POST'
        orders.append(payload)
        if len(orders) > 1:
            raise broker.UpstreamError('timeout')
        return 200, {'data':{'order_ids':['fixture-order']}}
    monkeypatch.setattr(broker,'send',transport)
    task = broker.start_analysis(ident,broker.AnalysisTask(project_id=project,agent_id=lead,
        instruments=keys,goal='Review coverage',specialist_ids=[specialist]),user)['id']
    ticket = broker.LiveLimitOrder(run_id=task,instrument=keys[0],account_id='fixture-account',
                                    price=123,quantity=1,side='BUY',product='D',confirmed=True)
    with pytest.raises(HTTPException):
        broker.submit_live_limit(ident,ticket,user)
    def finish():
        with db.connect() as conn:
            conn.execute("UPDATE runs SET status='SUCCEEDED',output='fixture analysis' WHERE project_id=%s", (project,))
    finish()
    assert broker.review_analysis(ident,task,user)['status']=='Master review queued'
    finish()
    assert broker.review_analysis(ident,task,user)['status']=='SUCCEEDED'
    with pytest.raises(HTTPException):
        broker.submit_live_limit(ident,ticket.model_copy(update={'account_id':'wrong-account'}),user)
    for _ in range(2):
        assert broker.submit_live_limit(ident,ticket,user)['broker_order_id']=='fixture-order'
    for _ in range(2):
        assert broker.submit_live_limit(ident,ticket.model_copy(update={'instrument':keys[1]}),user)['status']=='PENDING_RECONCILIATION'
    observed = broker.lookup_limit(ident,broker.OrderLookup(run_id=task,instrument=keys[0]),user)
    assert observed['status']=='complete' and observed['filled_quantity']==1
    assert len(orders)==2

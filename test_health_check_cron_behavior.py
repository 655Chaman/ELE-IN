import os, sys, asyncio
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
os.environ["SUPABASE_URL"] = "http://localhost:8000"
os.environ["SUPABASE_KEY"] = "mock_key"

import sys as _sys
mock_config = MagicMock()
_sys.modules['core.backend.core.config'] = mock_config

from core.backend.services.health_check_cron import run_health_checks

class DummyResponse:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count

def get_mock_supabase(accounts=None, proxies=None, machine_sent=10, logged_actions=10):
    mock_supabase = MagicMock()
    
    # Track update calls globally for assertion
    update_calls = []
    
    def table_mock(name):
        m = MagicMock()
        if name == "accounts":
            m.select().eq().execute.return_value = DummyResponse(accounts or [])
            m.select().in_().eq().execute.return_value = DummyResponse(accounts or [])
        elif name == "proxies":
            m.select().in_().execute.return_value = DummyResponse(proxies or [])
            m.select().eq().execute.return_value = DummyResponse(proxies or [])
        elif name == "account_daily_action_counts":
            m.select().eq().eq().eq().execute.return_value = DummyResponse([{"count": machine_sent}])
        elif name == "action_log":
            m.select().eq().ilike().gte().execute.return_value = DummyResponse([{"id": "log1"}], count=logged_actions)
        elif name == "workspaces":
            m.select().eq().execute.return_value = DummyResponse([{"owner_id": "owner-1"}])
        elif name == "campaigns":
            m.select().eq().execute.return_value = DummyResponse([{"id": "camp-1", "name": "Camp 1"}])
        elif name == "campaign_accounts":
            m.select().eq().execute.return_value = DummyResponse([{"account_id": "acc-1"}])
        
        def update_mock(data):
            update_calls.append((name, data))
            ret = MagicMock()
            ret.eq().execute.return_value = DummyResponse([{}])
            return ret
            
        def insert_mock(data):
            update_calls.append((name, data))
            ret = MagicMock()
            ret.execute.return_value = DummyResponse([{}])
            return ret
            
        m.update.side_effect = update_mock
        m.insert.side_effect = insert_mock
        return m
        
    mock_supabase.table.side_effect = table_mock
    mock_supabase.update_calls = update_calls
    return mock_supabase

@patch('core.backend.services.health_check_cron.get_service_client')
@patch('core.backend.services.health_check_cron.LinkedInWorker')
@patch('core.backend.services.health_check_cron.capture_error', create=True)
def test_health_check_valid_session(mock_capture_error, mock_worker_cls, mock_get_client):
    accounts = [{"id": "acc-1", "name": "Acc 1", "session_cookies_encrypted": '{"cookies": 1}', "proxy_id": "px-1", "workspace_id": "ws-1"}]
    proxies = [{"id": "px-1", "host": "proxy1", "port": 80, "username": "u1", "protocol": "http", "status": "healthy", "country_code": "US"}]
    mock_supabase = get_mock_supabase(accounts=accounts, proxies=proxies, machine_sent=10, logged_actions=10)
    mock_get_client.return_value = mock_supabase
    
    mock_worker = MagicMock()
    mock_worker.check_session_valid.return_value = True
    mock_worker_cls.return_value = mock_worker
    
    run_health_checks()
    
    updated = False
    for table_name, data in mock_supabase.update_calls:
        if table_name == "accounts" and "last_health_check_at" in data:
            updated = True
    assert updated, "last_health_check_at was not updated"
    
@patch('core.backend.services.health_check_cron.get_service_client')
@patch('core.backend.services.health_check_cron.LinkedInWorker')
@patch('core.backend.services.health_check_cron.capture_error', create=True)
def test_health_check_manual_send_anomaly(mock_capture_error, mock_worker_cls, mock_get_client):
    accounts = [{"id": "acc-1", "name": "Acc 1", "session_cookies_encrypted": '{"cookies": 1}', "proxy_id": "px-1", "workspace_id": "ws-1"}]
    mock_supabase = get_mock_supabase(accounts=accounts, machine_sent=10, logged_actions=20) # 20 > 10 * 1.3
    mock_get_client.return_value = mock_supabase
    
    mock_worker = MagicMock()
    mock_worker.check_session_valid.return_value = True
    mock_worker_cls.return_value = mock_worker
    
    run_health_checks()
    
    anomaly_updated = False
    for table_name, data in mock_supabase.update_calls:
        if table_name == "accounts" and data.get("manual_send_suspected") == True:
            anomaly_updated = True
    
    assert anomaly_updated, "Anomaly detection failed to update account"

@patch('core.backend.services.health_check_cron.get_service_client')
@patch('core.backend.services.health_check_cron.LinkedInWorker')
@patch('core.backend.services.health_check_cron._send_disconnect_email')
@patch('core.backend.services.health_check_cron.capture_error', create=True)
def test_health_check_invalid_session_disconnect(mock_capture_error, mock_email, mock_worker_cls, mock_get_client):
    accounts = [{"id": "acc-1", "name": "Acc 1", "session_cookies_encrypted": '{"cookies": 1}', "proxy_id": "px-1", "workspace_id": "ws-1"}]
    
    mock_supabase = get_mock_supabase(accounts=accounts)
    
    # Overwrite the table mock just for this specific test where we want active_senders to be empty
    original_table_mock = mock_supabase.table.side_effect
    def custom_table_mock(name):
        m = original_table_mock(name)
        if name == "accounts":
            # For active accounts, return the account
            m.select().eq().execute.return_value = DummyResponse(accounts)
            # For active_senders, return empty
            m.select().in_().eq().execute.return_value = DummyResponse([])
        return m
    mock_supabase.table.side_effect = custom_table_mock
    
    mock_get_client.return_value = mock_supabase
    
    mock_worker = MagicMock()
    mock_worker.check_session_valid.return_value = False
    mock_worker_cls.return_value = mock_worker
    
    run_health_checks()
    
    disconnected = False
    paused_campaign = False
    
    for table_name, data in mock_supabase.update_calls:
        if table_name == "accounts" and data.get("status") == "DISCONNECTED":
            disconnected = True
        if table_name == "campaigns" and data.get("status") == "PAUSED":
            paused_campaign = True
            
    assert disconnected, "Account was not disconnected"
    assert paused_campaign, "Campaign was not paused"
    mock_email.assert_called_once()

if __name__ == "__main__":
    print("Testing test_health_check_valid_session...")
    test_health_check_valid_session()
    print("Testing test_health_check_manual_send_anomaly...")
    test_health_check_manual_send_anomaly()
    print("Testing test_health_check_invalid_session_disconnect...")
    test_health_check_invalid_session_disconnect()
    print("All health_check_cron tests passed!")

import os, sys, asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

os.environ["SUPABASE_URL"] = "http://localhost:8000"
os.environ["SUPABASE_KEY"] = "mock_key"

from integrations.backend.routers.extension import router, verify_extension_api_key
from fastapi import FastAPI, Depends

app = FastAPI()
app.include_router(router)
client = TestClient(app)

class DummyResponse:
    def __init__(self, data):
        self.data = data

def test_verify_extension_api_key_success():
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().execute.return_value = DummyResponse([{"workspace_id": "ws-123", "is_active": True}])
    workspace_id = verify_extension_api_key("valid_key", mock_supabase)
    assert workspace_id == "ws-123"
    mock_supabase.table().update.assert_called()

def test_verify_extension_api_key_invalid():
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().execute.return_value = DummyResponse([])
    try:
        verify_extension_api_key("invalid_key", mock_supabase)
        assert False, "Should raise HTTPException"
    except Exception as e:
        assert getattr(e, "status_code", None) == 401

def test_report_task_result_ownership_failure():
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().execute.return_value = DummyResponse([{"workspace_id": "other-ws"}])
    from integrations.backend.routers.extension import report_task_result
    from fastapi import HTTPException
    try:
        report_task_result("task-1", {"status": "success"}, "ws-123", mock_supabase)
        assert False, "Should raise HTTPException"
    except HTTPException as e:
        assert e.status_code == 403

def test_report_task_result_success():
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().execute.return_value = DummyResponse([{"workspace_id": "ws-123"}])
    from integrations.backend.routers.extension import report_task_result
    res = report_task_result("task-1", {"status": "success"}, "ws-123", mock_supabase)
    assert res == {"status": "ok"}
    mock_supabase.table().update.assert_called()
    args, kwargs = mock_supabase.table().update.call_args
    assert args[0]["status"] == "completed"

def test_report_task_result_error():
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().execute.return_value = DummyResponse([{"workspace_id": "ws-123"}])
    from integrations.backend.routers.extension import report_task_result
    res = report_task_result("task-1", {"status": "error", "error_detail": "Timeout"}, "ws-123", mock_supabase)
    assert res == {"status": "ok"}
    mock_supabase.table().update.assert_called()
    args, kwargs = mock_supabase.table().update.call_args
    assert args[0]["status"] == "error"
    assert args[0]["error_reason"] == "Timeout"

def test_get_extension_tasks():
    mock_supabase = MagicMock()
    
    mocks = {}
    def table_mock(name):
        if name in mocks:
            return mocks[name]
        m = MagicMock()
        mocks[name] = m
        if name == "campaigns":
            m.select().eq().execute.return_value = DummyResponse([{"id": "camp-1"}])
        elif name == "campaign_accounts":
            m.select().eq().execute.return_value = DummyResponse([{"account_id": "acc-1"}])
        elif name == "campaign_execution_states":
            chain_mock = MagicMock()
            chain_mock.execute.return_value = DummyResponse([{
                "id": "task-1",
                "current_node_id": "node-1",
                "campaign_enrollments": {
                    "campaign_id": "camp-1",
                    "leads": {
                        "linkedin_url": "https://linkedin.com/in/test",
                        "first_name": "Test"
                    }
                }
            }])
            for method in ["select", "eq", "lte", "limit"]:
                getattr(m, method).return_value = chain_mock
                getattr(chain_mock, method).return_value = chain_mock
                
            m.update.return_value.eq.return_value.execute.return_value = DummyResponse([{}])
        return m
        
    mock_supabase.table.side_effect = table_mock
    from integrations.backend.routers.extension import get_extension_tasks
    
    res = get_extension_tasks("acc-1", "ws-123", mock_supabase)
    assert len(res["tasks"]) == 1
    task = res["tasks"][0]
    assert task["task_id"] == "task-1"
    assert task["linkedin_url"] == "https://linkedin.com/in/test"
    
    # Assert that campaign_execution_states was updated
    mock_supabase.table("campaign_execution_states").update.assert_called()
    args, kwargs = mock_supabase.table("campaign_execution_states").update.call_args
    assert args[0]["status"] == "running"

if __name__ == "__main__":
    print("Testing verify_extension_api_key_success...")
    test_verify_extension_api_key_success()
    print("Testing verify_extension_api_key_invalid...")
    test_verify_extension_api_key_invalid()
    print("Testing report_task_result_ownership_failure...")
    test_report_task_result_ownership_failure()
    print("Testing report_task_result_success...")
    test_report_task_result_success()
    print("Testing report_task_result_error...")
    test_report_task_result_error()
    print("Testing get_extension_tasks...")
    test_get_extension_tasks()
    print("All extension tests passed!")

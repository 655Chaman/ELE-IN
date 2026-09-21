import sys, os
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('/Users/krdeeksha/Ele-in/backend/.env')

# Ensure we have the correct path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from core.backend.api.auth_dep import get_service_client
from core.backend.services.notification_service import dispatch_notification

import campaigns.backend.routers.master_view as mv

def get_workspace_stats_for_service(supabase, workspace_id: str):
    """
    Helper to bypass FastAPI Request dependency and get master_view stats for a workspace.
    """
    class MockRequest:
        headers = {}
    
    # Get a real user to bypass membership checks
    members = supabase.table('workspace_members').select('user_id').eq('workspace_id', workspace_id).execute()
    if not members.data:
        return None
    user_id = members.data[0]['user_id']
    
    original_get_user = mv.get_current_user_id
    try:
        mv.get_current_user_id = lambda req, sup: user_id
        req = mv.MasterViewRequest()
        stats = mv.get_master_view_stats(MockRequest(), req, supabase, workspace_id)
        return stats
    except Exception as e:
        print(f"Failed to get stats for {workspace_id}: {e}")
        return None
    finally:
        mv.get_current_user_id = original_get_user

def run_throttle_and_burnout_checks(supabase):
    print("Running Throttle & Burnout Checks (Task #2)...")
    workspaces_res = supabase.table('workspaces').select('id, status').eq('status', 'active').execute()
    
    for ws in workspaces_res.data:
        workspace_id = ws['id']
        print(f"Checking workspace: {workspace_id}")
        
        # Get default limits
        defaults_res = supabase.table('workspace_sending_defaults').select('default_daily_connection_limit').eq('workspace_id', workspace_id).execute()
        if not defaults_res.data:
            print(f"WS {workspace_id} has no defaults")
            continue
        limit = defaults_res.data[0]['default_daily_connection_limit']
        if limit <= 0:
            print(f"WS {workspace_id} limit <= 0")
            continue
            
        threshold = limit * 0.8  # 80% utilization
        
        # Get accounts
        accounts_res = supabase.table('accounts').select('id, name, status').eq('workspace_id', workspace_id).in_('status', ['ACTIVE', 'MANUAL_MODE']).execute()
        if not accounts_res.data:
            print(f"WS {workspace_id} no active accounts")
            continue
            
        # Get stats to check sentiment
        print(f"Fetching stats for WS {workspace_id}...")
        stats = get_workspace_stats_for_service(supabase, workspace_id)
        if not stats:
            print(f"WS {workspace_id} no stats")
            continue
            
        sentiment = stats.get('radar_stats', {}).get('Sentiment (Pos)', 0)
        
        # Determine if sentiment is "negative/declining" (e.g. < 40%)
        is_negative_sentiment = sentiment < 40
        
        for acc in accounts_res.data:
            acc_id = acc['id']
            # Check last 3 days of utilization
            three_days_ago = (datetime.utcnow() - timedelta(days=3)).date().isoformat()
            
            counts_res = supabase.table('account_daily_action_counts') \
                .select('usage_date, count') \
                .eq('account_id', acc_id) \
                .eq('action_type', 'connection_request') \
                .gte('usage_date', three_days_ago) \
                .execute()
            
            if len(counts_res.data) >= 3:
                # check if all 3 days are >= threshold
                high_utilization = all(c['count'] >= threshold for c in counts_res.data)
                
                if high_utilization and is_negative_sentiment:
                    # Trigger alert!
                    print(f"Triggering burnout alert for account {acc['name']} ({acc_id}) in WS {workspace_id}")
                    payload = {
                        "account_id": acc_id,
                        "account_name": acc['name'],
                        "message": f"Account has sustained >80% utilization for 3 days with low positive sentiment ({sentiment:.1f}%). Consider a cool-down."
                    }
                    dispatch_notification(
                        svc=supabase,
                        workspace_id=workspace_id,
                        event_type="account_needs_attention",
                        payload=payload
                    )

def run_daily_digest(supabase):
    print("Running Daily Digest (Task #3)...")
    workspaces_res = supabase.table('workspaces').select('id, status').eq('status', 'active').execute()
    
    for ws in workspaces_res.data:
        workspace_id = ws['id']
        print(f"Generating Captain's Brief for {workspace_id}...")
        
        stats = get_workspace_stats_for_service(supabase, workspace_id)
        if not stats:
            continue
            
        ai_insight = stats.get('ai_insight')
        if not ai_insight:
            continue
            
        print(f"Dispatching daily digest for {workspace_id}: {ai_insight[:50]}...")
        dispatch_notification(
            svc=supabase,
            workspace_id=workspace_id,
            event_type="daily_digest",
            payload={
                "insight": ai_insight,
                "connections_today": stats.get('today', {}).get('connections', 0),
                "messages_today": stats.get('today', {}).get('messages', 0),
                "sentiment": stats.get('radar_stats', {}).get('Sentiment (Pos)', 0)
            }
        )
        
        # Chunking: sleep to avoid hammering the LLM API between workspaces
        time.sleep(2)

if __name__ == "__main__":
    supabase = get_service_client()
    run_throttle_and_burnout_checks(supabase)
    print("\n-------------------\n")
    run_daily_digest(supabase)

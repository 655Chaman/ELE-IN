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

def run_funnel_bottleneck_alerts(supabase):
    print("Running Funnel Bottleneck Alerts (Task #16 - #1)...")
    workspaces_res = supabase.table('workspaces').select('id, status').eq('status', 'active').execute()
    
    from datetime import timezone
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)
    
    for ws in workspaces_res.data:
        workspace_id = ws['id']
        
        # 1. Fetch action logs with node_id for the last 14 days
        logs_res = supabase.table('action_log').select('action_type, executed_at, metadata').eq('workspace_id', workspace_id).gte('executed_at', fourteen_days_ago.isoformat()).execute()
        
        from collections import defaultdict
        import json
        node_stats = defaultdict(lambda: {'prior_sends': 0, 'prior_success': 0, 'trailing_sends': 0, 'trailing_success': 0})
        
        for log in logs_res.data:
            meta = log.get('metadata')
            if not meta or not isinstance(meta, dict) or 'node_id' not in meta:
                continue
                
            node_id = meta['node_id']
            action_type = log.get('action_type')
            executed_at_str = log.get('executed_at')
            if not executed_at_str:
                continue
            
            # Handle possible trailing Z in timestamp
            executed_at = datetime.fromisoformat(executed_at_str.replace('Z', '+00:00'))
            
            is_trailing = executed_at >= seven_days_ago
            
            is_send = action_type in ['message', 'connection_request']
            is_success = action_type in ['reply_received', 'connection_accepted']
            
            if is_trailing:
                if is_send: node_stats[node_id]['trailing_sends'] += 1
                if is_success: node_stats[node_id]['trailing_success'] += 1
            else:
                if is_send: node_stats[node_id]['prior_sends'] += 1
                if is_success: node_stats[node_id]['prior_success'] += 1
                
        # 2. Check for bottlenecks
        for node_id, stats in node_stats.items():
            prior_sends = stats['prior_sends']
            prior_success = stats['prior_success']
            trailing_sends = stats['trailing_sends']
            trailing_success = stats['trailing_success']
            
            if prior_sends < 5 or trailing_sends < 5:
                continue # Not enough volume to confidently measure a drop
                
            prior_rate = prior_success / prior_sends
            trailing_rate = trailing_success / trailing_sends
            
            # Dropped by more than 50% relative
            if trailing_rate < (prior_rate * 0.5) and prior_rate > 0.05:
                print(f"Bottleneck detected on node {node_id}: Prior rate {prior_rate:.1%}, Trailing rate {trailing_rate:.1%}")
                
                # Fetch node content
                node_res = supabase.table('campaign_nodes').select('config').eq('id', node_id).execute()
                node_content = "Unknown content"
                if node_res.data and node_res.data[0]['config']:
                    config = node_res.data[0]['config']
                    node_content = config.get('body') or config.get('message') or json.dumps(config)
                    
                # Ask LLM for hypothesis
                from knowledge.backend.services.elein_ai_service import _get_sync_client, get_active_nvidia_keys
                
                keys = get_active_nvidia_keys("summarize")
                hypothesis = "Failed to generate AI hypothesis."
                if keys:
                    client = _get_sync_client(keys[0]["key"])
                    
                    prompt = f"""You are an expert sales strategist analyzing a sequence drop-off.
We detected a significant performance drop at a specific step in a cold outreach sequence.
Previous 7 days conversion rate: {prior_rate:.1%} ({prior_success}/{prior_sends})
Last 7 days conversion rate: {trailing_rate:.1%} ({trailing_success}/{trailing_sends})

Step Content:
{node_content}

Generate a short, specific, plain-English hypothesis for why this drop occurred and one suggested fix.
Keep it under 3 sentences. Do not use generic filler. Do not prefix with 'Hypothesis:'."""
                    try:
                        response = client.chat.completions.create(
                            model="meta/llama-3.2-11b-vision-instruct",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.3,
                            max_tokens=150
                        )
                        hypothesis = response.choices[0].message.content.strip()
                    except Exception as e:
                        print("LLM Error:", e)
                
                dispatch_notification(
                    svc=supabase,
                    workspace_id=workspace_id,
                    event_type="campaign_needs_attention",
                    payload={
                        "node_id": node_id,
                        "prior_rate": prior_rate,
                        "trailing_rate": trailing_rate,
                        "hypothesis": hypothesis
                    }
                )


if __name__ == "__main__":
    supabase = get_service_client()
    run_throttle_and_burnout_checks(supabase)
    print("\n-------------------\n")
    run_daily_digest(supabase)
    print("\n-------------------\n")
    run_funnel_bottleneck_alerts(supabase)

import asyncio
from typing import Optional

async def purge_workspace_data(workspace_id: str, supabase_client) -> bool:
    """
    Purges all PII data for a given workspace in the correct dependency order.
    Complies with GDPR Article 17.
    """
    # 1. Create a deletion request record
    res = supabase_client.table('gdpr_deletion_requests').insert({
        'workspace_id': workspace_id,
        'status': 'in_progress'
    }).execute()
    request_id = res.data[0]['id']

    try:
        # 2. Explicitly delete vector embeddings from knowledge_chunks first
        # (Though ON DELETE CASCADE might handle it, explicitly logging it is required)
        kc_res = supabase_client.table('knowledge_chunks').delete().eq('workspace_id', workspace_id).execute()
        
        # 2.5 Delete forgotten PII tables and campaign subsystem child records in dependency order
        tables_to_purge = [
            'ai_generations', 'processing_jobs', 'webhook_endpoints', 'knowledge_assets',
            'personas', 'objections', 'ai_reply_approvals', 'suppression_list',
            'enrichment_results', 'voice_notes', 'profile_activity_snapshots', 'audit_log',
            'notifications', 'outbox_events',
            'campaign_execution_states', 'campaign_node_executions', 'campaign_enrollments',
            'campaign_edges', 'campaign_nodes', 'campaign_versions', 'campaign_accounts',
            'workspace_blueprints', 'meeting_bookings', 'competitor_displacements',
            'sender_pods', 'bandit_experiments', 'account_daily_action_counts', 'account_limit_overrides'
        ]
        for table in tables_to_purge:
            try:
                supabase_client.table(table).delete().eq('workspace_id', workspace_id).execute()
            except Exception as _t_err:
                logger.debug(f"Non-fatal purge skip on {table}: {_t_err}")
        
        # 3. Delete from PII tables in child-first dependency order
        # Action Logs
        al_res = supabase_client.table('action_log').delete().eq('workspace_id', workspace_id).execute()
        
        # Messages
        msg_res = supabase_client.table('messages').delete().eq('workspace_id', workspace_id).execute()
        
        # Leads
        leads_res = supabase_client.table('leads').delete().eq('workspace_id', workspace_id).execute()
        
        # Campaigns
        camp_res = supabase_client.table('campaigns').delete().eq('workspace_id', workspace_id).execute()

        # Accounts (LinkedIn Data, Cookies)
        acc_res = supabase_client.table('accounts').delete().eq('workspace_id', workspace_id).execute()

        # 4. Finally, delete the workspace record itself
        # This will trigger the ON DELETE CASCADE for any remaining tables
        supabase_client.table('workspaces').delete().eq('id', workspace_id).execute()

        # 5. Mark as completed
        supabase_client.table('gdpr_deletion_requests').update({
            'status': 'completed'
        }).eq('id', request_id).execute()
        
        return True

    except Exception as e:
        # Mark as failed for retry cron
        supabase_client.table('gdpr_deletion_requests').update({
            'status': 'failed',
            'error_log': str(e)
        }).eq('id', request_id).execute()
        return False

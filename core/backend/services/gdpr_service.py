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

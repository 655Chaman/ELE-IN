import os
import time
import asyncio
import base64
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client, create_async_client

# PARANOIA LAYER 2: ZOMBIE TIMEOUT
# NEVER set this below 60 minutes. If a long-running AI task (like Voyager search) legitimately 
# takes 45 minutes, a short timeout will cause the reaper to reset the job while it is still running, 
# resulting in two workers executing the same expensive AI task simultaneously.
ZOMBIE_TIMEOUT_MINUTES = 120

# Load environment variables
load_dotenv("/Users/krdeeksha/Ele-in/backend/.env")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

async def process_single_job(job, sync_supabase):
    job_id = job["id"]
    job_type = job["job_type"]
    workspace_id = job["workspace_id"]
    asset_id = job["asset_id"]
    payload = job["payload"]
    
    print(f"Processing job {job_id} of type {job_type}")
    from knowledge.backend.services.knowledge_service import KnowledgeService
    
    try:
        def _run_sync_job():
            # Phase 0: Update asset status to 'processing' when picked up
            if asset_id:
                try:
                    sync_supabase.table("knowledge_assets").update({"status": "processing"}).eq("id", asset_id).execute()
                except Exception as e:
                    print(f"Failed to update asset status to processing: {e}")
            # PARANOIA LAYER 1: Thread-local event loop for async functions running in sync threads
            # Prevents "Task attached to a different loop" crashes during heavy loads.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if job_type == 'url':
                    loop.run_until_complete(KnowledgeService.process_url_bg(sync_supabase, workspace_id, payload['url'], asset_id))
                elif job_type == 'text':
                    loop.run_until_complete(KnowledgeService.process_text_bg(sync_supabase, workspace_id, payload['name'], payload['text'], asset_id))
                elif job_type == 'pdf':
                    storage_path = payload.get('storage_path')
                    if storage_path:
                        # Download from Supabase Storage
                        res = sync_supabase.storage.from_('knowledge-files').download(storage_path)
                        file_bytes = res
                    else:
                        # Fallback for old queued jobs that might still have base64 payload
                        file_bytes = base64.b64decode(payload['file_bytes'])
                    loop.run_until_complete(KnowledgeService.process_pdf_bg(sync_supabase, workspace_id, payload['filename'], file_bytes, asset_id))
                elif job_type == 'csv':
                    from campaigns.backend.routers.elein import process_csv_background
                    process_csv_background(payload['list_id'], payload['temp_file'], payload['mapping_dict'], payload['clean_data'], workspace_id, payload.get('target_timezone'))
                elif job_type == 'voyager_search':
                    from campaigns.backend.routers.elein import process_voyager_search_background
                    process_voyager_search_background(payload['list_id'], payload['url'], workspace_id, payload.get('account_id'), payload['max_results'], payload.get('target_timezone'))
                elif job_type == 'synthesis':
                    pass # update_synthesis runs automatically for this below
                elif job_type == 'hubspot_import':
                    from integrations.backend.services.hubspot_worker import import_hubspot_list_bg
                    loop.run_until_complete(import_hubspot_list_bg(sync_supabase, workspace_id, payload['list_id'], payload['internal_list_id']))
                elif job_type in ('inbox_sync', 'inbox_action'):
                    # ── INBOX JOBS: These run inside the SECURE background worker ──────────────────
                    # PARANOIA LAYER 2: Inbox jobs MUST be processed here in the background worker.
                    # The Web API cannot process these because it does not have COOKIE_PRIVATE_KEY.
                    # Never move decryption or Playwright execution back into the Web API routers.
                    from core.backend.core import crypto
                    from integrations.backend.services.linkedin_worker import LinkedInWorker
                    import json
                    import uuid

                    account_id = payload.get('account_id')
                    ws_id = payload.get('workspace_id', workspace_id)
                    
                    acc_res = sync_supabase.table("accounts").select("session_cookies_encrypted, proxies(protocol, host, port, username)").eq("id", account_id).execute()
                    if not acc_res.data:
                        raise ValueError(f"Account {account_id} not found.")
                    
                    acc = acc_res.data[0]
                    encrypted_cookies = acc.get("session_cookies_encrypted")
                    if not encrypted_cookies:
                        raise ValueError("Session cookies are null or empty. Account must be reconnected.")
                    
                    try:
                        decrypted = crypto.decrypt_bytes(encrypted_cookies)
                        cookie_json = decrypted.decode("utf-8")
                    except Exception as e:
                        raise ValueError("Cookie decryption failed. Account must be reconnected via the Chrome Extension.")
                    
                    # Parse Proxy
                    proxy_url = None
                    p = acc.get("proxies")
                    if p:
                        if p.get("username"):
                            proxy_url = f"{p['protocol']}://{p['username']}@{p['host']}:{p['port']}"
                        else:
                            proxy_url = f"{p['protocol']}://{p['host']}:{p['port']}"

                    try:
                        worker = LinkedInWorker(cookie_json, proxy_url=proxy_url, account_id=account_id)
                        
                        if job_type == 'inbox_sync':
                            messages = worker.sync_inbox()
                            
                            # Save messages
                            for m in messages:
                                existing = sync_supabase.table("messages").select("id").eq("account_id", account_id).eq("sender_name", m["sender_name"]).eq("message_text", m["message_text"]).eq("direction", m["direction"]).execute()
                                if not existing.data:
                                    sync_supabase.table("messages").insert({
                                        "id": str(uuid.uuid4()),
                                        "workspace_id": ws_id,
                                        "account_id": account_id,
                                        "sender_name": m["sender_name"],
                                        "message_text": m["message_text"],
                                        "direction": m["direction"],
                                    }).execute()
                        elif job_type == 'inbox_action':
                            action = payload.get('action')
                            payload_data = payload.get('payload_data', {})
                            if action == 'send_message':
                                worker.send_message(payload_data.get('profile_url'), payload_data.get('message'))
                            elif action == 'send_inmail':
                                worker.send_inmail(payload_data.get('profile_url'), payload_data.get('subject'), payload_data.get('body'))
                            elif action == 'send_message_with_attachment':
                                worker.send_message_with_attachment(payload_data.get('profile_url'), payload_data.get('body'), payload_data.get('attachment_url'), payload_data.get('attachment_type', 'document'))
                            else:
                                raise ValueError(f"Unknown inbox_action: {action}")
                    except Exception as e:
                        raise ValueError(f"LinkedIn worker error: {str(e)}")
                        
                else:
                    raise ValueError(f"Unknown job type: {job_type}")
                    
                sync_supabase.table("processing_jobs").update({"status": "done"}).eq("id", job_id).execute()
                
                if job_type in ('url', 'text', 'pdf', 'synthesis'):
                    loop.run_until_complete(KnowledgeService.update_synthesis(sync_supabase, workspace_id))
            finally:
                try:
                    # PARANOIA LAYER 2: Ensure pending tasks are cancelled to prevent memory leaks
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    loop.close()
                except Exception as loop_e:
                    print(f"Error closing thread loop: {loop_e}")
                
        await asyncio.to_thread(_run_sync_job)
        print(f"Job {job_id} completed successfully")
        
    except Exception as e:
        error_msg = str(e)[:500]
        print(f"Job {job_id} failed: {error_msg}")
        def _fail_job():
            sync_supabase.table("processing_jobs").update({
                "status": "failed",
                "error_msg": error_msg
            }).eq("id", job_id).execute()
            # PARANOIA: For list-type jobs, also mark the lead_list as errored.
            # If the background function itself threw before its own error handler ran
            # (e.g. KeyError on payload keys), the list would be stuck at 'pending' forever.
            list_id = payload.get("list_id") if isinstance(payload, dict) else None
            if list_id and job_type in ("voyager_search", "csv", "hubspot_import"):
                try:
                    sync_supabase.table("lead_lists").update({
                        "status": "error",
                        "row_count": -2,
                        "error_message": f"Job processor error: {error_msg}",
                    }).eq("id", list_id).execute()
                except Exception as le:
                    print(f"Failed to mark lead_list {list_id} as error: {le}")
        await asyncio.to_thread(_fail_job)


async def reap_zombie_jobs(async_supabase):
    try:
        # PARANOIA LAYER 1: try/except so network blips don't crash the reaper
        threshold_time = datetime.now(timezone.utc) - timedelta(minutes=ZOMBIE_TIMEOUT_MINUTES)
        
        response = await async_supabase.table("processing_jobs").select("id").eq("status", "running").lt("updated_at", threshold_time.isoformat()).execute()
        
        zombie_jobs = response.data
        if zombie_jobs:
            zombie_ids = [job['id'] for job in zombie_jobs]
            await async_supabase.table("processing_jobs").update({
                "status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).in_("id", zombie_ids).execute()
            
            print(f"[Zombie Reaper] Resurrected {len(zombie_ids)} marooned jobs.")
    except Exception as e:
        print(f"[Zombie Reaper] Failed to reap zombie jobs: {e}")


async def main_loop():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env")
        return

    # Use Async Client for the queue polling
    async_supabase = await create_async_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    # Use Sync Client to pass to legacy functions
    sync_supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    print("Starting horizontally scalable async job processor worker (Concurrency: 20)...")
    
    running_tasks = set()
    MAX_CONCURRENCY = 20
    
    last_reap_time = 0
    REAP_INTERVAL_SECONDS = 600 # 10 minutes
    last_hubspot_poll_time = 0
    HUBSPOT_POLL_INTERVAL_SECONDS = 300 # 5 minutes
    
    while True:
        try:
            current_time = time.time()
            if current_time - last_reap_time > REAP_INTERVAL_SECONDS:
                await reap_zombie_jobs(async_supabase)
                last_reap_time = current_time

            if current_time - last_hubspot_poll_time > HUBSPOT_POLL_INTERVAL_SECONDS:
                try:
                    from integrations.backend.services.hubspot_sync import sync_hubspot_deals_job
                    await sync_hubspot_deals_job(async_supabase, sync_supabase)
                except Exception as poll_e:
                    print(f"[HubSpot Poll] Error: {poll_e}")
                last_hubspot_poll_time = current_time


            done_tasks = {t for t in running_tasks if t.done()}
            running_tasks.difference_update(done_tasks)
            
            available_slots = MAX_CONCURRENCY - len(running_tasks)
            
            if available_slots <= 0:
                await asyncio.sleep(1)
                continue
                
            # Atomic DEQUEUE via Supabase RPC (FOR UPDATE SKIP LOCKED)
            response = await async_supabase.rpc('claim_processing_jobs', {'claim_limit': available_slots}).execute()
            jobs = response.data
            
            if not jobs:
                await asyncio.sleep(2)
                continue

            for job in jobs:
                task = asyncio.create_task(process_single_job(job, sync_supabase))
                running_tasks.add(task)
                
        except Exception as loop_e:
            print(f"Transient error in worker loop: {loop_e}")
            await asyncio.sleep(5)

def main():
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Worker stopped.")

if __name__ == "__main__":
    main()

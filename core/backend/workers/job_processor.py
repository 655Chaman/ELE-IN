import os
import json
import time
import asyncio
import logging
from core.backend.services.limits import get_effective_usage_date

logger = logging.getLogger(__name__)

from inbox.backend.services.inbox_service import (
    REPLY_ASSOCIATION_STATUSES,
    ACTIVE_REPLY_STATUSES,
    resolve_inbound_lead_and_campaign_context,
    sync_inbox_messages,
    process_inbox_messages,
)

process_inbox_sync = sync_inbox_messages
import base64
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client, create_async_client

# PARANOIA LAYER 0, 1 & 2: HEARTBEAT-BACKED ZOMBIE TIMEOUT
# Active jobs touch updated_at every 30 seconds via an async heartbeat worker.
# Therefore, 5 minutes of silence guarantees the worker process crashed or was OOM-killed.
ZOMBIE_TIMEOUT_MINUTES = max(2, min(15, int(os.environ.get("JOB_ZOMBIE_TIMEOUT_MINUTES", "5"))))

# Load environment variables
import os
from pathlib import Path
env_path = Path(__file__).resolve().parent.parent.parent.parent / "backend" / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")

async def process_single_job(job, sync_supabase):
    job_id = job["id"]
    job_type = job["job_type"]
    workspace_id = job["workspace_id"]
    asset_id = job.get("asset_id")
    raw_payload = job.get("payload")
    if isinstance(raw_payload, str):
        try:
            payload = json.loads(raw_payload)
        except Exception:
            payload = {}
    elif isinstance(raw_payload, dict):
        payload = dict(raw_payload)
    else:
        payload = {}
    
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
            
            asset_status = "failed"
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
                elif job_type == 'code_intelligence':
                    storage_path = payload.get('storage_path')
                    if storage_path:
                        res = sync_supabase.storage.from_('knowledge-files').download(storage_path)
                        file_bytes = res
                    else:
                        file_bytes = base64.b64decode(payload['file_bytes']) if 'file_bytes' in payload else b""
                    loop.run_until_complete(KnowledgeService.process_code_bg(sync_supabase, workspace_id, payload['filename'], file_bytes, asset_id))
                elif job_type == 'csv':
                    from campaigns.backend.routers.elein import process_csv_background
                    process_csv_background(payload['list_id'], payload['temp_file'], payload['mapping_dict'], payload['clean_data'], workspace_id, payload.get('target_timezone'), payload.get('collision_policy', 'merge'))
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
                    from integrations.backend.services.linkedin_worker import LinkedInWorker, SessionExpiredError
                    import json
                    import uuid

                    # PARANOIA LAYER 1: Fallback to job.get('asset_id') if payload lacks account_id
                    account_id = payload.get('account_id') or job.get('asset_id')
                    ws_id = payload.get('workspace_id', workspace_id)
                    
                    if not account_id:
                        raise ValueError(f"No account_id provided in payload or job asset_id for job {job_id}.")
                    
                    # If messages are pre-loaded in payload (e.g. simulated sync or external ingestion)
                    if job_type == 'inbox_sync' and payload.get('messages'):
                        messages = payload['messages']
                        sync_inbox_messages(sync_supabase, ws_id, account_id, messages)
                    else:
                        acc_res = sync_supabase.table("accounts").select("id, workspace_id, proxy_id, execution_channel, last_extension_active_at, session_cookies_encrypted, proxies(id, protocol, host, port, username, country_code, workspace_id)").eq("id", account_id).execute()
                        if not acc_res.data:
                            raise ValueError(f"Account {account_id} not found.")
                        
                        acc = acc_res.data[0]

                        # Paranoia Layer 1: Channel Mutex & Dual-IP Flapping Guard (Eradicates FLAW-03)
                        from core.backend.services.impossible_travel_guard import should_mute_cloud_execution
                        should_mute, mute_reason = should_mute_cloud_execution(acc)
                        if should_mute:
                            logger.info(f"[JobProcessor] Skipping cloud {job_type} for account {account_id}: {mute_reason}")
                            sync_supabase.table("processing_jobs").update({
                                "status": "done",
                                "metadata": {"muted": True, "reason": mute_reason}
                            }).eq("id", job_id).execute()
                            return

                        encrypted_cookies = acc.get("session_cookies_encrypted")
                        if not encrypted_cookies:
                            raise ValueError("Session cookies are null or empty. Account must be reconnected.")
                        
                        try:
                            # fetch dek from DB
                            dek_bytes = None
                            try:
                                rpc_res = sync_supabase.rpc("get_decrypted_account_payload", {"p_account_id": account_id}).execute()
                                if rpc_res.data and rpc_res.data.get("dek"):
                                    import base64
                                    dek_bytes = base64.b64decode(rpc_res.data["dek"])
                            except Exception as e:
                                logger.error(f"Failed to fetch DEK from Vault: {e}")
                            
                            raw_bytes = crypto.pg_hex_to_bytes(encrypted_cookies) if isinstance(encrypted_cookies, str) else encrypted_cookies
                            decrypted = crypto.decrypt_bytes(raw_bytes, dek=dek_bytes)
                            cookie_json = decrypted.decode("utf-8")
                        except Exception as e:
                            raise ValueError("Cookie decryption failed. Account must be reconnected via the Chrome Extension.")
                        
                        # Parse Proxy with Canonical Paranoia Builder
                        from core.backend.services.proxy_routing import build_authenticated_proxy_url
                        proxy_url = build_authenticated_proxy_url(acc, sync_supabase)
                        proxy_country = acc.get("proxies", {}).get("country_code") if isinstance(acc.get("proxies"), dict) else None

                        try:
                            worker = LinkedInWorker(cookie_json, proxy_url=proxy_url, account_id=account_id, country_code=proxy_country)
                            
                            if job_type == 'inbox_sync':
                                messages = worker.sync_inbox()
                                try:
                                    from knowledge.backend.services.elein_ai_service import classify_intent
                                    for m in messages:
                                        if m.get("direction") == "inbound":
                                            idem_key = f"classify_{ws_id}_{m.get('urn', hash(m['message_text']))}"
                                            intent_data = loop.run_until_complete(classify_intent(m["message_text"], workspace_id=ws_id, idempotency_key=idem_key))
                                            m["intent"] = intent_data.get("intent", "unknown")
                                            m["intent_confidence"] = intent_data.get("confidence", 0.0)
                                except Exception as e:
                                    logger.error(f"Intent classification failed in inbox_sync job: {e}")
                                sync_inbox_messages(sync_supabase, ws_id, account_id, messages)
                            elif job_type == 'inbox_action':
                                action = payload.get('action')
                                payload_data = payload.get('payload_data', {})
                                effective_date = get_effective_usage_date(payload.get("tz_str"))
                                consumed_action_type = None
                                try:
                                    if action == 'send_message':
                                        consumed_action_type = "message"
                                        ok = sync_supabase.rpc("try_consume_daily_action", {"p_account_id": account_id, "p_action_type": consumed_action_type, "p_usage_date": effective_date}).execute()
                                        if not ok.data: raise ValueError("Daily limit reached for action: message")
                                        worker.send_message(payload_data.get('profile_url'), payload_data.get('message'))
                                    elif action == 'send_message_to_existing_thread':
                                        consumed_action_type = "message"
                                        ok = sync_supabase.rpc("try_consume_daily_action", {"p_account_id": account_id, "p_action_type": consumed_action_type, "p_usage_date": effective_date}).execute()
                                        if not ok.data: raise ValueError("Daily limit reached for action: message")
                                        worker.send_message_to_existing_thread(payload_data.get('sender_name'), payload_data.get('message'))
                                    elif action == 'send_inmail':
                                        consumed_action_type = "inmail"
                                        ok = sync_supabase.rpc("try_consume_daily_action", {"p_account_id": account_id, "p_action_type": consumed_action_type, "p_usage_date": effective_date}).execute()
                                        if not ok.data: raise ValueError("Daily limit reached for action: inmail")
                                        worker.send_inmail(payload_data.get('profile_url'), payload_data.get('subject'), payload_data.get('body'))
                                    elif action == 'send_message_with_attachment':
                                        consumed_action_type = "message"
                                        ok = sync_supabase.rpc("try_consume_daily_action", {"p_account_id": account_id, "p_action_type": consumed_action_type, "p_usage_date": effective_date}).execute()
                                        if not ok.data: raise ValueError("Daily limit reached for action: message")
                                        worker.send_message_with_attachment(payload_data.get('profile_url'), payload_data.get('body'), payload_data.get('attachment_url'), payload_data.get('attachment_type', 'document'))
        
                                    else:
                                        raise ValueError(f"Unknown inbox_action: {action}")
                                except Exception as action_ex:
                                    if consumed_action_type:
                                        try:
                                            sync_supabase.rpc("release_consumed_daily_action", {
                                                "p_account_id": account_id,
                                                "p_action_type": consumed_action_type,
                                                "p_usage_date": effective_date
                                            }).execute()
                                        except Exception as release_ex:
                                            logger.warning(f"Failed to release daily action limit in inbox_action: {release_ex}")
                                    raise action_ex
                        except SessionExpiredError as e:
                            sync_supabase.table("accounts").update({"status": "DISCONNECTED"}).eq("id", account_id).execute()
                            logger.error(f"Account {account_id} disconnected during background job. Updated DB.")
                            raise ValueError("account_disconnected")
                        except Exception as e:
                            raise ValueError(f"LinkedIn worker error: {str(e)}")
                        
                else:
                    raise ValueError(f"Unknown job type: {job_type}")
                    
                sync_supabase.table("processing_jobs").update({"status": "done"}).eq("id", job_id).execute()
                
                if job_type in ('url', 'text', 'pdf', 'code_intelligence', 'synthesis'):
                    # Layer 0 & 1 Paranoia (Flaw 12): Dedicated synthesis jobs default to force=True unless explicitly false.
                    # Ingestion follower synthesis defaults to False unless payload specifies force=True.
                    force_synthesis = payload.get("force", True if job_type == 'synthesis' else False) if isinstance(payload, dict) else (job_type == 'synthesis')
                    loop.run_until_complete(KnowledgeService.update_synthesis(sync_supabase, workspace_id, force=bool(force_synthesis)))
                
                asset_status = "synced"
            finally:
                if asset_id and job_type in ('url', 'text', 'pdf', 'code_intelligence'):
                    # Layer 1 Paranoia: KnowledgeService._finalize_asset_processing sets 'failed' + error_msg if it errored.
                    # Only confirm 'synced' on clean completion; never overwrite 'failed' with a blank payload.
                    if asset_status == "synced":
                        try:
                            sync_supabase.table("knowledge_assets").update({"status": "synced"}).eq("id", asset_id).execute()
                        except Exception as e:
                            print(f"Failed to update asset status to synced: {e}")
                elif asset_id:
                    try:
                        sync_supabase.table("knowledge_assets").update({"status": asset_status}).eq("id", asset_id).execute()
                    except Exception as e:
                        print(f"Failed to update asset status to {asset_status}: {e}")
                
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
                
        heartbeat_stop = asyncio.Event()
        async def _heartbeat_loop():
            while not heartbeat_stop.is_set():
                try:
                    await asyncio.sleep(30)
                    if heartbeat_stop.is_set():
                        break
                    await asyncio.to_thread(
                        lambda: sync_supabase.table("processing_jobs").update({
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", job_id).eq("status", "running").execute()
                    )
                except Exception as hb_err:
                    logger.debug(f"[Heartbeat] Error updating job {job_id}: {hb_err}")

        hb_task = asyncio.create_task(_heartbeat_loop())
        try:
            await asyncio.to_thread(_run_sync_job)
        finally:
            heartbeat_stop.set()
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

        print(f"Job {job_id} completed successfully")
        
    except Exception as e:
        error_msg = str(e)[:500]
        print(f"Job {job_id} failed: {error_msg}")
        def _fail_job():
            sync_supabase.table("processing_jobs").update({
                "status": "failed",
                "error_msg": error_msg
            }).eq("id", job_id).execute()
            # PARANOIA: For knowledge assets, if an error occurred before KnowledgeService ran
            # (e.g. storage download failure or payload unpack error), guarantee the asset is marked failed with error_msg!
            if asset_id and job_type in ('url', 'text', 'pdf'):
                try:
                    sync_supabase.table("knowledge_assets").update({
                        "status": "failed",
                        "error_msg": error_msg
                    }).eq("id", asset_id).execute()
                except Exception as ae:
                    print(f"Failed to mark knowledge_asset {asset_id} as failed: {ae}")

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
        
        response = await async_supabase.table("processing_jobs").select("id, job_type, workspace_id, asset_id, payload").eq("status", "running").lt("updated_at", threshold_time.isoformat()).execute()
        
        zombie_jobs = response.data
        if zombie_jobs:
            zombie_ids = [job['id'] for job in zombie_jobs]
            await async_supabase.table("processing_jobs").update({
                "status": "failed",
                "error_msg": "Job timed out (zombie reaper)",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).in_("id", zombie_ids).execute()

            # Layer 1 & 2 Paranoia (FLAW 1.2 & FLAW-08): Cascade status to child entities & release reserved quotas
            for zj in zombie_jobs:
                try:
                    aid = zj.get("asset_id")
                    jtype = zj.get("job_type")
                    zpayload = zj.get("payload")
                    if isinstance(zpayload, str):
                        try:
                            zpayload = json.loads(zpayload)
                        except Exception:
                            zpayload = {}
                    elif not isinstance(zpayload, dict):
                        zpayload = {}

                    if aid and jtype in ('url', 'text', 'pdf'):
                        await async_supabase.table("knowledge_assets").update({
                            "status": "failed",
                            "error_msg": "Worker timed out (zombie reaper)",
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", aid).execute()

                    lid = zpayload.get("list_id")
                    if lid and jtype in ("voyager_search", "csv", "hubspot_import"):
                        await async_supabase.table("lead_lists").update({
                            "status": "error",
                            "row_count": -2,
                            "error_message": "Worker timed out (zombie reaper)",
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }).eq("id", lid).execute()

                    if jtype == "inbox_action":
                        acc_id = zpayload.get("account_id") or aid
                        if acc_id:
                            action_type = "inmail" if zpayload.get("action") == "send_inmail" else "message"
                            tz_str = zpayload.get("tz_str")
                            eff_date = get_effective_usage_date(tz_str)
                            try:
                                await async_supabase.rpc("release_consumed_daily_action", {
                                    "p_account_id": acc_id,
                                    "p_action_type": action_type,
                                    "p_usage_date": eff_date
                                }).execute()
                            except Exception as rel_err:
                                logger.debug(f"[ZombieReaper] Quota release notice: {rel_err}")
                except Exception as cascade_err:
                    print(f"[Zombie Reaper] Cascade failed for job {zj.get('id')}: {cascade_err}")
            
            print(f"[Zombie Reaper] Resurrected {len(zombie_ids)} marooned jobs with cascade.")
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

import signal
async def shutdown(sig, loop):
    print(f"Received exit signal {sig.name}. Initiating graceful shutdown...")

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        print(f"Waiting up to 10 seconds for {len(tasks)} active jobs to complete cleanly...")
        # Give active jobs 10 seconds to finish their current HTTP/DB calls
        done, pending = await asyncio.wait(tasks, timeout=10.0)
        if pending:
            print(f"Force cancelling {len(pending)} tasks that did not finish in time...")
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    # Layer 0 & 1 Paranoia: Only teardown browser pool AFTER active tasks have finished
    try:
        from integrations.backend.services.linkedin_pool import global_browser_pool
        global_browser_pool.teardown()
        print("Playwright browser pool torn down cleanly.")
    except Exception as e:
        print(f"Error tearing down browser pool: {e}")

    print("All tasks cleared. Stopping event loop.")
    loop.stop()

def main():
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))
    try:
        loop.run_until_complete(main_loop())
    except asyncio.CancelledError:
        pass
    print("Worker stopped.")

if __name__ == "__main__":
    main()

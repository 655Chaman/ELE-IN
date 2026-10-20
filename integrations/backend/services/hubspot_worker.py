import logging
import os
from core.backend.services.http_client import async_external_request
from leads.backend.services.data_hygiene import DataHygieneService

logger = logging.getLogger(__name__)

MAX_HUBSPOT_IMPORT_CONTACTS = int(os.getenv("MAX_HUBSPOT_IMPORT_CONTACTS", "10000"))
STREAM_CHUNK_SIZE = 500

async def import_hubspot_list_bg(supabase, workspace_id: str, hubspot_list_id: int, internal_list_id: str):
    """
    Paranoia Layer 0, 1 & 2: Streaming HubSpot Contact List Importer.
    - Layer 0: Imports in streaming chunks of 500 contacts directly via bulk_import_leads RPC.
    - Layer 1: Enforces MAX_HUBSPOT_IMPORT_CONTACTS safety ceiling (default 10,000) preventing OOM bombs.
      Applies DataHygieneService.sanitize_text against NUL bytes / malformed unicode.
      Deduplicates LinkedIn URLs within the batch.
    - Layer 2: On 401/403 token expiry, marks list 'failed' with actionable message and queues
      an outbox in-app notification.
    """
    try:
        # 1. Fetch token
        res = supabase.table("workspaces").select("hubspot_token").eq("id", workspace_id).execute()
        if not res.data or not res.data[0].get("hubspot_token"):
            raise ValueError("HubSpot not connected. Please connect your HubSpot account first.")

        access_token = res.data[0]["hubspot_token"]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        has_more = True
        vid_offset = 0
        total_imported = 0
        total_fetched = 0
        seen_urls = set()
        chunk_leads = []

        max_contacts = int(os.environ.get("MAX_HUBSPOT_IMPORT_CONTACTS", MAX_HUBSPOT_IMPORT_CONTACTS))

        while has_more:
            if total_fetched >= max_contacts:
                logger.warning(
                    f"[HubSpotImport] Hit maximum import ceiling of {max_contacts} contacts "
                    f"for list {internal_list_id}. Halting pagination safely."
                )
                break

            url = (
                f"https://api.hubapi.com/contacts/v1/lists/{hubspot_list_id}/contacts/all"
                f"?count=100&property=firstname&property=lastname&property=company&property=linkedin&property=hs_linkedin_url&property=city&property=country&property=email&property=jobtitle&property=phone"
            )
            if vid_offset > 0:
                url += f"&vidOffset={vid_offset}"

            try:
                resp = await async_external_request("GET", url, headers=headers)
                status_code = getattr(resp, "status_code", 200)
            except Exception as req_err:
                status_code = getattr(req_err, "status_code", None)
                if status_code in (401, 403):
                    err_msg = "HubSpot authorization expired or revoked (HTTP 401/403). Please reconnect HubSpot in Settings."
                    try:
                        supabase.table("outbox_events").insert({
                            "workspace_id": workspace_id,
                            "event_type": "notification.in_app",
                            "payload": {
                                "title": "HubSpot Import Failed",
                                "message": err_msg
                            },
                            "status": "pending"
                        }).execute()
                    except Exception:
                        pass
                    raise ValueError(err_msg)
                raise

            # Check for token expiry
            if status_code in (401, 403):
                err_msg = "HubSpot authorization expired or revoked (HTTP 401/403). Please reconnect HubSpot in Settings."
                try:
                    supabase.table("outbox_events").insert({
                        "workspace_id": workspace_id,
                        "event_type": "notification.in_app",
                        "payload": {
                            "title": "HubSpot Import Failed",
                            "message": err_msg
                        },
                        "status": "pending"
                    }).execute()
                except Exception:
                    pass
                raise ValueError(err_msg)

            if status_code != 200:
                resp_text = getattr(resp, "text", "")[:200]
                raise ValueError(f"Failed to fetch HubSpot contacts (HTTP {status_code}): {resp_text}")

            data = resp.json() if hasattr(resp, "json") else (resp if isinstance(resp, dict) else {})
            contacts = data.get("contacts", [])
            total_fetched += len(contacts)

            for contact in contacts:
                props = contact.get("properties", {})
                first_name = props.get("firstname", {}).get("value", "")
                last_name = props.get("lastname", {}).get("value", "")
                company = props.get("company", {}).get("value", "")
                linkedin = props.get("hs_linkedin_url", {}).get("value", "") or props.get("linkedin", {}).get("value", "")
                city = props.get("city", {}).get("value", "")
                country = props.get("country", {}).get("value", "")
                email = props.get("email", {}).get("value", "")
                job_title = props.get("jobtitle", {}).get("value", "")
                phone = props.get("phone", {}).get("value", "")

                # Paranoia Layer 1: Sanitize text against NUL bytes and control characters
                clean_first = DataHygieneService.sanitize_text(first_name, 100)
                clean_last = DataHygieneService.sanitize_text(last_name, 100)
                clean_company = DataHygieneService.sanitize_text(company, 150)
                clean_linkedin = DataHygieneService.sanitize_text(linkedin, 300)
                clean_city = DataHygieneService.sanitize_text(city, 100)
                clean_country = DataHygieneService.sanitize_text(country, 100)
                clean_email = DataHygieneService.clean_email(email)
                clean_job_title = DataHygieneService.sanitize_text(job_title, 150)

                # Deduplicate within batch by both email and linkedin (Email-first & Cross-field support)
                is_duplicate = False
                if clean_email and clean_email.lower() in seen_urls:
                    is_duplicate = True
                if clean_linkedin and clean_linkedin.lower() in seen_urls:
                    is_duplicate = True

                if is_duplicate:
                    continue

                if clean_email:
                    seen_urls.add(clean_email.lower())
                if clean_linkedin:
                    seen_urls.add(clean_linkedin.lower())

                loc_str = f"{clean_city}, {clean_country}".strip(", ") if clean_country else clean_city

                chunk_leads.append({
                    "first_name": clean_first,
                    "last_name": clean_last,
                    "company_name": clean_company,
                    "linkedin_url": clean_linkedin,
                    "email": clean_email,
                    "job_title": clean_job_title,
                    "p_location": loc_str,
                    "phone": phone
                })

                # Stream flush when chunk limit reached
                if len(chunk_leads) >= STREAM_CHUNK_SIZE:
                    from leads.backend.services.lead_ingestion_service import execute_bulk_import_leads
                    import_res = execute_bulk_import_leads(
                        supabase=supabase,
                        list_id=internal_list_id,
                        workspace_id=workspace_id,
                        leads=chunk_leads
                    )
                    inserted = import_res.get("inserted_count", len(chunk_leads))
                    total_imported += inserted
                    try:
                        supabase.table("lead_lists").update({
                            "status": "processing",
                            "row_count": total_imported
                        }).eq("id", internal_list_id).execute()
                    except Exception:
                        pass
                    chunk_leads = []

            has_more = data.get("has-more", False)
            vid_offset = data.get("vid-offset", 0)
            if not has_more:
                break

        # Flush remaining leads in final chunk
        if chunk_leads:
            from leads.backend.services.lead_ingestion_service import execute_bulk_import_leads
            import_res = execute_bulk_import_leads(
                supabase=supabase,
                list_id=internal_list_id,
                workspace_id=workspace_id,
                leads=chunk_leads
            )
            inserted = import_res.get("inserted_count", len(chunk_leads))
            total_imported += inserted

        try:
            supabase.table("lead_lists").update({
                "status": "completed",
                "row_count": total_imported
            }).eq("id", internal_list_id).execute()
        except Exception:
            pass
        logger.info(f"[HubSpotImport] Successfully completed import for list {internal_list_id}: {total_imported} leads.")

    except Exception as e:
        error_msg = str(e)[:500]
        logger.error(f"HubSpot import failed for list {internal_list_id}: {error_msg}", exc_info=True)
        try:
            supabase.table("lead_lists").update({
                "status": "failed",
                "error_message": error_msg,
                "row_count": -2
            }).eq("id", internal_list_id).execute()
        except Exception as update_err:
            logger.error(f"Also failed to mark lead_list {internal_list_id} as failed: {update_err}")
        raise

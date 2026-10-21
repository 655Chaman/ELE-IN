import os
import uuid
import json
import logging
import urllib.request
import urllib.error

from core.backend.api.auth_dep import get_service_client

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")


def send_outbound_email(
    match_id: str,
    to_email: str,
    subject: str,
    html_body: str,
    direction: str = "outbound",
    from_email: str = None,
):
    """
    Paranoia Layer 0, 1 & 2:
    Sends live outbound email via Resend API or SendGrid API and logs delivery into Supabase.
    Falls back gracefully in mock/test mode when no production ESP API keys are present.
    """
    email_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    sender = from_email or os.getenv("RESEND_FROM_EMAIL") or os.getenv("SENDGRID_FROM_EMAIL") or "support@elein.ai"
    message_id = None
    delivery_status = "sent"
    error_msg = None

    # 1. Attempt Live Resend API dispatch
    if RESEND_API_KEY:
        try:
            payload = {
                "from": sender,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            }
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    res_body = json.loads(resp.read().decode("utf-8"))
                    message_id = res_body.get("id") or f"resend_{email_id[:12]}"
        except Exception as e:
            logger.error(f"[InboxEmailService] Resend API dispatch error: {e}")
            delivery_status = "failed"
            error_msg = str(e)

    # 2. Attempt Live SendGrid API dispatch if Resend not configured
    elif SENDGRID_API_KEY:
        try:
            payload = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": sender},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_body}],
            }
            req = urllib.request.Request(
                "https://api.sendgrid.com/v3/mail/send",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201, 202):
                    message_id = f"sg_{email_id[:12]}@elein.ai"
        except Exception as e:
            logger.error(f"[InboxEmailService] SendGrid API dispatch error: {e}")
            delivery_status = "failed"
            error_msg = str(e)

    # 3. Environmental fallback (Test / Dev / Sandboxed environment)
    if not message_id and delivery_status != "failed":
        message_id = f"msg_{uuid.uuid4().hex[:12]}@b2b-pipeline.com"
        logger.info(f"[InboxEmailService] Simulated email to {to_email} (message_id: {message_id})")

    supabase = get_service_client()
    if supabase:
        try:
            insert_payload = {
                "id": email_id,
                "match_id": match_id,
                "message_id": message_id,
                "thread_id": thread_id,
                "subject": subject,
                "body": html_body,
                "direction": direction,
                "status": delivery_status,
            }
            if error_msg:
                insert_payload["error_message"] = error_msg
            supabase.table("emails").insert(insert_payload).execute()
        except Exception as db_err:
            logger.warning(f"[InboxEmailService] Failed logging outbound email to DB: {db_err}")

    if delivery_status == "failed":
        return {"success": False, "email_id": email_id, "error": error_msg}

    return {"success": True, "email_id": email_id, "message_id": message_id}

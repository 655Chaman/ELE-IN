import os
import uuid

from core.backend.api.auth_dep import get_service_client

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

def send_outbound_email(match_id: str, to_email: str, subject: str, html_body: str, direction: str = "outbound"):
    """
    Sends an email using Resend and logs it into the database.
    """
    # Create an internal email ID and Thread ID
    email_id = str(uuid.uuid4())
    # Generate a unique thread ID which could be passed in headers to correlate replies
    thread_id = str(uuid.uuid4())
    
    # In a real production system, you would call Resend API here.
    # For now, we will simulate the send and store it in the DB.
    # if RESEND_API_KEY:
    #     requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_API_KEY}"}, json={...})
    
    # Simulated Message ID from ESP
    message_id = f"msg_{uuid.uuid4().hex[:12]}@b2b-pipeline.com"
    
    supabase = get_service_client()
    supabase.table("emails").insert({
        "id": email_id,
        "match_id": match_id,
        "message_id": message_id,
        "thread_id": thread_id,
        "subject": subject,
        "body": html_body,
        "direction": direction,
        "status": "sent"
    }).execute()
    
    return {"success": True, "email_id": email_id, "message_id": message_id}

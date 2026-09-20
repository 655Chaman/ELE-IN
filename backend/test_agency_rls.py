import os
import uuid
import requests
from dotenv import load_dotenv
from supabase import create_client, ClientOptions

load_dotenv("/Users/krdeeksha/Ele-in/backend/.env")
url = os.environ.get("SUPABASE_URL")
service_key = os.environ.get("SUPABASE_SERVICE_KEY")
anon_key = os.environ.get("SUPABASE_KEY")

svc = create_client(url, service_key)
anon = create_client(url, anon_key)
API_URL = "http://localhost:8000"

def test_agency_rls():
    print("1. Setting up real agency & workspaces via service role...")
    owner_email = f"owner_{uuid.uuid4().hex[:8]}@example.com"
    member_email = f"member_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPassword123!"
    
    # Create Agency Owner
    owner_res = svc.auth.admin.create_user({"email": owner_email, "password": password, "email_confirm": True})
    owner_id = owner_res.user.id
    
    # Create Agency Member
    member_res = svc.auth.admin.create_user({"email": member_email, "password": password, "email_confirm": True})
    member_id = member_res.user.id
    
    agency_id = str(uuid.uuid4())
    client_a_ws = str(uuid.uuid4())
    client_b_ws = str(uuid.uuid4())

    try:
        # Create Agency
        svc.table("agencies").insert({"id": agency_id, "name": "Super Agency", "owner_id": owner_id}).execute()
        
        # Add owner to agency_members
        svc.table("agency_members").insert({"agency_id": agency_id, "user_id": owner_id, "role": "owner"}).execute()
        
        # Add member to agency_members
        am_res = svc.table("agency_members").insert({"agency_id": agency_id, "user_id": member_id, "role": "member"}).execute()
        agency_member_id = am_res.data[0]["id"]
        
        # Create Client A and Client B
        svc.table("workspaces").insert({"id": client_a_ws, "name": "Client A WS", "owner_id": owner_id, "agency_id": agency_id}).execute()
        svc.table("workspaces").insert({"id": client_b_ws, "name": "Client B WS", "owner_id": owner_id, "agency_id": agency_id}).execute()
        
        # Assign member to ONLY Client A
        svc.table("agency_client_access").insert({"agency_member_id": agency_member_id, "workspace_id": client_a_ws}).execute()
        
        # Add a dummy lead in both workspaces to test RLS
        lead_a = str(uuid.uuid4())
        lead_b = str(uuid.uuid4())
        svc.table("leads").insert([
            {"id": lead_a, "workspace_id": client_a_ws, "linkedin_url": "https://linkedin.com/in/a", "first_name": "Lead A"},
            {"id": lead_b, "workspace_id": client_b_ws, "linkedin_url": "https://linkedin.com/in/b", "first_name": "Lead B"}
        ]).execute()
        
        print("\n2. Authenticating as the OWNER...")
        owner_auth = anon.auth.sign_in_with_password({"email": owner_email, "password": password})
        owner_jwt = owner_auth.session.access_token
        owner_client = create_client(url, anon_key, options=ClientOptions(headers={"Authorization": f"Bearer {owner_jwt}"}))
        
        print("  -> OWNER testing Client A leads:")
        owner_a = owner_client.table("leads").select("*").eq("workspace_id", client_a_ws).execute()
        print(f"     Found {len(owner_a.data)} leads. Success if 1." )
        
        print("  -> OWNER testing Client B leads:")
        owner_b = owner_client.table("leads").select("*").eq("workspace_id", client_b_ws).execute()
        print(f"     Found {len(owner_b.data)} leads. Success if 1." )

        print("\n3. Authenticating as the MEMBER...")
        member_auth = anon.auth.sign_in_with_password({"email": member_email, "password": password})
        member_jwt = member_auth.session.access_token
        member_client = create_client(url, anon_key, options=ClientOptions(headers={"Authorization": f"Bearer {member_jwt}"}))
        
        print("  -> MEMBER testing Client A leads (should have access):")
        member_a = member_client.table("leads").select("*").eq("workspace_id", client_a_ws).execute()
        print(f"     Found {len(member_a.data)} leads. Success if 1." )
        
        print("  -> MEMBER testing Client B leads (should BE BLOCKED):")
        member_b = member_client.table("leads").select("*").eq("workspace_id", client_b_ws).execute()
        print(f"     Found {len(member_b.data)} leads. Success if 0." )

    finally:
        print("\n4. Cleaning up...")
        ws_del = svc.table("workspaces").delete().in_("id", [client_a_ws, client_b_ws]).execute()
        print(f"  -> Deleted {len(ws_del.data)} workspaces.")
        ag_del = svc.table("agencies").delete().eq("id", agency_id).execute()
        print(f"  -> Deleted {len(ag_del.data)} agency.")
        try:
            svc.auth.admin.delete_user(owner_id)
            svc.auth.admin.delete_user(member_id)
            print("  -> Deleted owner and member auth users.")
        except Exception as e:
            print(f"  -> Cleanup users error: {e}")

if __name__ == "__main__":
    test_agency_rls()

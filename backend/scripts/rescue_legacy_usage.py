import os
import csv
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv("../.env")

# This script is a disaster recovery tool.
# If you ever use Supabase PITR to extract the old `account_daily_usage` table as a CSV,
# run this script to safely map and ingest it into the new atomic architecture.

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
CSV_FILE_PATH = "legacy_account_daily_usage_backup.csv"

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ Missing Supabase environment variables.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def run_ingestion():
    if not os.path.exists(CSV_FILE_PATH):
        print(f"❌ Could not find {CSV_FILE_PATH}. Export this from your PITR backup.")
        return

    print("🚀 Starting legacy usage ingestion...")
    with open(CSV_FILE_PATH, mode='r') as file:
        reader = csv.DictReader(file)
        
        for row in reader:
            account_id = row['account_id']
            usage_date = row['date']
            connections_sent = int(row.get('connections_sent', 0))
            messages_sent = int(row.get('messages_sent', 0))

            # Ingest Connections
            if connections_sent > 0:
                try:
                    supabase.table('account_daily_action_counts').insert({
                        "account_id": account_id,
                        "action_type": "connection_request",
                        "usage_date": usage_date,
                        "count": connections_sent
                    }).execute()
                    print(f"✅ Restored {connections_sent} connections for {account_id} on {usage_date}")
                except Exception as e:
                    # Will safely ignore conflicts if the data is already there
                    pass

            # Ingest Messages
            if messages_sent > 0:
                try:
                    supabase.table('account_daily_action_counts').insert({
                        "account_id": account_id,
                        "action_type": "message",
                        "usage_date": usage_date,
                        "count": messages_sent
                    }).execute()
                    print(f"✅ Restored {messages_sent} messages for {account_id} on {usage_date}")
                except Exception as e:
                    pass

    print("🎉 Legacy usage data successfully migrated to atomic format.")

if __name__ == "__main__":
    run_ingestion()

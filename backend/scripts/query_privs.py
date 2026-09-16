import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("NO DATABASE_URL")
    exit(0)

conn = psycopg2.connect(db_url)
cur = conn.cursor()
cur.execute("""
    SELECT grantee, privilege_type 
    FROM information_schema.role_table_grants 
    WHERE table_name IN ('campaign_accounts', 'campaign_enrollments', 'campaign_execution_states', 'campaign_node_executions')
    AND grantee IN ('anon', 'authenticated', 'service_role');
""")
print("GRANTS:")
for r in cur.fetchall(): print(r)

cur.execute("""
    SELECT relname, relrowsecurity 
    FROM pg_class 
    WHERE relname IN ('campaign_accounts', 'campaign_enrollments', 'campaign_execution_states', 'campaign_node_executions');
""")
print("\nRLS:")
for r in cur.fetchall(): print(r)


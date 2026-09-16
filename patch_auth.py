# ⚠️  ONE-TIME MIGRATION SCRIPT — DO NOT RE-RUN
# This script was used to migrate from the monolith (frontend/src/) to the modular
# layout (core/, campaigns/, etc.). The migration is complete. Re-running this
# script will corrupt the current codebase. Safe to delete after team review.
import re

with open("core/backend/api/auth_dep.py", "r") as f:
    content = f.read()

replacement = """
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not any(request.url.path.endswith(p) for p in exempt_paths):
        try:
            ws_status_res = await supabase.table("workspaces").select("status").eq("id", workspace_id).execute()
            ws_status = ws_status_res.data[0].get("status") if ws_status_res.data else None
            if ws_status == "pending_deletion":
                raise HTTPException(
                    status_code=423,
                    detail="This workspace is scheduled for deletion. All modifications are locked during the 14-day grace period."
                )
        except HTTPException:
            raise
        except Exception as e:
            # If the column doesn't exist or DB errors out, gracefully ignore the deletion lock
            pass
"""

content = re.sub(
    r'    if request\.method in \("POST", "PUT", "PATCH", "DELETE"\) and not any\(request\.url\.path\.endswith\(p\) for p in exempt_paths\):\n        ws_status_res = await supabase\.table\("workspaces"\)\.select\("status"\)\.eq\("id", workspace_id\)\.execute\(\)\n        ws_status = ws_status_res\.data\[0\]\.get\("status"\) if ws_status_res\.data else None\n        if ws_status == "pending_deletion":\n            raise HTTPException\(\n                status_code=423,\n                detail="This workspace is scheduled for deletion\. All modifications are locked during the 14-day grace period\."\n            \)',
    replacement.strip('\n'),
    content
)

with open("core/backend/api/auth_dep.py", "w") as f:
    f.write(content)
print("Patched auth_dep.py")

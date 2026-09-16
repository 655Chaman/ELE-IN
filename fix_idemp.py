import re

with open("campaigns/backend/services/elein_orchestrator.py", "r") as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if "except Exception as e:" in line and "Collision detected!" in lines[i+1]:
        new_lines.append(line)
        new_lines.append(lines[i+1])
        new_lines.append(lines[i+1].replace("Collision detected!", "Check unique constraint (code 23505)"))
        indent = line.split("except")[0]
        new_lines.append(indent + "    err_str = str(e)\n")
        new_lines.append(indent + "    if not (hasattr(e, 'code') and getattr(e, 'code') == '23505') and '23505' not in err_str:\n")
        new_lines.append(indent + "        return {\"status\": \"error\", \"error\": f\"Database failed to create idempotency lock: {e}\"}\n")
        i += 2
        continue
    
    if "elif col_status == \"failed\":" in line:
        new_lines.append(line)
        indent = line.split("elif")[0]
        new_lines.append(indent + "    upd_res = self.supabase.table(\"campaign_node_executions\").update({\"status\": \"running\"}).eq(\"idempotency_key\", idemp_key).eq(\"status\", \"failed\").execute()\n")
        new_lines.append(indent + "    if not upd_res.data:\n")
        new_lines.append(indent + "        return {\"status\": \"error\", \"error\": \"UNKNOWN: Concurrent worker collision during retry.\", \"requires_approval\": True}\n")
        i += 1
        continue
    
    new_lines.append(line)
    i += 1

with open("campaigns/backend/services/elein_orchestrator.py", "w") as f:
    f.writelines(new_lines)


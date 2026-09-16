import re

with open("campaigns/backend/services/elein_orchestrator.py", "r") as f:
    content = f.read()

# 1. Fix idempotency key
old_key = 'idempotency_raw = f"{state.get(\'enrollment_id\')}_{current_node_id}_{attempt_count}"'
new_key = 'idempotency_raw = f"{state.get(\'enrollment_id\')}_{current_node_id}"'
content = content.replace(old_key, new_key)

# 2. Fix idempotency collision handling
old_idemp = """
                try:
                    self.supabase.table("campaign_node_executions").insert({
                        "idempotency_key": idemp_key,
                        "campaign_id": state["campaign_id"],
                        "enrollment_id": state["enrollment_id"],
                        "node_id": current_node_id,
                        "status": "running"
                    }).execute()
                except Exception as e:
                    # Collision detected!
                    try:
                        collision_res = self.supabase.table("campaign_node_executions").select("status, error_code, output_payload").eq("idempotency_key", idemp_key).execute()
                        if collision_res.data:
                            col_state = collision_res.data[0]
                            if col_state["status"] == "success":
                                return {"status": "fast_forward", "branch": col_state["output_payload"].get("branch"), "variables": col_state["output_payload"].get("variables")}
                            else:
                                return {"status": "error", "error": "UNKNOWN: Previous worker crashed mid-execution. Safe resume requires manual verification.", "requires_approval": True}
                        else:
                            return {"status": "error", "error": f"Database failed to create idempotency lock: {e}"}
                    except Exception as inner_e:
                        return {"status": "error", "error": f"Failed to resolve idempotency lock: {inner_e}"}
"""

new_idemp = """
                try:
                    self.supabase.table("campaign_node_executions").insert({
                        "idempotency_key": idemp_key,
                        "campaign_id": state["campaign_id"],
                        "enrollment_id": state["enrollment_id"],
                        "node_id": current_node_id,
                        "status": "running"
                    }).execute()
                except Exception as e:
                    # Collision detected! Only proceed if it is a unique constraint violation (code 23505)
                    err_str = str(e)
                    if not (hasattr(e, "code") and getattr(e, "code") == "23505") and "23505" not in err_str:
                        return {"status": "error", "error": f"Database failed to create idempotency lock: {e}"}

                    try:
                        collision_res = self.supabase.table("campaign_node_executions").select("status, error_code, output_payload").eq("idempotency_key", idemp_key).execute()
                        if collision_res.data:
                            col_state = collision_res.data[0]
                            if col_state["status"] == "success":
                                return {"status": "fast_forward", "branch": col_state["output_payload"].get("branch"), "variables": col_state["output_payload"].get("variables")}
                            elif col_state["status"] == "failed":
                                # Previously failed definitively. Retry is allowed. Update to running.
                                upd_res = self.supabase.table("campaign_node_executions").update({"status": "running"}).eq("idempotency_key", idemp_key).eq("status", "failed").execute()
                                if not upd_res.data:
                                    return {"status": "error", "error": "UNKNOWN: Concurrent worker collision during retry.", "requires_approval": True}
                                # Successfully set to running, proceed with external action
                                pass
                            else:
                                return {"status": "error", "error": "UNKNOWN: Previous worker crashed mid-execution. Safe resume requires manual verification.", "requires_approval": True}
                        else:
                            return {"status": "error", "error": f"Idempotency INSERT failed, but no collision exists."}
                    except Exception as inner_e:
                        return {"status": "error", "error": f"Failed to resolve idempotency lock: {inner_e}"}
"""
content = content.replace(old_idemp.strip(), new_idemp.strip())

# 3. Fix process_lead security_challenge handling
old_process = """
        if action_result.get("status") == "error":
            self.mark_error(
"""
new_process = """
        if action_result.get("status") == "security_challenge":
            self.mark_error(
                state["id"],
                action_result.get("error", "Security Challenge Detected"),
                attempts=state.get("attempts", 0),
                max_attempts=state.get("max_attempts", 5),
                hard_error=True,
                lease_token=lease_token,
                node_id=current_node_id
            )
            return

        if action_result.get("status") == "error":
            self.mark_error(
"""
content = content.replace(old_process.strip(), new_process.strip())

with open("campaigns/backend/services/elein_orchestrator.py", "w") as f:
    f.write(content)


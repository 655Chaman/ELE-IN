import re

with open("campaigns/backend/services/elein_orchestrator.py", "r") as f:
    content = f.read()

old_failed_block = """
                            elif col_status == "failed":
                                upd_res = self.supabase.table("campaign_node_executions").update({"status": "running"}).eq("idempotency_key", idemp_key).eq("status", "failed").execute()
                                if not upd_res.data:
                                    return {"status": "error", "error": "UNKNOWN: Concurrent worker collision during retry.", "requires_approval": True}
                                if col_err in ("RATE_LIMITED", "ACCOUNT_DISCONNECTED", "SECURITY_CHALLENGE"):
                                    # Previous attempt was blocked by an orchestration gate, so the external action NEVER happened.
                                    # We can safely bypass the collision and evaluate the gates again.
                                    logger.info(f"Idempotency hit ({idemp_key}): Previous orchestration block ({col_err}). Retrying.")
                                    pass 
                                else:
                                    # The external action definitively failed (TRANSIENT_EXECUTION_ERROR or DEFINITIVE_EXTERNAL_FAILURE).
                                    # Return error so process_lead can increment the attempt counter properly.
                                    return {"status": "error", "error": f"Previous execution failed with error: {col_err}"}
"""
new_failed_block = """
                            elif col_status == "failed":
                                upd_res = self.supabase.table("campaign_node_executions").update({"status": "running"}).eq("idempotency_key", idemp_key).eq("status", "failed").execute()
                                if not upd_res.data:
                                    return {"status": "error", "error": "UNKNOWN: Concurrent worker collision during retry.", "requires_approval": True}
                                logger.info(f"Idempotency hit ({idemp_key}): Retrying previously failed action ({col_err}).")
                                pass 
"""
content = content.replace(old_failed_block.strip("\n"), new_failed_block.strip("\n"))

with open("campaigns/backend/services/elein_orchestrator.py", "w") as f:
    f.write(content)


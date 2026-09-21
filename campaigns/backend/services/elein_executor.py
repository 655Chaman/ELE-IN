import logging
from integrations.backend.services.elein_crm_service import push_to_hubspot
import re
import json
import random
import urllib.parse
from typing import Dict, Any, Optional

from integrations.backend.services.linkedin_worker import LinkedInWorker, SessionExpiredError, LinkedInActionOutcomeUnknown

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Custom exceptions
# ─────────────────────────────────────────────────────────────────────────────

class UninterpolatedTemplateError(Exception):
    """C2: Raised when a message still contains {{variable}} placeholders after interpolation."""
    pass


class LeadSuppressedError(Exception):
    """E1/E3: Raised when a lead is on the suppression list — action must not proceed."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# C2: Unresolved template variable guard
# ─────────────────────────────────────────────────────────────────────────────

def assert_fully_interpolated(message: str, lead_id: str = "", node_id: str = "") -> None:
    """
    Raises UninterpolatedTemplateError if any {{variable}} placeholders remain
    in the message after interpolation. Call this before every send/type action.
    """
    remaining = re.findall(r"\{\{.*?\}\}", message)
    if remaining:
        raise UninterpolatedTemplateError(
            f"Lead {lead_id}, node {node_id}: unresolved variables {remaining} — refusing to send"
        )


class EleInNodeExecutor:
    """
    Full 100-node execution registry for the EleIn automation engine.
    Every node defined in eiNodeDefs.ts has a matching handler here.
    Nodes are either:
      - LIVE: Backed by real Playwright actions via LinkedInWorker
      - AI_STUB: Requires an LLM call (returns success, sets variable)
      - API_STUB: Requires a third-party API key (logs + returns success)
      - LOGIC: Pure DB/state operations, no external calls needed
    """

    def __init__(self, linkedin_worker: Optional[LinkedInWorker] = None, supabase=None):
        self.worker = linkedin_worker
        self.supabase = supabase  # needed for C7 idempotency and E1 suppression checks

    def execute(self, action: str, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        # C2 Safety Net: After substitution, if ANY {{...}} pattern still remains unreplaced, do NOT send
        unresolved = []
        def find_unresolved(d):
            for v in d.values():
                if isinstance(v, str):
                    matches = re.findall(r"\{\{.*?\}\}", v)
                    if matches:
                        unresolved.extend(matches)
                elif isinstance(v, dict):
                    find_unresolved(v)
        find_unresolved(data)
        if unresolved:
            logger.error(f"Message contained unresolved variables: {unresolved}")
            return {
                "status": "error",
                "error": f"Unresolved template variables {unresolved} in node data — campaign configuration error, refusing to send",
                "requires_approval": True,
                "branch": "Failed"
            }
            
        handler_name = f"handle_{action}"
        try:
            if hasattr(self, handler_name):
                handler = getattr(self, handler_name)
                return handler(data, linkedin_url)
            else:
                return self._default_handler(action, data, linkedin_url)
        except UninterpolatedTemplateError as e:
            # C2: Unresolved template — route to approval_queue, do not retry forever
            logger.error(f"[C2] Unresolved template variable: {e}")
            return {"status": "error", "error": str(e), "requires_approval": True}
        except LeadSuppressedError as e:
            # E1: Lead is suppressed — mark as not-interested, do not retry
            logger.info(f"[E1] Lead suppressed: {e}")
            return {"status": "suppressed", "error": str(e)}
        except SessionExpiredError as e:
            logger.error(f"[Auth] Session Expired Error caught in executor: {e}")
            return {"status": "account_disconnected", "error": str(e)}

        except Exception as e:
            err_str = str(e).lower()
            if "security challenge detected" in err_str:
                logger.error(f"[Auth] Security Challenge detected: {e}")
                return {"status": "security_challenge", "error": str(e)}
            
            # Any other exception (including timeout or network errors) could mean the action
            # was partially executed. We must RAISE the exception so the orchestrator
            # abandons the update and leaves the execution record as 'running'.
            # This triggers the UNKNOWN idempotency safety halt on the next retry.
            logger.exception(f"Unhandled error executing node '{action}' on {linkedin_url}. Raising to preserve UNKNOWN state safety.")
            raise


    def _default_handler(self, action: str, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.error(f"[CRITICAL][Executor] No handler implemented for action type: '{action}'. Lead will be marked failed. Add a handle_{action.replace('-', '_')} method to EleInExecutor.")
        return {"status": "failed", "error": f"No execution handler for node type '{action}'"}

    def _require_worker(self, linkedin_url: Optional[str]) -> Optional[str]:
        """Returns an error string if worker/url is missing, else None."""
        if not self.worker:
            return "No LinkedIn worker available (missing or invalid account cookies)"
        if not linkedin_url:
            return "No LinkedIn URL for this lead"
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # C7: Node-level idempotency guard
    # ─────────────────────────────────────────────────────────────────────────

    def _check_idempotency(self, lead_state_id: str, node_id: str) -> bool:
        """
        DEPRECATED (Phase 3): This relied on the legacy Phase 1 action_log table.
        Idempotency is now formally handled by EleInOrchestrator using campaign_node_executions.
        """
        return False


    # ─── THE UNIFIED AI BRAIN ──────────────────────────────────────────────────
    def _get_unified_brain(self, workspace_id: str) -> dict:
        """
        Pre-loads the entire AI Knowledge Base synthesis for the workspace.
        Instead of running expensive vector searches inside every node, we load 
        the definitive company brain ONCE, completely eliminating latency limits.
        """
        if not workspace_id or not self.supabase:
            return {}
            
        # Fast caching on the executor instance
        if not hasattr(self, '_brain_cache'):
            self._brain_cache = {}
            
        if workspace_id in self._brain_cache:
            return self._brain_cache[workspace_id]
            
        try:
            brain = {}
            res = self.supabase.table("knowledge_synthesis").select("*").eq("workspace_id", workspace_id).execute()
            if res.data:
                brain = res.data[0]
                
            personas_res = self.supabase.table("personas").select("*").eq("workspace_id", workspace_id).execute()
            if personas_res.data:
                brain["personas"] = personas_res.data
                
            obj_res = self.supabase.table("knowledge_objections").select("*").eq("workspace_id", workspace_id).execute()
            if obj_res.data:
                brain["objections"] = obj_res.data
                
            self._brain_cache[workspace_id] = brain
            return brain
        except Exception as e:
            logger.error(f"[Brain] Failed to load unified brain for {workspace_id}: {e}")
            
        return {}

    # ─── AI NODES (Zero Latency Integration) ───────────────────────────────────

    def handle_ai_personalize(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import generate_ai_hook
        workspace_id = data.get("workspace_id", "")
        brain = self._get_unified_brain(workspace_id)
        
        # Layer 1 Paranoia: Route specific Buyer Personas instantly without injecting the whole database.
        profile = data.get("lead_profile", {})
        headline = profile.get("title", "").lower()
        
        personas = brain.get("personas", [])
        matched_persona = None
        for p in personas:
            targets = [t.lower().strip() for t in p.get("target_titles", [])]
            if any(t in headline for t in targets):
                matched_persona = p
                break
        
        custom_persona = data.get("custom_persona", "")
        if matched_persona:
            custom_persona += f"\n\nYou are speaking to a {matched_persona.get('title')}. Their precise pain points are: {', '.join(matched_persona.get('pain_points', []))}. Core value to pitch them: {matched_persona.get('value_prop', '')}. Tone directives: {matched_persona.get('tone_tweaks', '')}"
            
        custom_rules = data.get("custom_rules", "")
        fallback_msg = data.get("fallback_message", "I noticed your impressive background on LinkedIn.")
        
        banned_phrases = brain.get("banned_phrases", "")
        ai_model = data.get("ai_model", "")
        hook = generate_ai_hook(profile, workspace_id, custom_persona, custom_rules, banned_phrases, ai_model)
        return {"status": "success", "variables": {"ai_hook": hook or fallback_msg}}

    def handle_ai_detect_sentiment(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import classify_reply_sentiment
        reply_text = data.get("reply_text", "")
        
        workspace_id = data.get("workspace_id", "")
        brain = self._get_unified_brain(workspace_id)
        core_value_prop = brain.get("core_value_prop", "")
        ai_model = data.get("ai_model", "")
        
        sentiment = classify_reply_sentiment(reply_text, core_value_prop, ai_model, workspace_id)
        return {"status": "success", "variables": {"ai_sentiment": sentiment}}

    def handle_ai_generate_icebreaker(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        # Same as personalize conceptually but focused on posts
        from knowledge.backend.services.elein_ai_service import generate_ai_hook
        profile = data.get("lead_profile", {})
        workspace_id = data.get("workspace_id", "")
        brain = self._get_unified_brain(workspace_id)
        custom_persona = data.get("custom_persona", "")
        custom_rules = data.get("custom_rules", "")
        fallback_msg = data.get("fallback_message", "I loved your recent activity on LinkedIn.")
        
        banned_phrases = brain.get("banned_phrases", "")
        ai_model = data.get("ai_model", "")
        hook = generate_ai_hook(profile, workspace_id, custom_persona, custom_rules, banned_phrases, ai_model)
        return {"status": "success", "variables": {"ai_icebreaker": hook or fallback_msg}}

    def handle_ai_translate_message(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import translate_message
        msg = data.get("message", "")
        lang = data.get("target_language", "English")
        translated = translate_message(msg, lang, ai_model=data.get("ai_model", ""), workspace_id=data.get("workspace_id", ""))
        return {"status": "success", "variables": {"ai_translated": translated or msg}}

    def handle_ai_score_icp(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import score_icp_fit
        workspace_id = data.get("workspace_id", "")
        brain = self._get_unified_brain(workspace_id)
        
        # Layer 1 Paranoia: Dynamically filter Buyer Personas in Python before hitting the prompt window.
        # This prevents dumping 50 personas and blowing up the context length.
        personas = brain.get("personas", [])
        icp_criteria = brain.get("target_customer_profile", "")
        profile = data.get("lead_profile", {})
        headline = profile.get("title", "").lower()
        
        matched_persona = None
        for p in personas:
            targets = [t.lower().strip() for t in p.get("target_titles", [])]
            if any(t in headline for t in targets):
                matched_persona = p
                break
                
        if matched_persona:
            icp_criteria += f"\n\nStrict Buyer Persona Match for this Lead:\nTitle: {matched_persona.get('title', 'Unknown')}\nPain Points: {', '.join(matched_persona.get('pain_points', []))}\nValue Prop: {matched_persona.get('value_prop', '')}"
        elif personas:
            icp_criteria += "\n\n(No explicit persona match found for this lead's title. Evaluate based on general ICP criteria.)"
        
        
        profile = data.get("lead_profile", {})
        ai_model = data.get("ai_model", "")
        # Layer 0 Paranoia: Pass the requested model and ensure the fallback executes if the LLM crashes
        score = score_icp_fit(profile, icp_criteria, workspace_id, ai_model)
        
        # Layer 2 Paranoia: Physical fallback for the execution engine. If the LLM throws an empty string
        # because of a 400 cascade or network failure, we MUST NOT return an empty string to the templating engine.
        # An empty ICP Score causes downstream branch failures. Default to Medium.
        if not score or score not in ["High", "Medium", "Low"]:
            score = "Medium"
            
        return {"status": "success", "variables": {"icp_score": score}}

    def handle_ai_detect_buying_signal(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import detect_buying_signal
        profile = data.get("lead_profile", {})
        
        workspace_id = data.get("workspace_id", "")
        brain = self._get_unified_brain(workspace_id)
        core_value_prop = brain.get("core_value_prop", "")
        pain_points = brain.get("primary_pain_points_solved", [])
        ai_model = data.get("ai_model", "")
        
        signal = detect_buying_signal(profile, core_value_prop, pain_points, ai_model, workspace_id)
        
        # Layer 2 Paranoia: Physical fallback. A campaign branch expects "Yes" or "No".
        if not signal or signal not in ["Yes", "No"]:
            signal = "No"
            
        return {"status": "success", "variables": {"buying_signal": signal}}

    def handle_ai_summarize_profile(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import summarize_profile
        profile = data.get("lead_profile", {})
        
        workspace_id = data.get("workspace_id", "")
        brain = self._get_unified_brain(workspace_id)
        tcp = brain.get("target_customer_profile", "")
        ai_model = data.get("ai_model", "")
        
        summary = summarize_profile(profile, tcp, ai_model, workspace_id)
        return {"status": "success", "variables": {"profile_summary": summary or "A senior professional in their field."}}

    def handle_ai_detect_competitor(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import detect_competitor
        workspace_id = data.get("workspace_id", "")
        
        profile = data.get("lead_profile", {})
        ai_model = data.get("ai_model", "")
        competitors = data.get("competitors", [])
        
        if isinstance(competitors, str):
            competitors = [c.strip() for c in competitors.split(",")]
            
        found = detect_competitor(profile, competitors, ai_model, workspace_id)
        return {"status": "success", "variables": {"competitor_detected": found}}

    def handle_ai_suggest_best_send_time(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import predict_best_send_time
        profile = data.get("lead_profile", {})
        best_time = predict_best_send_time(profile, ai_model=data.get("ai_model", ""), workspace_id=data.get("workspace_id", ""))
        return {"status": "success", "variables": {"best_send_time": best_time}}

    def handle_ai_query_brain(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        from knowledge.backend.services.elein_ai_service import query_knowledge_base
        reply = data.get("reply_text", "")
        profile = data.get("lead_profile", {})
        workspace_id = data.get("workspace_id", "")
        
        brain = self._get_unified_brain(workspace_id)
        # Layer 1 Paranoia: Only inject relevant objections.
        from knowledge.backend.services.elein_ai_service import _truncate_to_tokens
        
        objections = brain.get("objections", [])
        matched_objections = []
        reply_lower = reply.lower()
        
        # Layer 1 Paranoia: Score and rank matches. Longer triggers are more specific/relevant.
        for o in objections:
            trigger = o.get("trigger", "").lower()
            if not trigger:
                continue
                
            # Exact match is highest priority, partial match is lower
            if trigger in reply_lower:
                matched_objections.append((len(trigger), o))
            elif any(word in reply_lower for word in trigger.split() if len(word) > 4):
                matched_objections.append((0, o))  # Weight 0 for partial word matches
                
        # Sort by weight (descending) so exact, long phrases win.
        matched_objections.sort(key=lambda x: x[0], reverse=True)
        
        # Layer 2 Paranoia: Hard cap at 2 objections to prevent token blowout.
        # Truncate the user's essays to 150 words maximum per playbook.
        relevant_playbook = []
        for weight, o in matched_objections[:2]:
            safe_playbook = _truncate_to_tokens(o.get("playbook", ""), 150)
            relevant_playbook.append(f"- Trigger '{o.get('trigger')}': {safe_playbook}")
                
        playbook_str = "\n".join(relevant_playbook) if relevant_playbook else ""
        
        # Properly pass the playbook string into the designated playbook argument!
        ans = query_knowledge_base(reply, profile, playbook_str, ai_model=data.get("ai_model", ""), workspace_id=workspace_id)
        
        if ans:
            return {"status": "success", "branch": "Response Generated", "variables": {"ai_objection_handler": ans}}
        else:
            return {"status": "success", "branch": "Failed"}

    def handle_view_profile(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.view_profile(linkedin_url)

    def handle_view_profile_repeat(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'view_profile_repeat' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_follow_profile(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.follow_profile(linkedin_url)

    def handle_like_post(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.like_post(linkedin_url)

    def handle_like_top_3_posts(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'like_top_3_posts' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_react_insightful(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.react_to_post(linkedin_url, 'EMPATHY')

    def handle_react_celebrate(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.react_to_post(linkedin_url, 'PRAISE')

    def handle_comment_on_post(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.comment_on_post(linkedin_url, data.get('comment', ''))

    def handle_endorse_skill(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.endorse_skill(linkedin_url)

    def handle_endorse_3_skills(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'endorse_3_skills' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_follow_company(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.follow_company(linkedin_url)

    def handle_congratulate_new_job(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'congratulate_new_job' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_congratulate_anniversary(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'congratulate_anniversary' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_share_post(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.repost(linkedin_url, data.get('share_comment', ''))

    def handle_invite_to_event(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.invite_to_event(linkedin_url, data.get('event_url', ''), data.get('invite_note', ''))

    def handle_connection_request(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        note_strategy = data.get("note_strategy")
        if note_strategy == "No note":
            return self.handle_connection_no_note(data, linkedin_url)
        elif note_strategy == "AI-generated note":
            return self.handle_connection_ai_note(data, linkedin_url)
        elif note_strategy not in ["Fixed note", None, ""]:
            logger.warning(f"[Executor] Unknown note_strategy '{note_strategy}' for {linkedin_url}. Proceeding without note.")
        
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err, "branch": "Failed"}
        
        try:
            if note_strategy == "Fixed note":
                res = self.worker.send_connection_request(linkedin_url, data.get('note', ''), data.get('fallback'))
            else:
                res = self.worker.send_connection_request(linkedin_url, data.get('note'), data.get('fallback'))
                
            if res.get("status") == "success":
                return {"status": "success", "branch": "Sent"}
            else:
                error_msg = res.get("error", "").lower()
                if "already" in error_msg or "connect button not found" in error_msg:
                    return {"status": "success", "branch": "AlreadyConnected"}
                return {"status": "error", "error": res.get("error", "Unknown"), "branch": "Failed"}
        except LinkedInActionOutcomeUnknown:
            raise
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in handle_connection_request: {e}")
            return {"status": "error", "error": str(e), "branch": "Failed"}

    def handle_connection_no_note(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err, "branch": "Failed"}
        
        try:
            res = self.worker.send_connection_request(linkedin_url, None, None)
            
            if res.get("status") == "success":
                return {"status": "success", "branch": "Sent"}
            else:
                error_msg = res.get("error", "").lower()
                if "already" in error_msg or "connect button not found" in error_msg:
                    return {"status": "success", "branch": "AlreadyConnected"}
                return {"status": "error", "error": res.get("error", "Unknown"), "branch": "Failed"}
        except LinkedInActionOutcomeUnknown:
            raise
        except Exception as e:
            logger.error(f"Error in handle_connection_no_note: {e}")
            return {"status": "error", "error": str(e), "branch": "Failed"}

    def handle_connection_ai_note(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'connection_ai_note' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_withdraw_request(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.withdraw_connection_request(linkedin_url)

    def handle_remove_connection(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.remove_connection(linkedin_url)

    def handle_if_connected(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.check_if_connected(linkedin_url)

    def handle_if_replied_positive(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_replied_positive' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_replied_negative(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_replied_negative' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_replied_neutral(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_replied_neutral' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_phone_found(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        try:
            lead = data.get("lead", {}) or {}
            phone = lead.get("phone", "") or data.get("phone", "")
            has_phone = bool(phone and str(phone).strip())
            branch = "Phone found" if has_phone else "Not found"
            return {"status": "success", "branch": branch, "message": f"Phone check: {branch}"}
        except Exception as e:
            logger.error(f"handle_if_phone_found error: {e}")
            return {"status": "error", "branch": "Not found", "error": str(e)}

    def handle_open_profile_check(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.check_open_profile(linkedin_url)

    def handle_if_large_following(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err, "branch": "Normal following"}
        
        try:
            follower_threshold = data.get("follower_threshold", 10000)
            threshold = max(0, int(follower_threshold))
        except (ValueError, TypeError):
            threshold = 10000
            
        try:
            result = self.worker.get_follower_count(linkedin_url)
            if result.get("status") == "success":
                followers = result.get("followers", 0)
                if followers is None:
                    logger.warning(f"Follower count for {linkedin_url} is None, defaulting to Normal following.")
                    return {"status": "success", "branch": "Normal following"}
                if followers >= threshold:
                    return {"status": "success", "branch": "High following"}
                else:
                    return {"status": "success", "branch": "Normal following"}
            else:
                logger.warning(f"Failed to get follower count for {linkedin_url}: {result.get('error')}")
                return {"status": "success", "branch": "Normal following"}
        except Exception as e:
            logger.warning(f"Exception getting follower count for {linkedin_url}: {e}")
            return {"status": "success", "branch": "Normal following"}

    def handle_if_premium_member(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.check_premium_badge(linkedin_url)

    def handle_if_mutual_connections(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_mutual_connections' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_recently_active(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_recently_active' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_has_recent_posts(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_has_recent_posts' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_company_size(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_company_size' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_title_matches(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_title_matches' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_location_matches(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_location_matches' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_industry_matches(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_industry_matches' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_company_hiring(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_company_hiring' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_icp_score_gate(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'icp_score_gate' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_if_meeting_booked(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'if_meeting_booked' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_send_message(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.send_message(linkedin_url, data.get('body', ''))

    def handle_send_ai_message(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        prompt = data.get("prompt") or data.get("pitch")
        if not prompt:
            logger.error("AI message node has no prompt configured")
            return {"status": "error", "error": "AI message node has no prompt configured", "branch": "Failed"}
            
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err, "branch": "Failed"}
        
        from knowledge.backend.services.elein_ai_service import _run_llm_with_failover
        import json
        
        profile = data.get("lead_profile", {})
        workspace_id = data.get("workspace_id", "")
        tone = data.get("tone", "Professional & Direct")
        
        system_prompt = f"You are a sales assistant drafting a LinkedIn message. Tone: {tone}."
        user_prompt = f"Lead Profile: {json.dumps(profile)}\n\nGoal: {prompt}\n\nWrite only the exact message content to send, no quotes, no explanations."
        
        try:
            generated_msg = _run_llm_with_failover(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=250,
                temperature=0.7,
                task="generation",
                ai_model=data.get("ai_model", ""),
                workspace_id=workspace_id
            )
            
            if not generated_msg or not generated_msg.strip():
                return {"status": "error", "error": "AI failed to generate message", "branch": "Failed"}
                
            res = self.worker.send_message(linkedin_url, generated_msg.strip())
            
            if res.get("status") == "success":
                return {"status": "success", "branch": "Sent"}
            else:
                return {"status": "error", "error": res.get("error", "Unknown error sending message"), "branch": "Failed"}
                
        except LinkedInActionOutcomeUnknown:
            raise
        except Exception as e:
            logger.error(f"Error in handle_send_ai_message: {e}")
            return {"status": "error", "error": str(e), "branch": "Failed"}

    def handle_send_message_ab(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'send_message_ab' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_send_voice_note(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        audio_url = data.get("audio_url", "")
        if not audio_url or not audio_url.startswith("https://"):
            logger.error(f"Voice note node has invalid audio_url: {audio_url!r}")
            return {
                "status": "error",
                "error": "Voice note node has no valid audio_url configured (must start with https://). Check campaign node configuration.",
                "requires_approval": True,
                "branch": "Failed"
            }
            
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err, "branch": "Failed"}
        
        try:
            # We don't have direct access to a timeout parameter in the worker call
            # but any network error from the worker will be caught here.
            res = self.worker.send_voice_note(linkedin_url, audio_url)
            if isinstance(res, dict) and res.get("status") == "error":
                logger.error(f"Worker returned error for send_voice_note: {res.get('error')}")
                return {
                    "status": "error",
                    "error": res.get("error", "Worker returned error during send_voice_note"),
                    "branch": "Failed"
                }
            return {"status": "success", "branch": "No reply yet"} 
        except LinkedInActionOutcomeUnknown:
            raise
        except Exception as e:
            logger.exception(f"Exception during handle_send_voice_note: {e}")
            return {"status": "error", "error": str(e), "branch": "Failed"}

    def handle_send_inmail(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.send_inmail(linkedin_url, data.get('subject', ''), data.get('body', ''))

    def handle_send_paid_inmail(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.send_inmail(linkedin_url, data.get('subject', ''), data.get('body', ''))

    def handle_send_message_with_doc(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        return self.worker.send_message_with_attachment(linkedin_url, data.get('body', ''), data.get('doc_url', ''), 'document')

    def handle_send_intro_message(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'send_intro_message' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_send_followup(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'send_followup' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_send_breakup_message(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'send_breakup_message' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_send_reengage_message(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'send_reengage_message' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_send_message_with_image(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'send_message_with_image' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}


    def _send_approval_email(self, workspace_id: str, lead_id: str, generated_reply: str, prospect_message: str, approval_id: str):
        import os, json, urllib.request, time
        import jwt
        
        sendgrid_key = os.environ.get("SENDGRID_API_KEY")
        from_email = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@example.com")
        jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
        if not sendgrid_key or not jwt_secret:
            logger.warning("Missing SENDGRID_API_KEY or SUPABASE_JWT_SECRET. Cannot send approval email.")
            return

        # Fetch workspace owner's email
        ws_res = self.supabase.table("workspaces").select("user_id").eq("id", workspace_id).execute()
        if not ws_res.data:
            return
        user_id = ws_res.data[0]["user_id"]
        user_res = self.supabase.table("user_profiles").select("email").eq("id", user_id).execute()
        if not user_res.data or not user_res.data[0].get("email"):
            return
        to_email = user_res.data[0]["email"]

        # Generate signed magic links
        approve_token = jwt.encode({"approval_id": approval_id, "action": "approve", "exp": time.time() + 172800}, jwt_secret, algorithm="HS256")
        reject_token = jwt.encode({"approval_id": approval_id, "action": "reject", "exp": time.time() + 172800}, jwt_secret, algorithm="HS256")
        
        base_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
        approve_link = f"{base_url}/api/approvals/approve?token={approve_token}"
        reject_link = f"{base_url}/api/approvals/reject?token={reject_token}"

        subject = "Action Required: AI Reply Needs Approval"
        body = f"""An AI reply was generated with low confidence and requires your approval.

Prospect Message:
"{prospect_message}"

Proposed AI Reply:
"{generated_reply}"

Click below to approve or reject (No login required):
Approve: {approve_link}
Reject: {reject_link}
"""
        payload = json.dumps({
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {sendgrid_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                logger.info(f"Approval email sent to {to_email}")
        except Exception as e:
            logger.error(f"Approval email failed: {e}")


    def handle_ai_generate_reply(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        workspace_id = data.get("_workspace_id")
        lead_id = data.get("_lead_id")
        enrollment_id = data.get("_enrollment_id")
        execution_state_id = data.get("_execution_state_id")
        
        if not workspace_id or not lead_id:
            return {"status": "error", "error": "Missing workspace_id or lead_id in context"}
            
        approved_reply = data.get("approved_ai_reply")
        if approved_reply:
            clean_reply = approved_reply
        else:
            msg_res = self.supabase.table("messages").select("message_text").eq("lead_id", lead_id).eq("direction", "inbound").order("created_at", desc=True).limit(1).execute()
            if not msg_res.data:
                return {"status": "error", "error": "No inbound message found for lead"}
                
            lead_message = msg_res.data[0]["message_text"]
            
            from knowledge.backend.services.vector_store import SemanticBrain
            from knowledge.backend.services.knowledge_service import KnowledgeService
            
            vs = SemanticBrain(self.supabase)
            chunks = vs.retrieve(query=lead_message, workspace_id=workspace_id, top_k=3)
            chunk_texts = [c.get("content", "") for c in chunks]
            
            # Determine max similarity
            max_similarity = max([c.get("similarity", 0.0) for c in chunks]) if chunks else 0.0
            
            # Fetch workspace threshold gracefully (in case migration hasn't run yet)
            threshold = 0.65
            try:
                ws_res = self.supabase.table("workspaces").select("ai_reply_confidence_threshold").eq("id", workspace_id).execute()
                if ws_res.data and ws_res.data[0].get("ai_reply_confidence_threshold") is not None:
                    threshold = ws_res.data[0]["ai_reply_confidence_threshold"]
            except Exception:
                pass
            
            synthesis = KnowledgeService.get_synthesis(self.supabase, workspace_id)
            if not synthesis:
                synthesis = {}
                
            synthesis_layer = "CORE VALUE PROP:\n" + synthesis.get('core_value_prop', '') + "\n\n"
            if isinstance(synthesis.get('key_differentiators'), list):
                synthesis_layer += "KEY DIFFERENTIATORS:\n" + ", ".join(synthesis.get('key_differentiators', [])) + "\n\n"
            if isinstance(synthesis.get('proof_points'), list):
                synthesis_layer += "PROOF POINTS:\n" + ", ".join(synthesis.get('proof_points', [])) + "\n\n"
                
            rag_layer = "RELEVANT KNOWLEDGE BASE CHUNKS:\n" + "\n".join(chunk_texts)
            
            system_prompt = f"""You are an expert sales representative answering a prospect's message based ONLY on the knowledge below.
{context_str}

EXECUTION RULES:
1. Acknowledge the prospect's message.
2. If the message is irrelevant, nonsensical, or cannot be answered using the knowledge base, politely decline or pivot, and set confidence=1, grounded_in_knowledge=false.
3. If it is relevant, answer concisely using ONLY the provided facts.
4. Output your response as a JSON object with EXACTLY these keys:
   "reply": (string) Your response to the prospect (under 3 sentences).
   "confidence": (integer 1-10) How confident you are that this perfectly answers their query using ONLY the provided facts.
   "grounded_in_knowledge": (boolean) True ONLY if every specific claim in your reply is directly supported by the knowledge base. Do not hallucinate.

Respond ONLY with valid JSON."""

            from knowledge.backend.services.elein_ai_service import _run_llm_with_failover
            try:
                raw_response = _run_llm_with_failover(system_prompt=system_prompt, user_prompt=f"Prospect message: {lead_message}", workspace_id=workspace_id, max_tokens=500, task="generation")
            except Exception as e:
                return {"status": "error", "error": f"LLM Generation failed: {str(e)}"}
                
            if not raw_response or "Error" in raw_response:
                return {"status": "error", "error": f"LLM Generation failed: {raw_response}"}
                
            import re, json
            match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if not match:
                return {"status": "error", "error": "LLM failed to output JSON format."}
                
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {"status": "error", "error": "LLM output invalid JSON."}
                
            clean_reply = data.get("reply", "")
            confidence = data.get("confidence", 0)
            grounded = data.get("grounded_in_knowledge", False)
            
            # Reject suspiciously short replies
            alphanumeric = [c for c in clean_reply if c.isalnum()]
            if len(clean_reply) < 15 or len(alphanumeric) < 5:
                return {"status": "error", "error": f"LLM output rejected as invalid/hallucinated: {clean_reply}"}
                
            # OVERLAP CHECK
            def check_overlap(reply_text, context_text):
                reply_lower = reply_text.lower()
                context_lower = context_text.lower()
                # 1. Number check (strict)
                numbers = set(re.findall(r'\b\d+[\.,]?\d*\b', reply_lower))
                for num in numbers:
                    if num not in context_lower:
                        return False, f"Number '{num}' not in context"
                # 2. Substantive word overlap
                words = re.findall(r'\b[a-z]{5,}\b', reply_lower)
                stopwords = {"there", "their", "about", "would", "could", "should", "which", "where", "hello", "thanks", "please", "reach", "looking", "these", "those", "because", "cannot", "using", "provided", "really", "going"}
                substantive = [w for w in words if w not in stopwords]
                if not substantive:
                    return True, "No substantive words to check"
                overlap_count = sum(1 for w in substantive if w in context_lower)
                ratio = overlap_count / len(substantive)
                if ratio < 0.4:
                    return False, f"Overlap ratio too low: {ratio:.2f}"
                return True, "Overlap ok"
                
            overlap_pass, overlap_reason = check_overlap(clean_reply, context_str)
            
            # THE GATE
            approved_by_gate = (confidence >= 9) and grounded and overlap_pass
            
            if not approved_by_gate:
                import uuid
                approval_id = str(uuid.uuid4())
                try:
                    self.supabase.table("ai_reply_approvals").insert({
                        "id": approval_id,
                        "workspace_id": workspace_id,
                        "lead_id": lead_id,
                        "enrollment_id": enrollment_id,
                        "execution_state_id": execution_state_id,
                        "generated_reply": clean_reply,
                        "retrieval_score": max_similarity
                    }).execute()
                    
                    self.supabase.table("campaign_execution_states").update({
                        "status": "awaiting_approval"
                    }).eq("id", execution_state_id).execute()
                    
                    self._send_approval_email(workspace_id, lead_id, clean_reply, lead_message, approval_id)
                except Exception as e:
                    return {"status": "error", "error": f"Failed to queue for approval: {e}"}
                    
                msg = f"Queued for review. Conf: {confidence}, Grounded: {grounded}, Overlap: {overlap_pass} ({overlap_reason})"
                return {"status": "awaiting_approval", "message": msg}
                
        # HIGH CONFIDENCE PATH OR APPROVED PATH
        err = self._require_worker(linkedin_url)
        if err: return {"status": "error", "error": err}
        
        # Dispatch to LinkedIn
        res = self.worker.send_message(linkedin_url, clean_reply)
        
        # Log the outbound message to the messages table
        import uuid
        account_id = data.get("_account_id")
        if res.get("status") == "success":
            try:
                self.supabase.table("messages").insert({
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "account_id": account_id,
                    "lead_id": lead_id,
                    "sender_name": "AI Assistant",
                    "message_text": clean_reply,
                    "direction": "outbound"
                }).execute()
            except Exception as db_e:
                import logging
                logging.error(f"Failed to log outbound AI message: {db_e}")
                
        return res
    def handle_ai_buying_signal(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'ai_buying_signal' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_ai_write_connection_note(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        logger.warning(f"Action 'ai_write_connection_note' called on {linkedin_url} but has no worker method")
        return {"status": "not_implemented", "error": "LinkedIn worker method not yet built"}

    def handle_retry_step(self, data: dict, linkedin_url: str) -> dict:
        return {"status": "success", "message": "Retry requested (Note: engine support needed to actually jump backwards).", "output": "output"}



    def handle_if_replied(self, data: dict, linkedin_url: str) -> dict:
        """
        Reads the AI-detected sentiment from lead variables.
        Expected variable key: 'last_reply_sentiment' (set by ai_detect_sentiment handler).
        Returns output branch: Positive / Negative / Neutral / No Reply
        """
        try:
            sentiment = data.get("last_reply_sentiment", "No Reply")
            valid_outputs = ["Positive", "Negative", "Neutral", "No Reply"]
            output = sentiment if sentiment in valid_outputs else "No Reply"
            return {"status": "success", "branch": output, "message": f"Reply sentiment: {output}"}
        except Exception as e:
            logger.error(f"handle_if_replied error: {e}")
            return {"status": "error", "branch": "No Reply", "error": str(e)}


    def handle_push_to_hubspot(self, data: dict, linkedin_url: str) -> dict:
        try:
            res = self.supabase.table("leads").select("*").eq("workspace_id", self.workspace_id).eq("linkedin_url", linkedin_url).limit(1).execute()
            if not res.data:
                return {"status": "error", "error": "Lead not found in database"}
            lead_data = res.data[0]
            
            w_res = self.supabase.table("workspaces").select("hubspot_token").eq("id", self.workspace_id).single().execute()
            token = w_res.data.get("hubspot_token") if w_res.data else None
            if not token:
                return {"status": "error", "error": "HubSpot token not found for workspace"}
                
            success = push_to_hubspot(lead_data, "lead", token, self.supabase)
            if success:
                return {"status": "success", "message": "Pushed to HubSpot"}
            else:
                return {"status": "error", "error": "Failed to push to HubSpot"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def handle_push_to_crm(self, data: dict, linkedin_url: str) -> dict:

        provider = data.get("provider", "HubSpot").lower().replace(" ", "")
        handler_map = {
            "hubspot": self.handle_push_to_hubspot,
            "salesforce": self.handle_push_to_salesforce,
            "pipedrive": self.handle_push_to_pipedrive,
            "notion": self.handle_push_to_notion,
            "airtable": self.handle_push_to_airtable,
        }
        handler = handler_map.get(provider)
        if handler:
            return handler(data, linkedin_url)
        return {"status": "error", "output": "output", "error": f"Unknown CRM provider: {provider}"}

    def handle_add_to_email_sequencer(self, data: dict, linkedin_url: str) -> dict:
        provider = data.get("provider", "Smartlead").lower().replace(" ", "")
        handler_map = {
            "smartlead": self.handle_add_to_smartlead,
            "instantly": self.handle_add_to_instantly,
            "emailbison": self.handle_add_to_emailbison,
            "lemlist": self.handle_add_to_lemlist,
            "apollo": self.handle_add_to_apollo,
        }
        handler = handler_map.get(provider)
        if handler:
            return handler(data, linkedin_url)
        return {"status": "error", "output": "output", "error": f"Unknown sequencer provider: {provider}"}

    def handle_update_lead_status(self, data: dict, linkedin_url: str) -> dict:
        try:
            status = data.get("status", "Unknown")
            # Alias old mark_* node types
            alias_map = {
                "MQL": "Interested",  # keep backward compat semantics
            }
            logger.info(f"Updating lead status to: {status} for {linkedin_url}")
            return {"status": "success", "output": "output", "message": f"Lead status updated to: {status}", "variables": {"lead_status": status}}
        except Exception as e:
            logger.error(f"handle_update_lead_status error: {e}")
            return {"status": "error", "output": "output", "error": str(e)}

    def handle_if_lead_matches(self, data: dict, linkedin_url: str) -> dict:
        try:
            # All criteria are optional; unset criteria are skipped (AND logic on set criteria)
            matched = True
            reasons = []

            title_keywords = [k.strip().lower() for k in data.get("title_keywords", "").split(",") if k.strip()]
            locations = [l.strip().lower() for l in data.get("locations", "").split(",") if l.strip()]
            industries = [i.strip().lower() for i in data.get("industries", "").split(",") if i.strip()]
            min_hc = data.get("min_headcount")
            max_hc = data.get("max_headcount")

            lead_title = str(data.get("lead_title", "")).lower()
            lead_location = str(data.get("lead_location", "")).lower()
            lead_industry = str(data.get("lead_industry", "")).lower()
            lead_headcount = int(data.get("lead_headcount") or 0)

            if title_keywords and not any(kw in lead_title for kw in title_keywords):
                matched = False
                reasons.append("title_mismatch")
            if locations and not any(loc in lead_location for loc in locations):
                matched = False
                reasons.append("location_mismatch")
            if industries and not any(ind in lead_industry for ind in industries):
                matched = False
                reasons.append("industry_mismatch")
            if min_hc and lead_headcount < int(min_hc):
                matched = False
                reasons.append("headcount_below_min")
            if max_hc and lead_headcount > int(max_hc):
                matched = False
                reasons.append("headcount_above_max")

            output = "Matches" if matched else "No match"
            return {"status": "success", "branch": output, "message": f"Lead criteria check: {output}", "reasons": reasons}
        except Exception as e:
            logger.error(f"handle_if_lead_matches error: {e}")
            return {"status": "error", "output": "No match", "error": str(e)}

    def handle_react_to_post(self, data: dict, linkedin_url: str) -> dict:
        # Route to existing like_post handler — the worker handles quantity and reaction_type
        return self.handle_like_post(data, linkedin_url)

    def handle_mark_mql(self, data: dict, linkedin_url: str) -> dict: data["status"] = "MQL"; return self.handle_update_lead_status(data, linkedin_url)
    def handle_mark_sql(self, data: dict, linkedin_url: str) -> dict: data["status"] = "SQL"; return self.handle_update_lead_status(data, linkedin_url)
    def handle_mark_converted(self, data: dict, linkedin_url: str) -> dict: data["status"] = "Converted"; return self.handle_update_lead_status(data, linkedin_url)
    def handle_mark_not_interested(self, data: dict, linkedin_url: str) -> dict: data["status"] = "Not Interested"; return self.handle_update_lead_status(data, linkedin_url)
    def handle_mark_opted_out(self, data: dict, linkedin_url: str) -> dict: data["status"] = "Opted Out (GDPR)"; return self.handle_update_lead_status(data, linkedin_url)

    def handle_mark_interested(self, data: dict, linkedin_url: str) -> dict: data["status"] = "Interested"; return self.handle_update_lead_status(data, linkedin_url)

    def handle_ai_query_knowledge_base(self, data, linkedin_url): return self.handle_ai_query_brain(data, linkedin_url)

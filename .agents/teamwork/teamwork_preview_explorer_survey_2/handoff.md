# Handoff Report: Requirements R2 & R3 Investigation

## 1. Observation

### R2: `if_replied_*` Sentiment Variable Mismatch & Pipeline Audit

1. **Current State in `campaigns/backend/services/elein_executor.py`**:
   - `handle_ai_detect_sentiment` (lines 325-336):
     ```python
     def handle_ai_detect_sentiment(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
         from knowledge.backend.services.elein_ai_service import classify_reply_sentiment
         reply_text = data.get("reply_text", "")
         
         workspace_id = data.get("workspace_id", "")
         brain = self._get_unified_brain(workspace_id)
         core_value_prop = brain.get("core_value_prop", "")
         ai_model = data.get("ai_model", "")
         
         sentiment = classify_reply_sentiment(reply_text, core_value_prop, ai_model, workspace_id)
         return {"status": "success", "variables": {"ai_sentiment": sentiment}}
     ```
     - Writes to `variables["ai_sentiment"]`.
     - Fails to return a `"branch"` key even though `core/frontend/lib/eiNodeDefs.ts` defines `outputs: ["Positive", "Neutral", "Negative"]` for `ai_detect_sentiment`.
     - Relies entirely on `data.get("reply_text")` being passed in memory; if `reply_text` is empty, it classifies an empty string instead of pulling the lead's inbound reply from the database.

   - `_get_reply_sentiment(self, data: dict) -> str` (lines 642-660):
     ```python
     def _get_reply_sentiment(self, data: dict) -> str:
         lead_id = data.get("lead", {}).get("id")
         if not lead_id or not self.supabase:
             return "No Reply"
             
         msg_res = self.supabase.table("messages").select("message_text").eq("lead_id", lead_id).eq("direction", "inbound").order("created_at", desc=True).limit(1).execute()
         if not msg_res.data:
             return "No Reply"
             
         reply_text = msg_res.data[0]["message_text"]
         workspace_id = data.get("workspace_id", self.workspace_id)
         brain = self._get_unified_brain(workspace_id)
         core_value_prop = brain.get("core_value_prop", "")
         ai_model = data.get("ai_model", "")
         
         from knowledge.backend.services.elein_ai_service import classify_reply_sentiment
         sentiment = classify_reply_sentiment(reply_text, core_value_prop, ai_model, workspace_id)
         return sentiment
     ```
     - Does NOT inspect `data.get("variables", {}).get("ai_sentiment")` or `data.get("ai_sentiment")` before querying the database and running LLM inference.
     - Extracts `lead_id` only via `data.get("lead", {}).get("id")`. When invoked by `elein_orchestrator.py`, `_lead_id` or `lead_id` or `opportunity_id` is passed at the root of `resolved_data`, so `data.get("lead")` is often `None`, causing `_get_reply_sentiment` to prematurely return `"No Reply"`.
     - Does not write back the classified sentiment into `variables["ai_sentiment"]`.

   - `handle_if_replied_positive`, `handle_if_replied_negative`, `handle_if_replied_neutral` (lines 661-675):
     ```python
     def handle_if_replied_positive(self, data: dict, linkedin_url: str) -> dict:
         sentiment = self._get_reply_sentiment(data).lower()
         if sentiment == "no reply": return {"status": "success", "branch": "No Reply"}
         return {"status": "success", "branch": "Positive" if "positive" in sentiment else "Not Positive"}

     def handle_if_replied_negative(self, data: dict, linkedin_url: str) -> dict:
         sentiment = self._get_reply_sentiment(data).lower()
         if sentiment == "no reply": return {"status": "success", "branch": "No Reply"}
         return {"status": "success", "branch": "Negative" if "negative" in sentiment else "Not Negative"}

     def handle_if_replied_neutral(self, data: dict, linkedin_url: str) -> dict:
         sentiment = self._get_reply_sentiment(data).lower()
         if sentiment == "no reply": return {"status": "success", "branch": "No Reply"}
         return {"status": "success", "branch": "Neutral" if "neutral" in sentiment else "Not Neutral"}
     ```
     - Branch name mismatch: in `core/frontend/lib/eiNodeDefs.ts`, the outputs are `["Positive", "Other"]`, `["Negative", "Other"]`, `["Neutral", "Other"]`. The backend handlers return `"Not Positive"`, `"Not Negative"`, `"Not Neutral"`, or `"No Reply"`.
     - In `campaigns/backend/services/elein_orchestrator.py` (lines 794-801):
       ```python
       branch_edge = next((e for e in outgoing_edges if e.get("source_handle") == branch_handle), None)
       if not branch_edge:
           err_msg = f"Lead {state['opportunity_id']} stuck: node {current_node_id} returned branch '{branch_handle}' but no matching edge found. Marking lead as ERROR."
       ```
       Because the frontend generated edge handle is `"Other"`, matching fails, and the lead is marked with a runtime ERROR.

   - `handle_if_replied` (lines 1243-1252):
     In initial commit `f003cfe84baf00e56ea174039338ae4e3af88392`:
     ```python
     def handle_if_replied(self, data: dict, linkedin_url: str) -> dict:
         """
         Reads the AI-detected sentiment from lead variables.
         Expected variable key: 'last_reply_sentiment' (set by ai_detect_sentiment handler).
         Returns output branch: Positive / Negative / Neutral / No Reply
         """
         sentiment = data.get("last_reply_sentiment", "No Reply")
     ```
     This legacy docstring and code explicitly expected `'last_reply_sentiment'`, while `handle_ai_detect_sentiment` produced `'ai_sentiment'`.

2. **Registered Sentiment Variables in Frontend & API Gateways**:
   - `core/frontend/lib/treeValidator.ts` (line 187):
     ```typescript
     const ALLOWED_VARIABLES = [
       'first_name', 'last_name', 'company', 'job_title', 'location', 'industry', 'mutual_connections',
       'ai_icebreaker', 'ai_sentiment', 'ai_brain_reply', 'best_send_time', 'work_email', 'competitor_detected'
     ];
     ```
   - `campaigns/backend/routers/elein.py` (line 1753):
     ```python
     allowed_vars = {
         'first_name', 'last_name', 'company', 'job_title', 'location', 'industry', 'mutual_connections',
         'ai_icebreaker', 'ai_sentiment', 'ai_brain_reply', 'best_send_time', 'work_email', 'competitor_detected'
     }
     ```
   - `inbox/backend/routers/inbox.py` (line 748):
     ```python
     allowed_vars = {
         'first_name', 'last_name', 'company', 'job_title', 'location', 'industry', 'mutual_connections',
         'ai_icebreaker', 'ai_sentiment', 'ai_brain_reply', 'best_send_time', 'work_email', 'competitor_detected'
     }
     ```
   - **Conclusion on Key Standardization**: The entire platform already standardizes on **`ai_sentiment`**. There are no references to `last_reply_sentiment` in `treeValidator.ts`, `elein.py`, or `inbox.py`. To eliminate dead code and prevent mismatches, all handlers and docstrings must standardize on `ai_sentiment`, while writing both `ai_sentiment` and `last_reply_sentiment` into `variables` for backward compatibility.

---

### R3: Missing Node Handlers & Worker Architecture

1. **Current Node Definitions in `core/frontend/lib/eiNodeDefs.ts`**:
   - `like_top_3_posts` (lines 117-128): category `warmup`, outputs `["then"]`, fields `[{ key: "reaction_type", options: ["Like", "Insightful", "Celebrate"] }]`. `comingSoon` is absent (enabled).
   - `view_profile_repeat` (lines 130-139): category `warmup`, outputs `["then"]`, delayDefault 3 days. `comingSoon` is absent (enabled).
   - `congratulate_new_job` (lines 141-152): category `warmup`, outputs `["then"]`, fields `[{ key: "message", default placeholder: "Congrats on the new role at {{company}}, {{first_name}}!" }]`. `comingSoon` is absent (enabled).
   - `congratulate_anniversary` (lines 154-165): category `warmup`, outputs `["then"]`, fields `[{ key: "message", default placeholder: "Happy work anniversary, {{first_name}}! A real milestone." }]`. `comingSoon` is absent (enabled).
   - `endorse_3_skills` (lines 215-226): category `connect`, outputs `["then"]`, fields `[{ key: "fallback", options: ["Endorse however many exist", "Skip this step"] }]`. `comingSoon` is absent (enabled).

2. **Enrichment Nodes in `core/frontend/lib/eiNodeDefs.ts` (lines 822-975)**:
   All 12 data enrichment / multichannel nodes are verified to have `comingSoon: true`:
   - `find_email` (line 823): `comingSoon: true`
   - `find_personal_email` (line 835): `comingSoon: true`
   - `find_phone` (line 847): `comingSoon: true`
   - `find_tech_stack` (line 859): `comingSoon: true`
   - `find_funding_round` (line 873): `comingSoon: true`
   - `find_headcount` (line 887): `comingSoon: true`
   - `find_job_postings` (line 899): `comingSoon: true`
   - `get_linkedin_activity` (line 913): `comingSoon: true`
   - `get_mutual_connections` (line 925): `comingSoon: true`
   - `verify_email` (line 937): `comingSoon: true`
   - `send_slack_alert` (line 953): `comingSoon: true`
   - `send_webhook` (line 968): `comingSoon: true`

3. **Current Stub Handlers in `campaigns/backend/services/elein_executor.py`**:
   - `handle_view_profile_repeat` (lines 498-501):
     Calls `self.worker.view_profile(linkedin_url)` without logging to `action_log`.
   - `handle_like_top_3_posts` (lines 513-516):
     Calls `self.worker.like_post(linkedin_url)` once. Ignores the remaining 2 posts, ignores `reaction_type`, does not consume daily limits for posts 2 & 3, and does not log to `action_log`.
   - `handle_endorse_3_skills` (lines 538-541):
     Calls `self.worker.endorse_skill(linkedin_url)` once. Ignores remaining 2 skills, ignores `fallback` setting, and does not log to `action_log`.
   - `handle_congratulate_new_job` (lines 548-552):
     Calls `self.worker.send_message(linkedin_url, message)`, but does not call `self._log_outbound_message(data, message)` to record the message in `messages`, and does not log to `action_log`.
   - `handle_congratulate_anniversary` (lines 554-558):
     Calls `self.worker.send_message(linkedin_url, message)`, but does not call `self._log_outbound_message(data, message)` to record the message in `messages`, and does not log to `action_log`.

4. **Worker Capabilities in `integrations/backend/services/linkedin_worker.py`**:
   - `LinkedInWorker` provides:
     - `view_profile(profile_url)` (line 349)
     - `like_post(profile_url)` (line 444)
     - `react_to_post(profile_url, reaction="LIKE")` (line 471)
     - `endorse_skill(profile_url)` (line 532)
     - `send_message(profile_url, message)` (line 720)
   - It does NOT yet have `like_top_3_posts` or `endorse_3_skills` methods.

5. **Limit Consumption Pattern (`try_consume_daily_action`)**:
   - In `elein_executor.py` (lines 170-177):
     `execute()` checks `ACTION_TYPE_MAP` and calls `self._check_limit(mapped_action)` which executes RPC `try_consume_daily_action`.
   - For `like_top_3_posts` and `endorse_3_skills`:
     The initial action (post 1 or skill 1) is consumed by `execute()`. Posts 2 & 3 and skills 2 & 3 require subsequent calls to `self._check_limit()`.

6. **Audit Table `action_log` Schema**:
   From `backend/supabase_schema.sql` (lines 462-472):
   - `id`: UUID (auto-generated)
   - `workspace_id`: UUID
   - `account_id`: UUID (optional)
   - `lead_state_id` / `execution_state_id`: UUID (optional)
   - `action_type`: TEXT
   - `result`: TEXT ('success', 'error', 'skipped')
   - `error_detail`: TEXT (optional)
   - `metadata`: JSONB
   - `executed_at`: TIMESTAMPTZ (auto-generated)

---

## 2. Logic Chain

1. **R2 Sentiment Pipeline Logic Chain**:
   - *Observation*: `handle_ai_detect_sentiment` stores `variables["ai_sentiment"]`, but `handle_if_replied` documented expecting `variables["last_reply_sentiment"]`.
   - *Observation*: `core/frontend/lib/treeValidator.ts`, `campaigns/backend/routers/elein.py`, and `inbox/backend/routers/inbox.py` all list `'ai_sentiment'` in `ALLOWED_VARIABLES`.
   - *Deduction*: `ai_sentiment` is the intended canonical variable. Setting `{"ai_sentiment": sentiment, "last_reply_sentiment": sentiment}` preserves backwards compatibility while satisfying the requirement to standardize.
   - *Observation*: `_get_reply_sentiment(data)` unconditionally runs an external LLM call and queries `messages`, ignoring whether sentiment was already determined. Furthermore, it queries with `lead_id = data.get("lead", {}).get("id")`, which is null when orchestrator sends `_lead_id`.
   - *Deduction*: `_get_reply_sentiment` must check `data.get("ai_sentiment")` and `data.get("variables", {}).get("ai_sentiment")` first. If null, extract `lead_id` across `_lead_id`, `lead_id`, and `opportunity_id` before querying `messages`.
   - *Observation*: `if_replied_positive` branches to `"Not Positive"`, but `eiNodeDefs.ts` defines `outputs: ["Positive", "Other"]`. Orchestrator fails to route edges labeled `"Other"`.
   - *Deduction*: The handlers must return `"Positive"`, `"Negative"`, or `"Neutral"` on truthy match, and `"Other"` otherwise.

2. **R3 Node Handlers Logic Chain**:
   - *Observation*: `like_top_3_posts` and `endorse_3_skills` currently only call worker single-action methods (`like_post` and `endorse_skill`) once.
   - *Observation*: Neither handler loops, neither consumes daily limits for additional actions, and neither writes to `action_log`.
   - *Observation*: `congratulate_new_job` and `congratulate_anniversary` send messages via `worker.send_message`, but bypass `self._log_outbound_message` and write nothing to `action_log`.
   - *Deduction*:
     - In `integrations/backend/services/linkedin_worker.py`, implement `like_top_3_posts` and `endorse_3_skills` to automate Playwright DOM actions for multiple posts and skills.
     - In `campaigns/backend/services/elein_executor.py`, build a centralized `_log_action` helper for `action_log` writes.
     - In `handle_like_top_3_posts` and `handle_endorse_3_skills`, call worker methods or fallback loops, check limits via `_check_limit` for subsequent actions, and record completion in `action_log`.
     - In `handle_congratulate_new_job` and `handle_congratulate_anniversary`, call `_log_outbound_message` on success and record execution in `action_log`.
     - In `handle_view_profile_repeat`, record execution in `action_log`.

---

## 3. Caveats

1. **Worker Availability in Headless / Offline Testing**:
   During tests or when LinkedIn credentials are not bound to an executor instance, `self.worker` may be `None` or a `MagicMock`. The handlers must guard worker calls with `err = self._require_worker(linkedin_url)` and handle mock responses gracefully.
2. **Rate Limit Exhaustion Mid-Batch**:
   If a user has 1 daily action remaining when executing `like_top_3_posts`, the 1st post will succeed, but the 2nd post will be rejected by `try_consume_daily_action`. The handler must catch this gracefully, record the partial count in `action_log`, and return success with the actual number of posts liked rather than throwing an unhandled exception.
3. **LinkedIn DOM Volatility**:
   LinkedIn frequently modifies DOM attributes. The worker methods in `linkedin_worker.py` must use flexible selector chains (e.g. `button[aria-label^='Like'], button[aria-label^='React to']`) and timeouts to avoid hanging.

---

## 4. Conclusion & Proposed Implementation

### A. R2 Implementation: Align Sentiment Variable & Handlers
Standardize on `ai_sentiment` end-to-end.

In `campaigns/backend/services/elein_executor.py`:
```python
    def _get_reply_sentiment(self, data: dict) -> str:
        """
        Retrieves reply sentiment from cached variables ('ai_sentiment' / 'last_reply_sentiment')
        or queries the database for the most recent inbound message and runs AI sentiment classification.
        """
        # 1. Check if sentiment was already classified
        lead_vars = data.get("lead", {}).get("variables", {}) if isinstance(data.get("lead"), dict) else {}
        direct_vars = data.get("variables", {}) if isinstance(data.get("variables"), dict) else {}
        
        cached = (
            data.get("ai_sentiment")
            or direct_vars.get("ai_sentiment")
            or lead_vars.get("ai_sentiment")
            or data.get("last_reply_sentiment")
            or direct_vars.get("last_reply_sentiment")
            or lead_vars.get("last_reply_sentiment")
        )
        if cached and str(cached).strip():
            return str(cached).strip()

        # 2. Extract lead ID from all parameter locations (Paranoia Layer 1)
        lead_id = (
            data.get("lead", {}).get("id")
            if isinstance(data.get("lead"), dict) else None
        ) or data.get("_lead_id") or data.get("lead_id") or data.get("opportunity_id")
        
        if not lead_id or not self.supabase:
            return "No Reply"
            
        try:
            msg_res = self.supabase.table("messages").select("message_text").eq("lead_id", lead_id).eq("direction", "inbound").order("created_at", desc=True).limit(1).execute()
            if not msg_res.data:
                return "No Reply"
                
            reply_text = msg_res.data[0]["message_text"]
            workspace_id = data.get("_workspace_id") or data.get("workspace_id") or self.workspace_id
            brain = self._get_unified_brain(workspace_id)
            core_value_prop = brain.get("core_value_prop", "")
            ai_model = data.get("ai_model", "")
            
            from knowledge.backend.services.elein_ai_service import classify_reply_sentiment
            sentiment = classify_reply_sentiment(reply_text, core_value_prop, ai_model, workspace_id)
            return sentiment or "Neutral"
        except Exception as e:
            logger.error(f"Error in _get_reply_sentiment: {e}")
            return "No Reply"

    def handle_ai_detect_sentiment(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        reply_text = data.get("reply_text", "")
        if reply_text:
            workspace_id = data.get("_workspace_id") or data.get("workspace_id", "") or self.workspace_id
            brain = self._get_unified_brain(workspace_id)
            core_value_prop = brain.get("core_value_prop", "")
            ai_model = data.get("ai_model", "")
            from knowledge.backend.services.elein_ai_service import classify_reply_sentiment
            sentiment = classify_reply_sentiment(reply_text, core_value_prop, ai_model, workspace_id)
        else:
            sentiment = self._get_reply_sentiment(data)

        normalized = sentiment.title() if sentiment and sentiment.lower() != "no reply" else "Neutral"
        branch = normalized if normalized in ["Positive", "Negative", "Neutral"] else "Neutral"
        
        return {
            "status": "success",
            "branch": branch,
            "variables": {
                "ai_sentiment": normalized,
                "last_reply_sentiment": normalized
            }
        }

    def handle_if_replied(self, data: dict, linkedin_url: str) -> dict:
        """
        Reads the AI-detected sentiment from lead variables ('ai_sentiment') or queries inbound messages.
        Expected variable key: 'ai_sentiment' (set by ai_detect_sentiment handler).
        Returns output branch: Positive / Negative / Neutral / No Reply
        """
        try:
            sentiment = self._get_reply_sentiment(data)
            valid_outputs = ["Positive", "Negative", "Neutral", "No Reply"]
            output = sentiment.title() if sentiment.title() in valid_outputs else "No Reply"
            return {
                "status": "success",
                "branch": output,
                "message": f"Reply sentiment: {output}",
                "variables": {
                    "ai_sentiment": output,
                    "last_reply_sentiment": output
                }
            }
        except Exception as e:
            logger.error(f"handle_if_replied error: {e}")
            return {"status": "error", "branch": "No Reply", "error": str(e)}

    def handle_if_replied_positive(self, data: dict, linkedin_url: str) -> dict:
        sentiment = self._get_reply_sentiment(data).lower()
        branch = "Positive" if "positive" in sentiment else "Other"
        sentiment_val = sentiment.title() if sentiment != "no reply" else "No Reply"
        return {
            "status": "success",
            "branch": branch,
            "variables": {
                "ai_sentiment": sentiment_val,
                "last_reply_sentiment": sentiment_val
            }
        }

    def handle_if_replied_negative(self, data: dict, linkedin_url: str) -> dict:
        sentiment = self._get_reply_sentiment(data).lower()
        branch = "Negative" if "negative" in sentiment else "Other"
        sentiment_val = sentiment.title() if sentiment != "no reply" else "No Reply"
        return {
            "status": "success",
            "branch": branch,
            "variables": {
                "ai_sentiment": sentiment_val,
                "last_reply_sentiment": sentiment_val
            }
        }

    def handle_if_replied_neutral(self, data: dict, linkedin_url: str) -> dict:
        sentiment = self._get_reply_sentiment(data).lower()
        branch = "Neutral" if "neutral" in sentiment else "Other"
        sentiment_val = sentiment.title() if sentiment != "no reply" else "No Reply"
        return {
            "status": "success",
            "branch": branch,
            "variables": {
                "ai_sentiment": sentiment_val,
                "last_reply_sentiment": sentiment_val
            }
        }
```

---

### B. R3 Implementation: 5 Engagement Handlers & Worker Methods

1. **Centralized Action Logger in `EleInNodeExecutor`**:
```python
    def _log_action(
        self,
        data: Dict[str, Any],
        action_type: str,
        result: str = "success",
        error_detail: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Appends an execution event to public.action_log.
        Safe against database connection failures and schema field aliases.
        """
        if not self.supabase:
            return
        try:
            workspace_id = data.get("_workspace_id") or data.get("workspace_id") or getattr(self, "workspace_id", None)
            account_id = data.get("_account_id") or (self.worker.account_id if self.worker else None)
            execution_state_id = data.get("_execution_state_id") or data.get("execution_state_id")
            lead_id = data.get("_lead_id") or (data.get("lead", {}).get("id") if isinstance(data.get("lead"), dict) else None) or data.get("lead_id") or data.get("opportunity_id")

            meta = dict(metadata or {})
            if lead_id and "lead_id" not in meta:
                meta["lead_id"] = lead_id

            payload = {
                "workspace_id": workspace_id,
                "action_type": action_type,
                "result": result,
                "error_detail": error_detail,
                "metadata": meta,
            }
            if account_id:
                payload["account_id"] = account_id
            if execution_state_id:
                payload["execution_state_id"] = execution_state_id
                payload["lead_state_id"] = execution_state_id

            self.supabase.table("action_log").insert(payload).execute()
        except Exception as e:
            logger.warning(f"Failed to record action_log for '{action_type}': {e}")
```

2. **The 5 Production Handlers in `EleInNodeExecutor`**:
```python
    def handle_view_profile_repeat(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err:
            self._log_action(data, "view_profile_repeat", result="error", error_detail=err)
            return {"status": "error", "error": err}
            
        try:
            res = self.worker.view_profile(linkedin_url)
            status = res.get("status", "success")
            self._log_action(
                data,
                "view_profile_repeat",
                result=status,
                error_detail=res.get("error"),
                metadata={"linkedin_url": linkedin_url, "worker_action": res.get("action")}
            )
            return res
        except Exception as e:
            logger.error(f"handle_view_profile_repeat error: {e}")
            self._log_action(data, "view_profile_repeat", result="error", error_detail=str(e))
            return {"status": "error", "error": str(e)}

    def handle_like_top_3_posts(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err:
            self._log_action(data, "like_top_3_posts", result="error", error_detail=err)
            return {"status": "error", "error": err}

        reaction_type = data.get("reaction_type", "Like")
        reaction_map = {"Like": "LIKE", "Insightful": "EMPATHY", "Celebrate": "PRAISE"}
        mapped_reaction = reaction_map.get(reaction_type, "LIKE")

        try:
            if hasattr(self.worker, "like_top_3_posts") and callable(getattr(self.worker, "like_top_3_posts")):
                res = self.worker.like_top_3_posts(linkedin_url, reaction=mapped_reaction)
            else:
                liked_count = 0
                first_res = self.worker.react_to_post(linkedin_url, mapped_reaction) if hasattr(self.worker, "react_to_post") else self.worker.like_post(linkedin_url)
                if first_res.get("status") == "success":
                    liked_count += 1
                    for _ in range(2):
                        limit_err = self._check_limit("react_post")
                        if limit_err:
                            logger.warning(f"Rate limit reached after {liked_count} post likes: {limit_err}")
                            break
                        sub_res = self.worker.react_to_post(linkedin_url, mapped_reaction) if hasattr(self.worker, "react_to_post") else self.worker.like_post(linkedin_url)
                        if sub_res.get("status") == "success":
                            liked_count += 1
                        else:
                            break
                res = {"status": "success", "action": "like_top_3_posts", "count": liked_count} if liked_count > 0 else first_res

            status = res.get("status", "success")
            self._log_action(
                data,
                "like_top_3_posts",
                result=status,
                error_detail=res.get("error"),
                metadata={"linkedin_url": linkedin_url, "reaction_type": reaction_type, "count": res.get("count", 1)}
            )
            return res
        except Exception as e:
            logger.error(f"handle_like_top_3_posts error: {e}")
            self._log_action(data, "like_top_3_posts", result="error", error_detail=str(e))
            return {"status": "error", "error": str(e)}

    def handle_endorse_3_skills(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err:
            self._log_action(data, "endorse_3_skills", result="error", error_detail=err)
            return {"status": "error", "error": err}

        fallback_mode = data.get("fallback", "Endorse however many exist")

        try:
            if hasattr(self.worker, "endorse_3_skills") and callable(getattr(self.worker, "endorse_3_skills")):
                res = self.worker.endorse_3_skills(linkedin_url, max_skills=3)
            else:
                endorsed_count = 0
                first_res = self.worker.endorse_skill(linkedin_url)
                if first_res.get("status") == "success":
                    endorsed_count += 1
                    for _ in range(2):
                        limit_err = self._check_limit("endorse_skill")
                        if limit_err:
                            logger.warning(f"Rate limit reached after {endorsed_count} skill endorsements: {limit_err}")
                            break
                        sub_res = self.worker.endorse_skill(linkedin_url)
                        if sub_res.get("status") == "success":
                            endorsed_count += 1
                        else:
                            break
                elif fallback_mode == "Skip this step":
                    res = {"status": "skipped", "reason": "Fewer than 3 skills found and fallback is to skip"}
                    self._log_action(data, "endorse_3_skills", result="skipped", metadata={"reason": res["reason"]})
                    return res
                res = {"status": "success", "action": "endorse_3_skills", "count": endorsed_count} if endorsed_count > 0 else first_res

            status = res.get("status", "success")
            self._log_action(
                data,
                "endorse_3_skills",
                result=status,
                error_detail=res.get("error"),
                metadata={"linkedin_url": linkedin_url, "fallback_mode": fallback_mode, "count": res.get("count", 1)}
            )
            return res
        except Exception as e:
            logger.error(f"handle_endorse_3_skills error: {e}")
            self._log_action(data, "endorse_3_skills", result="error", error_detail=str(e))
            return {"status": "error", "error": str(e)}

    def handle_congratulate_new_job(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err:
            self._log_action(data, "congratulate_new_job", result="error", error_detail=err)
            return {"status": "error", "error": err}

        message = data.get("message") or "Congratulations on the new role!"
        try:
            res = self.worker.send_message(linkedin_url, message)
            status = res.get("status", "success")
            if status == "success":
                self._log_outbound_message(data, message)
                
            self._log_action(
                data,
                "congratulate_new_job",
                result=status,
                error_detail=res.get("error"),
                metadata={"linkedin_url": linkedin_url, "message_preview": message[:100]}
            )
            return res
        except Exception as e:
            logger.error(f"handle_congratulate_new_job error: {e}")
            self._log_action(data, "congratulate_new_job", result="error", error_detail=str(e))
            return {"status": "error", "error": str(e)}

    def handle_congratulate_anniversary(self, data: Dict[str, Any], linkedin_url: Optional[str]) -> Dict[str, Any]:
        err = self._require_worker(linkedin_url)
        if err:
            self._log_action(data, "congratulate_anniversary", result="error", error_detail=err)
            return {"status": "error", "error": err}

        message = data.get("message") or "Happy work anniversary!"
        try:
            res = self.worker.send_message(linkedin_url, message)
            status = res.get("status", "success")
            if status == "success":
                self._log_outbound_message(data, message)

            self._log_action(
                data,
                "congratulate_anniversary",
                result=status,
                error_detail=res.get("error"),
                metadata={"linkedin_url": linkedin_url, "message_preview": message[:100]}
            )
            return res
        except Exception as e:
            logger.error(f"handle_congratulate_anniversary error: {e}")
            self._log_action(data, "congratulate_anniversary", result="error", error_detail=str(e))
            return {"status": "error", "error": str(e)}
```

3. **Playwright Worker Implementations in `integrations/backend/services/linkedin_worker.py`**:
```python
    @linkedin_action_safe
    def like_top_3_posts(self, profile_url: str, reaction: str = "LIKE") -> Dict[str, Any]:
        with self._get_or_create_context() as page:
            try:
                page.goto(f"{profile_url.rstrip('/')}/recent-activity/all/", wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 6)
                self._human_scroll(page)
                
                like_btns = page.locator("button[aria-label^='Like'], button[aria-label^='React to']").all()
                if not like_btns:
                    return {"status": "error", "error": "No recent posts found to like"}
                
                liked_count = 0
                for btn in like_btns[:3]:
                    try:
                        if btn.is_visible(timeout=3000):
                            with self._mutation_boundary():
                                btn.click(delay=random.randint(50, 150))
                                liked_count += 1
                                self._human_delay(2, 4)
                    except Exception as inner_e:
                        logger.warning(f"Error liking post {liked_count+1}: {inner_e}")
                        continue

                if liked_count > 0:
                    logger.info(f"[LIVE] like_top_3_posts: {liked_count} posts liked on {profile_url}")
                    return {"status": "success", "action": "like_top_3_posts", "count": liked_count}
                return {"status": "error", "error": "Could not click any like buttons"}
            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}

    @linkedin_action_safe
    def endorse_3_skills(self, profile_url: str, max_skills: int = 3) -> Dict[str, Any]:
        with self._get_or_create_context() as page:
            try:
                page.goto(profile_url, wait_until="domcontentloaded")
                self._check_for_challenge(page)
                self._human_delay(3, 5)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                self._human_delay(1, 2)
                endorse_btns = page.locator("button[aria-label^='Endorse']").all()
                if not endorse_btns:
                    return {"status": "error", "error": "No endorse buttons found on profile"}
                
                endorsed_count = 0
                for btn in endorse_btns[:max_skills]:
                    try:
                        if btn.is_visible(timeout=3000):
                            with self._mutation_boundary():
                                btn.click(delay=random.randint(50, 150))
                                endorsed_count += 1
                                self._human_delay(1, 3)
                    except Exception as inner_e:
                        logger.warning(f"Error endorsing skill {endorsed_count+1}: {inner_e}")
                        continue

                if endorsed_count > 0:
                    logger.info(f"[LIVE] endorse_3_skills: {endorsed_count} skills endorsed on {profile_url}")
                    return {"status": "success", "action": "endorse_3_skills", "count": endorsed_count}
                return {"status": "error", "error": "Could not endorse any skills"}
            except LinkedInActionOutcomeUnknown:
                raise
            except Exception as e:
                return {"status": "error", "error": str(e)}
```

---

## 5. Verification Method

1. **Python Syntax & Compilation**:
   ```bash
   python3 -m py_compile campaigns/backend/services/elein_executor.py campaigns/backend/services/elein_orchestrator.py integrations/backend/services/linkedin_worker.py core/backend/workers/job_processor.py
   ```
   *Expected result*: Exit code 0 (zero errors).

2. **Frontend Type-Check**:
   ```bash
   npx tsc --noEmit
   ```
   *Expected result*: Exit code 0 (zero TypeScript errors).

3. **Executor Test Suite**:
   ```bash
   python3 -m unittest campaigns/backend/tests/test_elein_executor.py
   ```
   *Expected result*: 6+ tests passing with exit code 0.

4. **Specific Invalidation Conditions**:
   - If any handler emits an unmapped branch (e.g. `"Not Positive"`) when the node's edge handle is `"Other"`, edge resolution will fail.
   - If `ai_sentiment` is omitted from `variables`, template replacement `{{ai_sentiment}}` in downstream message nodes will abort via `UninterpolatedTemplateError`.
   - If `try_consume_daily_action` is bypassed, accounts will exceed LinkedIn's daily action threshold and trigger safety challenges.
   - If `action_log` entries fail to record `execution_state_id` or `workspace_id`, dashboard analytics rollup triggers will fail to attribute activity to campaigns.

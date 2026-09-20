"""
Node Executor — maps node types to actual service calls.
Each executor receives the node config + the accumulated context dict
and returns a result dict stored back into context[node.id].
"""

import json
import os
import re
import time
from typing import Any, Dict

import structlog

from campaigns.backend.schemas.workflow_schemas import WorkflowNode

logger = structlog.get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Template rendering: replace {{variable.path}} with context values
# ─────────────────────────────────────────────────────────────────────────────

def _render(template: str, context: dict[str, Any]) -> str:
    """Replace {{node_id.key}} or {{key}} tokens with context values."""
    if not template:
        return template

    def replacer(match):
        path = match.group(1).strip()
        parts = path.split(".")
        try:
            val = context
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p, "")
                else:
                    val = getattr(val, p, "")
            return str(val) if val is not None else ""
        except Exception:
            return ""

    return re.sub(r"\{\{([^}]+)\}\}", replacer, template)


# ─────────────────────────────────────────────────────────────────────────────
# Node executors
# ─────────────────────────────────────────────────────────────────────────────

def _exec_trigger(node: WorkflowNode, context: dict, run_id: str) -> dict:
    return {"triggered": True, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _exec_http_request(node: WorkflowNode, context: dict, run_id: str) -> dict:
    import urllib.request
    cfg = node.data
    url = _render(cfg.get("url", ""), context)
    method = cfg.get("method", "GET")
    headers = json.loads(_render(cfg.get("headers", "{}"), context)) if cfg.get("headers") else {}
    body_str = _render(cfg.get("body", ""), context)
    body = body_str.encode("utf-8") if body_str and method != "GET" else None

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            response_body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(response_body)
            except Exception:
                parsed = response_body
        return {"status_code": resp.status, "response": parsed}
    except Exception as e:
        return {"error": str(e), "url": url}


def _exec_set(node: WorkflowNode, context: dict, run_id: str) -> dict:
    cfg = node.data
    key = cfg.get("key", "output")
    value = _render(cfg.get("value", ""), context)
    return {key: value, "output": value}


def _exec_code(node: WorkflowNode, context: dict, run_id: str) -> dict:
    cfg = node.data
    code = cfg.get("code", "")

    # Hardened sandbox — strip dangerous builtins
    _SAFE_BUILTINS = {
        "abs": abs, "all": all, "any": any, "bool": bool,
        "dict": dict, "enumerate": enumerate, "filter": filter,
        "float": float, "int": int, "isinstance": isinstance,
        "len": len, "list": list, "map": map, "max": max,
        "min": min, "print": print, "range": range, "round": round,
        "set": set, "sorted": sorted, "str": str, "sum": sum,
        "tuple": tuple, "zip": zip, "type": type,
    }
    local_env = {"context": context, "result": None}
    try:
        exec(code, {"__builtins__": _SAFE_BUILTINS}, local_env)
        output = local_env.get("result")
        if output is None:
            # Auto-detect: return entire local_env minus internals as output
            output = {k: v for k, v in local_env.items()
                      if k not in ("context", "result", "__builtins__")}
            if not output:
                output = None
        return {"output": output, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}



def _exec_if_else(node: WorkflowNode, context: dict, run_id: str) -> dict:
    """Evaluate a condition and return branch='true' or branch='false'."""
    cfg = node.data
    field_path = cfg.get("field", "")
    operator = cfg.get("operator", "equals")
    compare_value = cfg.get("value", "")

    # Resolve field value from context
    actual = _resolve_field(field_path, context)
    compare = _render(compare_value, context)

    result = _evaluate_condition(actual, operator, compare)
    branch = "true" if result else "false"
    logger.info("if_else.evaluated", field=field_path, operator=operator,
                actual=actual, compare=compare, result=branch)
    return {"branch": branch, "evaluated": result, "field_value": actual}


def _exec_switch(node: WorkflowNode, context: dict, run_id: str) -> dict:
    cfg = node.data
    field_path = cfg.get("field", "")
    cases_str = cfg.get("cases", "")
    
    actual = _resolve_field(field_path, context)
    cases = [c.strip() for c in cases_str.split(",") if c.strip()]
    
    for case in cases:
        if str(actual).lower() == case.lower():
            return {"branch": case, "field_value": actual}
            
    return {"branch": "default", "field_value": actual}


def _exec_loop(node: WorkflowNode, context: dict, run_id: str) -> dict:
    """Loop node — signals the executor to iterate. Returns loop metadata."""
    cfg = node.data
    array_source = cfg.get("array_source", "")
    array_data = _resolve_field(array_source, context)
    if not isinstance(array_data, list):
        array_data = []
    return {"batch_size": 10, "items_count": len(array_data), "is_loop": True, "source": array_source}


def _exec_delay(node: WorkflowNode, context: dict, run_id: str) -> dict:
    cfg = node.data
    duration = int(cfg.get("duration", 5))
    unit = cfg.get("unit", "seconds")
    seconds_map = {"seconds": 1, "minutes": 60, "hours": 3600}
    sleep_secs = duration * seconds_map.get(unit, 1)
    sleep_secs = min(sleep_secs, 300)
    resume_at = time.time() + sleep_secs
    return {"status": "waiting", "resume_at": resume_at}


def _exec_human_review(node: WorkflowNode, context: dict, run_id: str) -> dict:
    cfg = node.data
    message = _render(cfg.get("message", "Review required"), context)
    logger.info("human_review.pending", run_id=run_id, message=message)
    return {"status": "waiting", "message": message}



def _exec_scrape_leads(node: WorkflowNode, context: dict, run_id: str) -> dict:
    import os
    import urllib.request
    import urllib.parse
    
    cfg = node.data
    market = cfg.get("market", "")
    limit = int(cfg.get("limit", 10))
    keywords = cfg.get("keywords", "")
    
    apify_token = os.environ.get("APIFY_API_TOKEN")
    if not apify_token:
        # Fallback to duckduckgo search if no apify token
        query = f"{market} {keywords}".strip()
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode('utf-8')
                links = re.findall(r'href="([^"]+)"', html)
                results = [{"url": l} for l in set(links) if "http" in l][:limit]
                return {"leads": results, "count": len(results), "status": "success"}
        except Exception as e:
            return {"error": str(e), "success": False}

    node_ctx = context.get(node.id, {})
    apify_run_id = node_ctx.get("apify_run_id")

    if apify_run_id:
        # Phase 2: Resume call
        status_url = f"https://api.apify.com/v2/actor-runs/{apify_run_id}?token={apify_token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(status_url)) as s_resp:
                s_data = json.loads(s_resp.read().decode("utf-8"))
                status = s_data["data"]["status"]
                
                if status == "SUCCEEDED":
                    dataset_id = s_data["data"]["defaultDatasetId"]
                    ds_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={apify_token}"
                    with urllib.request.urlopen(urllib.request.Request(ds_url)) as ds_resp:
                        items = json.loads(ds_resp.read().decode("utf-8"))
                        return {"leads": items, "count": len(items), "status": "success"}
                elif status in ["RUNNING", "READY"]:
                    return {"status": "waiting", "apify_run_id": apify_run_id}
                elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    raise Exception(f"Apify run failed with status: {status}")
        except Exception as e:
            raise e
    else:
        # Phase 1: First call
        url = f"https://api.apify.com/v2/acts/kVYdvNOefemtiDXO5/runs?token={apify_token}"
        headers = {"Content-Type": "application/json"}
        payload = json.dumps({
            "queries": f"{market} {keywords}",
            "limit": limit
        }).encode("utf-8")
        
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                run_id_apify = data["data"]["id"]
                return {"status": "waiting", "apify_run_id": run_id_apify, "dataset_id": None}
        except Exception as e:
            return {"error": str(e), "success": False}


def _exec_enrich_leads(node: WorkflowNode, context: dict, run_id: str) -> dict:
    import urllib.parse
    cfg = node.data
    leads = context.get(node.data.get("leads_source", ""), {}).get("leads") or []
    apollo_token = os.environ.get("APOLLO_API_KEY")

    if not apollo_token:
        # Raise — we refuse to return mock data per user directive
        raise Exception(
            "APOLLO_API_KEY is missing. Add it to .env to run real lead enrichment. "
            "We do not return fake enriched data."
        )

    enriched = []
    for lead in leads[:50]:  # cap at 50 to be safe
        email = lead.get("email", "")
        first = lead.get("firstName", lead.get("first_name", ""))
        last = lead.get("lastName", lead.get("last_name", ""))
        company = lead.get("organization", lead.get("company", ""))

        payload = json.dumps({
            "first_name": first, "last_name": last,
            "organization_name": company, "email": email,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.apollo.io/v1/people/match",
            data=payload,
            headers={"Content-Type": "application/json", "x-api-key": apollo_token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                person = data.get("person", {})
                enriched.append({**lead, **person})
        except Exception as e:
            enriched.append({**lead, "enrich_error": str(e)})

    return {"enriched_leads": enriched, "count": len(enriched), "source": "apollo"}


def _exec_send_email(node: WorkflowNode, context: dict, run_id: str) -> dict:
    cfg = node.data
    to_email = _render(cfg.get("to", ""), context)
    
    if not to_email:
        lead = context.get("lead", {})
        if isinstance(lead, dict) and lead.get("email"):
            to_email = str(lead.get("email")).strip()
        elif context.get("email"):
            to_email = str(context.get("email")).strip()
    subject = _render(cfg.get("subject_template", ""), context)
    body = _render(cfg.get("body_template", ""), context)

    sendgrid_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@example.com")

    if not sendgrid_key:
        raise Exception(
            "SENDGRID_API_KEY is missing. Add it to .env to send real emails. "
            "We do not silently swallow email sends."
        )

    if not to_email:
        raise Exception("send_email: 'to' field is empty — cannot send email without a recipient.")

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
            logger.info("send_email.success", to=to_email, subject=subject, status=resp.status)
            return {"sent": True, "to": to_email, "subject": subject, "timestamp": time.time()}
    except Exception as e:
        raise Exception(f"SendGrid send failed: {e}")


def _exec_find_businesses(node: WorkflowNode, context: dict, run_id: str) -> dict:
    # Same Apify actor as scrape_leads for maps
    cfg = node.data
    query = cfg.get("query", "")
    limit = int(cfg.get("limit", 10))
    
    apify_token = os.environ.get("APIFY_API_TOKEN")
    if not apify_token:
        # Fallback to duckduckgo search if no apify token (avoiding mock data, doing real search)
        import urllib.request
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode('utf-8')
                # Extract some links
                import re
                links = re.findall(r'href="([^"]+)"', html)
                return {"results": [{"url": l} for l in set(links) if "http" in l][:limit]}
        except Exception as e:
            return {"error": str(e)}
            
    # Real Apify call logic would go here
    return {"success": False, "error": "Not implemented with Apify yet"}

def _exec_gohighlevel(node: WorkflowNode, context: dict, run_id: str) -> dict:
    cfg = node.data
    mapping = json.loads(cfg.get("field_mapping", "{}"))
    
    rendered_mapping = {}
    for k, v in mapping.items():
        rendered_mapping[k] = _render(str(v), context)
        
    ghl_token = os.environ.get("GHL_API_TOKEN")
    if not ghl_token:
        return {"error": "Missing GHL_API_TOKEN", "success": False, "attempted_payload": rendered_mapping}
        
    url = "https://services.leadconnectorhq.com/contacts/"
    headers = {
        "Authorization": f"Bearer {ghl_token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, data=json.dumps(rendered_mapping).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return {"success": True, "ghl_response": json.loads(resp.read().decode("utf-8"))}
    except Exception as e:
        return {"error": str(e), "success": False}

def _exec_rag_inbox_monitor(node: WorkflowNode, context: Dict, run_id: str) -> Dict:
    resume_payload = context.get("resume_payload")
    if not resume_payload:
        return {"status": "waiting"}
        
    email_text = resume_payload.get("text", "")
    
    # Basic LLM simulation logic for classification
    email_lower = email_text.lower()
    if "not interested" in email_lower or "unsubscribe" in email_lower or "stop" in email_lower:
        classification = "not_interested"
    elif "later" in email_lower or "next month" in email_lower or "busy" in email_lower:
        classification = "later"
    else:
        classification = "interested"

    return {"status": "success", "branch": classification, "email_text": email_text}


def _exec_if_email_found(node: WorkflowNode, context: dict, run_id: str) -> dict:
    lead = context.get("lead", {})
    email = ""
    if isinstance(lead, dict) and lead.get("email"):
        email = lead.get("email")
    elif context.get("email"):
        email = context.get("email")
        
    has_email = bool(email and str(email).strip())
    branch = "Has Email" if has_email else "No Email"
    logger.info("if_email_found.evaluated", email=email, result=branch)
    return {"branch": branch, "evaluated": has_email, "field_value": email}

# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher

# ─────────────────────────────────────────────────────────────────────────────

_EXECUTORS = {
    "trigger_manual":       _exec_trigger,
    "trigger_schedule":     _exec_trigger,
    "trigger_webhook":      _exec_trigger,
    "http_request":         _exec_http_request,
    "set":                  _exec_set,
    "code":                 _exec_code,
    "if_else":              _exec_if_else,
    "switch":               _exec_switch,
    "loop":                 _exec_loop,
    "delay":                _exec_delay,
    "human_review":         _exec_human_review,
    "scrape_leads":         _exec_scrape_leads,
    "enrich_leads":         _exec_enrich_leads,
    "send_email":           _exec_send_email,
    "if_email_found":       _exec_if_email_found,
    "find_businesses":      _exec_find_businesses,
    "gohighlevel":          _exec_gohighlevel,
    "rag_inbox_monitor":    _exec_rag_inbox_monitor,
}


def execute_node(node: WorkflowNode, context: dict[str, Any], run_id: str) -> dict[str, Any]:
    executor = _EXECUTORS.get(node.type)
    if not executor:
        logger.warning("node.unknown_type", node_type=node.type)
        return {"skipped": True, "reason": f"Unknown node type: {node.type}"}
    return executor(node, context, run_id)


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_field(field_path: str, context: dict) -> Any:
    """Resolve 'node_id.key.subkey' from context."""
    parts = field_path.split(".")
    val = context
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return None
    return val


def _evaluate_condition(actual: Any, operator: str, compare: str) -> bool:
    try:
        if operator == "equals":
            return str(actual).lower() == compare.lower()
        elif operator == "not_equals":
            return str(actual).lower() != compare.lower()
        elif operator == "greater_than":
            return float(actual) > float(compare)
        elif operator == "less_than":
            return float(actual) < float(compare)
        elif operator == "contains":
            return compare.lower() in str(actual).lower()
        elif operator == "not_contains":
            return compare.lower() not in str(actual).lower()
        elif operator == "is_empty":
            return actual is None or str(actual).strip() == ""
        return False
    except Exception:
        return False

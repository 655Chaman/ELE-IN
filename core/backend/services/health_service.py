import json
import os

from core.backend.services.matchmaking_service import get_llm_client

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_FILE = os.path.join(BASE_DIR, "health_status.json")

def _load_health() -> dict:
    if not os.path.exists(HEALTH_FILE):
        return {}
    try:
        with open(HEALTH_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_health(state: dict):
    tmp = HEALTH_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, HEALTH_FILE)

def get_pipeline_health(pipeline_key: str) -> dict:
    """Returns { 'status': 'healthy'|'degraded', 'diagnosis': '...' }"""
    return _load_health().get(pipeline_key, {"status": "healthy", "diagnosis": ""})

def diagnose_pipeline_failure(task_id: str, market: str, action: str, logs: str, row_count: int):
    """
    Called after a pipeline runs. 
    If row_count == 0 or there's an explicit error, it flags as degraded and calls LLM.
    Otherwise, marks as healthy.
    """
    pipeline_key = f"{market}_{action}"
    state = _load_health()
    
    if row_count > 0 and "[RUNNER ERROR]" not in logs and "[INGEST ERROR]" not in logs:
        # Healthy
        state[pipeline_key] = {"status": "healthy", "diagnosis": ""}
        _save_health(state)
        return
        
    # Degraded - Call LLM
    client, model_name = get_llm_client()
    diagnosis = "Pipeline failed or returned 0 leads. AI diagnosis unavailable."
    
    if client:
        prompt = f"""
You are an expert DevOps engineer diagnosing a data scraping/enrichment pipeline failure.
The pipeline '{task_id}' for market '{market}' action '{action}' resulted in {row_count} rows.
Here are the tail logs:
{logs[-1500:]}

Provide a concise, 1-2 sentence human-readable diagnosis of what broke (e.g. 'CSS selector changed', 'Apify actor timed out', 'No leads matched criteria'). 
Output ONLY the text diagnosis.
"""
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=150,
                stream=False
            )
            diagnosis = completion.choices[0].message.content.strip()
        except Exception as e:
            error_str = str(e).lower()
            print(f"Failed to run LLM diagnosis: {e}")
            if "rate limit" in error_str or "429" in error_str:
                diagnosis = "Pipeline failed or returned 0 leads. AI diagnosis unavailable (Rate Limit Exceeded)."
            elif "timeout" in error_str or "read time out" in error_str:
                diagnosis = "Pipeline failed or returned 0 leads. AI diagnosis unavailable (Timeout)."
            elif "connection" in error_str:
                diagnosis = "Pipeline failed or returned 0 leads. AI diagnosis unavailable (Connection Error)."
            else:
                diagnosis = f"Pipeline failed. AI diagnosis error: {str(e)[:100]}"
                
    state[pipeline_key] = {"status": "degraded", "diagnosis": diagnosis}
    _save_health(state)

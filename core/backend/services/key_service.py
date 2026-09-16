import json
import os

import structlog
from dotenv import set_key

logger = structlog.get_logger()

# Storing API keys in a local JSON to survive restarts
KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api_keys.json")
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

def get_current_keys() -> dict[str, str]:
    if not os.path.exists(KEYS_FILE):
        return {}
    try:
        with open(KEYS_FILE) as f:
            return json.load(f)
    except Exception as e:
        logger.error("api_keys_read_error", error=str(e))
        return {}

def update_keys(keys_data: dict[str, str]) -> bool:
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(keys_data, f, indent=2)
            
        # Also sync specific keys directly to the .env file so the scraper subprocesses can read them natively
        if keys_data.get("api_key_mailsso"):
            set_key(ENV_FILE, "MAILSSO_KEY", keys_data["api_key_mailsso"])
        
        if keys_data.get("api_key_apify"):
            set_key(ENV_FILE, "APIFY_TOKEN", keys_data["api_key_apify"])
            
        # Sync LLM Keys based on selected provider
        provider = keys_data.get("llm_provider", "openai")
        llm_key = keys_data.get("api_key_llm") or keys_data.get("api_key_openai", "")
        
        if provider:
            set_key(ENV_FILE, "LLM_PROVIDER", provider)
        if "llm_model" in keys_data:
            set_key(ENV_FILE, "LLM_MODEL", keys_data["llm_model"])

        if llm_key:
            if provider == "nvidia":
                set_key(ENV_FILE, "NVIDIA_API_KEY", llm_key)
            elif provider == "openrouter":
                set_key(ENV_FILE, "OPENROUTER_API_KEY", llm_key)
            elif provider == "anthropic":
                set_key(ENV_FILE, "ANTHROPIC_API_KEY", llm_key)
            elif provider == "gemini":
                set_key(ENV_FILE, "GEMINI_API_KEY", llm_key)
            else:
                set_key(ENV_FILE, "OPENAI_API_KEY", llm_key)
                
        return True
    except Exception as e:
        logger.error("api_keys_write_error", error=str(e))
        return False

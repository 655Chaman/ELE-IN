import json
import os

import structlog
from dotenv import set_key

logger = structlog.get_logger()

# Storing API keys in a local JSON to survive restarts
KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api_keys.json")
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

def get_current_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE) as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    keys = dict(loaded)
        except Exception as e:
            logger.error("api_keys_read_error", error=str(e))

    # Paranoia Layer 1: Environment variable fallback for missing or unconfigured keys
    env_mappings = {
        "api_key_openai": ["OPENAI_API_KEY"],
        "api_key_nvidia": ["NVIDIA_API_KEY"],
        "api_key_anthropic": ["ANTHROPIC_API_KEY"],
        "api_key_gemini": ["GEMINI_API_KEY"],
        "api_key_openrouter": ["OPENROUTER_API_KEY"],
        "api_key_apify": ["APIFY_TOKEN", "APIFY_API_KEY"],
        "api_key_mailsso": ["MAILSSO_KEY", "MAILSSO_API_KEY"],
        "llm_provider": ["LLM_PROVIDER"],
        "llm_model": ["LLM_MODEL"],
    }

    for key_name, env_vars in env_mappings.items():
        if not keys.get(key_name):
            for var in env_vars:
                val = os.getenv(var)
                if val:
                    keys[key_name] = val.strip()
                    break

    # If api_key_llm is missing, resolve it from the active provider's key
    if not keys.get("api_key_llm"):
        provider = (keys.get("llm_provider") or "openai").lower()
        provider_key_map = {
            "openai": "api_key_openai",
            "nvidia": "api_key_nvidia",
            "anthropic": "api_key_anthropic",
            "gemini": "api_key_gemini",
            "openrouter": "api_key_openrouter",
        }
        active_key_attr = provider_key_map.get(provider, "api_key_openai")
        if keys.get(active_key_attr):
            keys["api_key_llm"] = keys[active_key_attr]

    return keys

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

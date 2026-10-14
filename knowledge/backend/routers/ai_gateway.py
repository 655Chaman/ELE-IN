from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List, Tuple
import logging
import re
from datetime import datetime, timezone

from core.backend.api.auth_dep import get_supabase_client, get_current_workspace, get_service_client
from supabase import Client
from core.backend.services.credit_service import check_tier_access, TIER_LIMITS
from knowledge.backend.services.byok_vault import (
    encrypt_byok_key,
    decrypt_byok_key,
    validate_byok_key,
    InvalidKeyFormatError,
    VaultDecryptionError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge/ai", tags=["AI Gateway & BYOK"])

# Catalog of available LLM routing choices
AVAILABLE_AI_MODELS = [
    {
        "id": "Auto-Route (Recommended)",
        "name": "Task-Adaptive Auto-Route",
        "provider": "Ele-in NIM Cluster",
        "description": "Dynamic routing to optimal model per subtask (synthesis, scoring, drafting) for maximum deliverability & throughput.",
        "is_pro": False,
        "cost_in": "$0.10 - $0.35",
        "cost_out": "$0.10 - $0.35",
        "latency": "< 800ms",
        "context_window": "32K",
    },
    {
        "id": "DeepSeek V4 Pro",
        "name": "DeepSeek-R1 Reasoning",
        "provider": "DeepSeek",
        "description": "Deep chain-of-thought mathematical and conversational reasoning for complex objections and personalized ICP angle discovery.",
        "is_pro": True,
        "cost_in": "$0.55",
        "cost_out": "$2.19",
        "latency": "1.2s - 2.5s",
        "context_window": "64K",
    },
    {
        "id": "Nemotron 120B",
        "name": "NVIDIA Nemotron-4 340B",
        "provider": "NVIDIA",
        "description": "High-parameter enterprise sales synthesis, corporate persona alignment, and natural executive rapport.",
        "is_pro": True,
        "cost_in": "$4.20",
        "cost_out": "$4.20",
        "latency": "900ms - 1.8s",
        "context_window": "128K",
    },
    {
        "id": "Llama-3.2 11B",
        "name": "Meta Llama 3.2 11B Vision",
        "provider": "Meta",
        "description": "Ultra-low latency reasoning with vision and profile screenshot multi-modal comprehension.",
        "is_pro": True,
        "cost_in": "$0.16",
        "cost_out": "$0.16",
        "latency": "< 450ms",
        "context_window": "128K",
    },
    {
        "id": "GPT-OS",
        "name": "OpenAI GPT-4o-Mini",
        "provider": "OpenAI",
        "description": "Industry-standard precision for structured JSON output, intent classification, and multi-step workflow logic.",
        "is_pro": True,
        "cost_in": "$0.15",
        "cost_out": "$0.60",
        "latency": "600ms - 1.2s",
        "context_window": "128K",
    },
    {
        "id": "Kimi k3",
        "name": "Moonshot Kimi K3 32K",
        "provider": "Moonshot",
        "description": "Ultra-long context window for digesting extensive corporate whitepapers, 10-K filings, and complex technical collateral.",
        "is_pro": True,
        "cost_in": "$0.30",
        "cost_out": "$0.30",
        "latency": "1.0s - 2.0s",
        "context_window": "32K",
    },
]

SUPPORTED_BYOK_PROVIDERS = ["openai", "anthropic", "deepseek", "groq", "openrouter"]

# Layer 1 Environmental Fallback in-memory map
_FALLBACK_AI_SETTINGS: Dict[str, Dict[str, Any]] = {}


def _get_workspace_tier(supabase: Client, workspace_id: str) -> str:
    """Helper to fetch verified workspace subscription tier."""
    try:
        ws_res = supabase.table("workspaces").select("tier").eq("id", workspace_id).limit(1).execute()
        if ws_res.data and ws_res.data[0].get("tier"):
            t = str(ws_res.data[0]["tier"]).strip().upper()
            if t == "GROWTH":
                return "PRO"
            return t
    except Exception:
        pass
    return "FREE"


class AISettingsUpdateRequest(BaseModel):
    default_model: Optional[str] = None
    byok_provider: Optional[str] = None
    byok_key: Optional[str] = None
    remove_byok: Optional[bool] = False
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class TestKeyRequest(BaseModel):
    provider: str
    api_key: str


@router.get("/settings")
def get_ai_settings(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Retrieve current workspace AI configuration:
    Selected default model, BYOK connection state, token limits, and available models catalog.
    """
    tier = _get_workspace_tier(supabase, workspace_id)
    can_models = check_tier_access(workspace_id, "ai_models")
    can_byok = check_tier_access(workspace_id, "byok")
    can_telemetry = check_tier_access(workspace_id, "ai_telemetry")

    settings_row = None
    try:
        res = supabase.table("workspace_ai_settings").select(
            "default_model, byok_provider, byok_key_last_chars, temperature, max_tokens_budget, updated_at"
        ).eq("workspace_id", workspace_id).limit(1).execute()
        if res.data:
            settings_row = res.data[0]
    except Exception as e:
        logger.debug(f"[AIGateway] workspace_ai_settings query fallback: {e}")
        settings_row = _FALLBACK_AI_SETTINGS.get(workspace_id)

    if not settings_row:
        settings_row = {
            "default_model": "Auto-Route (Recommended)",
            "byok_provider": None,
            "byok_key_last_chars": None,
            "temperature": 0.7,
            "max_tokens_budget": 2000000,
        }

    last_chars = settings_row.get("byok_key_last_chars")
    has_byok = bool(last_chars and settings_row.get("byok_provider"))
    masked_key = f"••••••••••••{last_chars}" if last_chars else None

    return {
        "status": "success",
        "workspace_id": workspace_id,
        "tier": tier,
        "can_choose_ai_models": can_models,
        "can_byok_ai_keys": can_byok,
        "can_view_token_telemetry": can_telemetry,
        "default_model": settings_row.get("default_model", "Auto-Route (Recommended)"),
        "byok_provider": settings_row.get("byok_provider"),
        "byok_key_masked": masked_key,
        "has_byok": has_byok,
        "temperature": settings_row.get("temperature", 0.7),
        "max_tokens_budget": settings_row.get("max_tokens_budget", 2000000),
        "available_models": AVAILABLE_AI_MODELS,
    }


@router.put("/settings")
def update_ai_settings(
    payload: AISettingsUpdateRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Update workspace default AI model, BYOK credentials, and inference parameters.
    Layer 0: Core update.
    Layer 1: Environmental DB failure fallback.
    Layer 2: Human paranoia tier gating and credential safety.
    """
    can_models = check_tier_access(workspace_id, "ai_models")
    can_byok = check_tier_access(workspace_id, "byok")

    # Layer 2: Model choice entitlement check
    if payload.default_model and payload.default_model != "Auto-Route (Recommended)" and not can_models:
        raise HTTPException(
            status_code=403,
            detail="Advanced AI model selection is exclusive to Growth Pro and Enterprise workspaces. Please upgrade to select specialized reasoning engines."
        )

    # Layer 2: BYOK entitlement check
    if payload.byok_key and not can_byok:
        raise HTTPException(
            status_code=403,
            detail="Bring Your Own Key (BYOK) AI gateway integration is exclusive to Growth Pro and Enterprise workspaces. Please upgrade to connect external LLM API keys."
        )

    update_dict: Dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    if payload.default_model is not None:
        valid_model_ids = [m["id"] for m in AVAILABLE_AI_MODELS]
        if payload.default_model not in valid_model_ids:
            raise HTTPException(status_code=400, detail=f"Invalid AI model selected: {payload.default_model}")
        update_dict["default_model"] = payload.default_model

    if payload.temperature is not None:
        update_dict["temperature"] = payload.temperature

    if payload.remove_byok:
        update_dict["byok_provider"] = None
        update_dict["byok_key_ciphertext"] = None
        update_dict["byok_key_last_chars"] = None
    elif payload.byok_key:
        provider = (payload.byok_provider or "openai").lower()
        if provider not in SUPPORTED_BYOK_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}. Supported: {', '.join(SUPPORTED_BYOK_PROVIDERS)}")

        try:
            clean_key = validate_byok_key(provider, payload.byok_key)
            encrypted_key = encrypt_byok_key(clean_key)
        except InvalidKeyFormatError as ike:
            raise HTTPException(status_code=400, detail=str(ike))
        except Exception as err:
            logger.error(f"[AIGateway] Failed to encrypt BYOK key: {err}")
            raise HTTPException(status_code=500, detail="Internal error encrypting BYOK credentials.")

        update_dict["byok_provider"] = provider
        update_dict["byok_key_ciphertext"] = encrypted_key
        update_dict["byok_key_last_chars"] = clean_key[-4:]

    # Layer 1: Attempt upsert into DB; if table missing, fall back to memory
    persisted_ok = False
    try:
        check = supabase.table("workspace_ai_settings").select("workspace_id").eq("workspace_id", workspace_id).execute()
        if check.data:
            supabase.table("workspace_ai_settings").update(update_dict).eq("workspace_id", workspace_id).execute()
        else:
            insert_data = {"workspace_id": workspace_id, **update_dict}
            supabase.table("workspace_ai_settings").insert(insert_data).execute()
        persisted_ok = True
    except Exception as e:
        logger.warning(f"[AIGateway] Failed DB upsert, falling back to memory: {e}")
        current = _FALLBACK_AI_SETTINGS.get(workspace_id, {
            "default_model": "Auto-Route (Recommended)",
            "byok_provider": None,
            "byok_key_last_chars": None,
            "temperature": 0.7,
            "max_tokens_budget": 2000000,
        })
        current.update(update_dict)
        _FALLBACK_AI_SETTINGS[workspace_id] = current

    # Return updated state
    last_chars = update_dict.get("byok_key_last_chars")
    masked_key = f"••••••••••••{last_chars}" if last_chars else None

    return {
        "status": "success",
        "persisted": persisted_ok,
        "default_model": update_dict.get("default_model", payload.default_model or "Auto-Route (Recommended)"),
        "byok_provider": update_dict.get("byok_provider"),
        "byok_key_masked": masked_key,
        "has_byok": bool(masked_key),
    }


def get_decrypted_workspace_byok_key(supabase: Client, workspace_id: str) -> Optional[Tuple[str, str]]:
    """
    Retrieves and decrypts the active BYOK API key for a workspace.
    Returns (provider, decrypted_api_key) or None if no active key exists.
    """
    row = None
    try:
        res = supabase.table("workspace_ai_settings").select(
            "byok_provider, byok_key_ciphertext"
        ).eq("workspace_id", workspace_id).limit(1).execute()
        if res.data:
            row = res.data[0]
    except Exception as e:
        logger.debug(f"[AIGateway] Error fetching workspace_ai_settings for decryption: {e}")
        row = _FALLBACK_AI_SETTINGS.get(workspace_id)

    if not row:
        return None

    provider = row.get("byok_provider")
    ciphertext = row.get("byok_key_ciphertext")
    if not provider or not ciphertext:
        return None

    try:
        decrypted = decrypt_byok_key(ciphertext)
        if decrypted:
            return provider, decrypted
    except Exception as e:
        logger.error(f"[AIGateway] Failed to decrypt BYOK key for workspace {workspace_id}: {e}")
        return None

    return None


@router.post("/test-key")
def test_byok_key(
    payload: TestKeyRequest,
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Validate provider API key format and signature.
    """
    if not check_tier_access(workspace_id, "byok"):
        raise HTTPException(
            status_code=403,
            detail="BYOK validation requires a Growth Pro subscription."
        )

    provider = payload.provider.lower()
    if provider not in SUPPORTED_BYOK_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    try:
        clean_key = validate_byok_key(provider, payload.api_key)
    except InvalidKeyFormatError as ike:
        raise HTTPException(status_code=400, detail=str(ike))

    return {
        "status": "success",
        "valid": True,
        "provider": provider,
        "last_chars": clean_key[-4:],
        "message": f"Successfully validated {provider.capitalize()} API key format."
    }


@router.get("/telemetry")
def get_ai_token_telemetry(
    supabase: Client = Depends(get_supabase_client),
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Aggregates granular AI token telemetry, compute expenditure ($),
    model usage breakdown, and recent generation audit trail.
    """
    can_telemetry = check_tier_access(workspace_id, "ai_telemetry")
    tier = _get_workspace_tier(supabase, workspace_id)

    if not can_telemetry:
        # Layer 2: Return locked state with informative preview benchmarks
        return {
            "status": "success",
            "is_locked": True,
            "tier": tier,
            "total_tokens": 14250,
            "total_cost": 0.048,
            "total_calls": 38,
            "monthly_token_budget": 500000,
            "model_breakdown": [
                {"model": "Auto-Route (Llama-3.2)", "count": 28, "tokens": 9800, "cost": 0.015},
                {"model": "Nemotron-3.5", "count": 10, "tokens": 4450, "cost": 0.033},
            ],
            "recent_generations": [],
            "upgrade_required": True,
            "message": "AI Token Cost Telemetry is locked on the Free tier. Upgrade to Growth Pro to access real-time inference telemetry and cost accounting."
        }

    try:
        res = supabase.table("ai_generations").select(
            "id, model, tokens_used, cost, created_at, prompt, output"
        ).eq("workspace_id", workspace_id).order("created_at", desc=True).limit(200).execute()
        
        rows = res.data or []
    except Exception as e:
        logger.warning(f"[AIGateway] Failed querying ai_generations: {e}")
        rows = []

    total_tokens = sum(int(r.get("tokens_used") or 0) for r in rows)
    total_cost = sum(float(r.get("cost") or 0.0) for r in rows)
    total_calls = len(rows)

    # Calculate model breakdown
    models_dict: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m = r.get("model") or "unknown"
        if m not in models_dict:
            models_dict[m] = {"model": m, "count": 0, "tokens": 0, "cost": 0.0}
        models_dict[m]["count"] += 1
        models_dict[m]["tokens"] += int(r.get("tokens_used") or 0)
        models_dict[m]["cost"] += float(r.get("cost") or 0.0)

    model_breakdown = sorted(
        [
            {
                "model": v["model"],
                "count": v["count"],
                "tokens": v["tokens"],
                "cost": round(v["cost"], 4),
            }
            for v in models_dict.values()
        ],
        key=lambda x: x["tokens"],
        reverse=True
    )

    recent_generations = [
        {
            "id": r.get("id"),
            "model": r.get("model", "unknown"),
            "tokens_used": int(r.get("tokens_used") or 0),
            "cost": round(float(r.get("cost") or 0.0), 5),
            "prompt_preview": (r.get("prompt") or "")[:120],
            "output_preview": (r.get("output") or "")[:120],
            "created_at": r.get("created_at"),
        }
        for r in rows[:15]
    ]

    return {
        "status": "success",
        "is_locked": False,
        "tier": tier,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "total_calls": total_calls,
        "monthly_token_budget": 5000000 if tier == "ENTERPRISE" else 2000000,
        "model_breakdown": model_breakdown,
        "recent_generations": recent_generations,
    }

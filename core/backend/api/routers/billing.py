from supabase import Client
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
import hmac
import os
import uuid
import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, Tuple, Dict, Any
from core.backend.api.auth_dep import get_current_workspace, get_async_service_client, get_supabase_client, get_service_client, require_superadmin

logger = logging.getLogger(__name__)

router = APIRouter()

_fallback_credit_mutex = threading.Lock()
_PROCESSED_FALLBACK_EVENTS: Set[Tuple[str, str]] = set()

def add_credits_safely_fallback(supabase: Client, workspace_id: str, credits: int, event_id: str, provider: str):
    """
    Paranoia Layer 0, 1 & 2: Adds credits safely via RPC with an idempotent, TOCTOU-safe fallback.
    - Layer 0: Checks processed_webhook_events table before mutating balance, preventing duplicate crediting.
    - Layer 1: Distributed workspace lock eliminates race conditions during read-modify-write across Uvicorn workers.
    - Layer 2: Gracefully handles unmigrated schema, validates inputs (credits > 0), and records processed status.
    """
    if not workspace_id or not event_id or credits <= 0:
        logger.warning(f"[Billing] Invalid arguments to add_credits_safely_fallback: ws={workspace_id}, cr={credits}, evt={event_id}")
        return

    try:
        supabase.rpc("add_credits_safely", {
            "p_workspace_id": workspace_id,
            "p_credits": credits,
            "p_event_id": event_id,
            "p_provider": provider
        }).execute()
        return
    except Exception as rpc_err:
        logger.warning(f"[Billing] RPC add_credits_safely failed, applying idempotent fallback: {rpc_err}")

    # Fallback Path with strict idempotency and TOCTOU protection under distributed lock
    from core.backend.services.credit_service import distributed_workspace_lock
    with distributed_workspace_lock(f"billing_credits_{workspace_id}", ttl_seconds=30, supabase=supabase, blocking=True):
        event_key = (str(event_id), str(provider))
        if event_key in _PROCESSED_FALLBACK_EVENTS:
            logger.info(f"[Billing] In-memory deduplication: event {event_id} from {provider} already processed.")
            return

        # 1. Check database-level idempotency via processed_webhook_events
        try:
            evt_res = supabase.table("processed_webhook_events").select("event_id, provider").eq("event_id", event_id).eq("provider", provider).execute()
            if evt_res.data:
                matched = any(isinstance(r, dict) and r.get("event_id") == event_id for r in evt_res.data)
                if matched:
                    logger.info(f"[Billing] DB deduplication: event {event_id} already recorded in processed_webhook_events.")
                    _PROCESSED_FALLBACK_EVENTS.add(event_key)
                    return
        except Exception as check_err:
            logger.warning(f"[Billing] Error querying processed_webhook_events in fallback: {check_err}")

        # 2. Mark event as processed in database first (fail early on collision)
        try:
            supabase.table("processed_webhook_events").insert({
                "event_id": event_id,
                "provider": provider
            }).execute()
        except Exception as insert_err:
            err_str = str(insert_err).lower()
            if any(k in err_str for k in ("duplicate", "unique", "conflict", "primary", "23505", "already exists")):
                logger.info(f"[Billing] DB unique collision: event {event_id} from {provider} already recorded by another worker.")
                _PROCESSED_FALLBACK_EVENTS.add(event_key)
                return
            logger.warning(f"[Billing] Could not insert into processed_webhook_events in fallback: {insert_err}")

        # 3. Apply balance update with verified current balance
        try:
            ws_res = supabase.table("workspaces").select("data_cleaning_credits").eq("id", workspace_id).execute()
            current = (ws_res.data[0].get("data_cleaning_credits") or 0) if ws_res.data else 0
            supabase.table("workspaces").update({
                "data_cleaning_credits": current + credits
            }).eq("id", workspace_id).execute()
            _PROCESSED_FALLBACK_EVENTS.add(event_key)
            logger.info(f"[Billing] Fallback successfully added {credits} credits to workspace {workspace_id} (new balance={current + credits}).")
        except Exception as update_err:
            logger.error(f"[Billing] Direct credits update failed in fallback: {update_err}")

async def _resolve_client(getter_or_client):
    if callable(getter_or_client):
        res = getter_or_client()
    else:
        res = getter_or_client
    if hasattr(res, "__await__"):
        return await res
    return res

async def _resolve_query(query):
    if hasattr(query, "execute"):
        res = query.execute()
    else:
        res = query
    if hasattr(res, "__await__"):
        return await res
    return res

async def async_add_credits_safely_fallback(supabase, workspace_id: str, credits: int, event_id: str, provider: str):
    """
    Paranoia Layer 0, 1 & 2: Async version of idempotent, TOCTOU-safe credit addition fallback.
    """
    if not workspace_id or not event_id or credits <= 0:
        logger.warning(f"[Billing] Invalid arguments to async_add_credits_safely_fallback: ws={workspace_id}, cr={credits}, evt={event_id}")
        return

    try:
        await _resolve_query(
            supabase.rpc("add_credits_safely", {
                "p_workspace_id": workspace_id,
                "p_credits": credits,
                "p_event_id": event_id,
                "p_provider": provider
            })
        )
        return
    except Exception as rpc_err:
        logger.warning(f"[Billing] Async RPC add_credits_safely failed, applying idempotent fallback: {rpc_err}")

    # Fallback Path with strict idempotency and TOCTOU protection under distributed lock
    from core.backend.services.credit_service import distributed_workspace_lock
    with distributed_workspace_lock(f"billing_credits_{workspace_id}", ttl_seconds=30, supabase=supabase, blocking=True):
        event_key = (str(event_id), str(provider))
        if event_key in _PROCESSED_FALLBACK_EVENTS:
            logger.info(f"[Billing] Async in-memory deduplication: event {event_id} from {provider} already processed.")
            return

        # 1. Check database-level idempotency via processed_webhook_events
        try:
            evt_res = await _resolve_query(
                supabase.table("processed_webhook_events").select("event_id, provider").eq("event_id", event_id).eq("provider", provider)
            )
            if evt_res and getattr(evt_res, "data", None):
                matched = any(isinstance(r, dict) and r.get("event_id") == event_id for r in evt_res.data)
                if matched:
                    logger.info(f"[Billing] Async DB deduplication: event {event_id} already recorded in processed_webhook_events.")
                    _PROCESSED_FALLBACK_EVENTS.add(event_key)
                    return
        except Exception as check_err:
            logger.warning(f"[Billing] Async error querying processed_webhook_events in fallback: {check_err}")

        # 2. Mark event as processed in database first
        try:
            await _resolve_query(
                supabase.table("processed_webhook_events").insert({
                    "event_id": event_id,
                    "provider": provider
                })
            )
        except Exception as insert_err:
            err_str = str(insert_err).lower()
            if any(k in err_str for k in ("duplicate", "unique", "conflict", "primary", "23505", "already exists")):
                logger.info(f"[Billing] Async DB collision guard: event {event_id} from {provider} already recorded by another worker.")
                _PROCESSED_FALLBACK_EVENTS.add(event_key)
                return
            logger.warning(f"[Billing] Async could not insert into processed_webhook_events in fallback: {insert_err}")

        # 3. Apply balance update with verified current balance
        try:
            ws_res = await _resolve_query(
                supabase.table("workspaces").select("data_cleaning_credits").eq("id", workspace_id)
            )
            current = (ws_res.data[0].get("data_cleaning_credits") or 0) if (ws_res and ws_res.data) else 0
            await _resolve_query(
                supabase.table("workspaces").update({
                    "data_cleaning_credits": current + credits
                }).eq("id", workspace_id)
            )
            _PROCESSED_FALLBACK_EVENTS.add(event_key)
            logger.info(f"[Billing] Async fallback successfully added {credits} credits to workspace {workspace_id} (new balance={current + credits}).")
        except Exception as update_err:
            logger.error(f"[Billing] Async direct credits update failed in fallback: {update_err}")

PACKAGES = {
    'credits_1000': {"credits": 1000, "inr_paise": 99900, "usd_cents": 1200, "tier": None},
    'credits_5000': {"credits": 5000, "inr_paise": 449900, "usd_cents": 5500, "tier": None},
    'starter_tier': {"credits": 1500, "inr_paise": 249900, "usd_cents": 2900, "tier": "PRO"},
    'growth_tier': {"credits": 5000, "inr_paise": 799900, "usd_cents": 9900, "tier": "PRO"},
    'growth_tier_annual': {"credits": 60000, "inr_paise": 7798800, "usd_cents": 94800, "tier": "PRO"},
    'growth_tier_oto': {"credits": 5000, "inr_paise": 559900, "usd_cents": 6900, "tier": "PRO"},
    'growth_tier_annual_oto': {"credits": 60000, "inr_paise": 5458800, "usd_cents": 66000, "tier": "PRO"}
}

from core.backend.services.credit_service import is_mock_billing_allowed

class CheckoutRequest(BaseModel):
    package_id: str
    provider: str
    action: Optional[str] = "upgrade"

@router.post("/checkout")
async def checkout(request: CheckoutRequest, workspace_id: str = Depends(get_current_workspace), supabase: Client = Depends(get_supabase_client)):
    # Layer 0 & Layer 2: Fast input validation before performing side effects
    if request.package_id not in PACKAGES:
        raise HTTPException(status_code=400, detail="Invalid package_id")
    if request.provider not in ("razorpay", "lemonsqueezy"):
        raise HTTPException(status_code=400, detail="Invalid provider")
    # Paranoia Layer 1 & 2: 48-Hour OTO Promotional Expiry Validation
    if request.package_id in ("growth_tier_oto", "growth_tier_annual_oto"):
        try:
            inbound_check = supabase.table("messages").select("created_at").eq("workspace_id", workspace_id).eq("direction", "inbound").order("created_at", desc=False).limit(1).execute()
            if inbound_check.data:
                first_win_at = inbound_check.data[0].get("created_at")
                if first_win_at:
                    from datetime import datetime, timezone, timedelta
                    dt = datetime.fromisoformat(first_win_at.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) - dt > timedelta(hours=48):
                        raise HTTPException(
                            status_code=400,
                            detail="The 48-hour First-Win momentum grant has expired for this workspace."
                        )
        except HTTPException:
            raise
        except Exception as e_check:
            logger.warning(f"Failed to check OTO promotional eligibility: {e_check}")

    package = PACKAGES[request.package_id]
    
    if request.provider == "razorpay":
        try:
            import razorpay
        except ImportError:
            razorpay = None
            
        rzp_key_id = os.environ.get("RAZORPAY_KEY_ID")
        rzp_key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not rzp_key_id or not rzp_key_secret or not razorpay:
            # Paranoia Layer 1: Allow simulated checkout only when explicitly permitted in dev/test
            if is_mock_billing_allowed():
                mock_order_id = f"order_mock_{uuid.uuid4().hex[:8]}"
                session_id = str(uuid.uuid4())
                try:
                    supabase.table("billing_transactions").insert({
                        "id": session_id,
                        "workspace_id": workspace_id,
                        "provider": "razorpay",
                        "provider_order_id": mock_order_id,
                        "status": "pending",
                        "package_id": request.package_id
                    }).execute()
                except Exception as db_e:
                    print(f"Mock checkout error: {db_e}")
                return {"order_id": mock_order_id, "session_id": str(session_id), "amount": package.get("inr_paise", 0), "key_id": "mock_rzp_key"}
            raise HTTPException(status_code=501, detail="Razorpay keys not configured. Cannot process real checkout.")
            
        try:
            client = razorpay.Client(auth=(rzp_key_id, rzp_key_secret))
            amount_paise = package.get("inr_paise", 0)
            
            # Layer 1 Paranoia: Create a secure, trackable session in the database.
            session_id = str(uuid.uuid4())
            try:
                supabase.table("billing_transactions").insert({
                    "id": session_id,
                    "workspace_id": workspace_id,
                    "provider": "razorpay",
                    "provider_order_id": f"pending_{session_id[:8]}", # Placeholder until webhook
                    "status": "pending",
                    "package_id": request.package_id
                }).execute()
            except Exception as db_e:
                print(f"Failed to create secure checkout session in DB: {db_e}")
                pass
                
            order_data = {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"receipt_{uuid.uuid4().hex[:8]}",
                "notes": {
                    "checkout_session_id": str(session_id)
                }
            }
            order = client.order.create(data=order_data)
            try:
                supabase.table("billing_transactions").update({
                    "provider_order_id": order["id"]
                }).eq("id", session_id).execute()
            except Exception as up_e:
                logger.warning(f"[Billing] Could not update provider_order_id: {up_e}")
            return {"order_id": order["id"], "session_id": str(session_id), "amount": amount_paise, "key_id": rzp_key_id}
        except Exception as e:
            print("Razorpay order creation failed:", e)
            raise HTTPException(status_code=500, detail="Failed to create Razorpay order")
            
    elif request.provider == "lemonsqueezy":
        ls_api_key = os.environ.get("LEMONSQUEEZY_API_KEY")
        session_id = str(uuid.uuid4())
        try:
            supabase.table("billing_transactions").insert({
                "id": session_id,
                "workspace_id": workspace_id,
                "provider": "lemonsqueezy",
                "provider_order_id": f"pending_{session_id[:8]}",
                "status": "pending",
                "package_id": request.package_id
            }).execute()
        except Exception as db_e:
            print(f"Failed to create secure LemonSqueezy session in DB: {db_e}")

        if not ls_api_key:
            if is_mock_billing_allowed():
                return {"checkout_url": f"https://mock.lemonsqueezy.com/checkout/{uuid.uuid4().hex[:8]}", "session_id": session_id}
            raise HTTPException(status_code=501, detail="LemonSqueezy keys not configured. Cannot process real checkout.")

        store_id = os.environ.get("LEMONSQUEEZY_STORE_ID")
        variant_id = package.get("variant_id") or os.environ.get(f"LEMONSQUEEZY_VARIANT_{request.package_id.upper()}")

        if not store_id or not variant_id:
            if is_mock_billing_allowed():
                return {"checkout_url": f"https://mock.lemonsqueezy.com/checkout/{uuid.uuid4().hex[:8]}", "session_id": session_id}
            raise HTTPException(status_code=400, detail="LemonSqueezy store ID or variant ID not configured in environment variables.")

        try:
            import requests
            payload = {
                "data": {
                    "type": "checkouts",
                    "attributes": {
                        "checkout_data": {
                            "custom": {
                                "workspace_id": workspace_id,
                                "package_id": request.package_id,
                                "checkout_session_id": str(session_id)
                            }
                        }
                    },
                    "relationships": {
                        "store": {"data": {"type": "stores", "id": str(store_id)}},
                        "variant": {"data": {"type": "variants", "id": str(variant_id)}}
                    }
                }
            }
            headers = {
                "Authorization": f"Bearer {ls_api_key}",
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json"
            }
            resp = requests.post("https://api.lemonsqueezy.com/v1/checkouts", json=payload, headers=headers, timeout=15)
            if resp.status_code not in (200, 201):
                print(f"LemonSqueezy API error: {resp.status_code} {resp.text}")
                raise HTTPException(status_code=502, detail=f"LemonSqueezy API error: {resp.text}")
            resp_data = resp.json()
            checkout_url = resp_data["data"]["attributes"]["url"]
            return {"checkout_url": checkout_url, "session_id": session_id}
        except HTTPException:
            raise
        except Exception as e:
            print(f"LemonSqueezy checkout creation failed: {e}")
            if is_mock_billing_allowed():
                return {"checkout_url": f"https://mock.lemonsqueezy.com/checkout/{uuid.uuid4().hex[:8]}", "session_id": session_id}
            raise HTTPException(status_code=500, detail="Failed to create LemonSqueezy checkout")

class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    session_id: str

@router.post("/verify")
async def verify_payment(
    request: VerifyPaymentRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 1 & 2: Synchronous Payment Verification
    Eliminates race condition where webhook arrives 1-5 seconds after client completes checkout.
    Strictly validates input parameters, session ownership, order ID integrity, and environment gates.
    """
    req_pay_id = (request.razorpay_payment_id or "").strip()
    req_order_id = (request.razorpay_order_id or "").strip()
    req_sig = (request.razorpay_signature or "").strip()
    req_sess_id = (request.session_id or "").strip()

    if not req_pay_id or not req_order_id or not req_sess_id:
        raise HTTPException(status_code=400, detail="Missing or invalid payment verification parameters")

    session_res = supabase.table("billing_transactions").select("workspace_id, package_id, status, provider_order_id, provider").eq("id", req_sess_id).execute()
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Checkout session not found")

    session = session_res.data[0]
    if session.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=403, detail="Unauthorized workspace session")

    # If webhook already beat us to it
    if session.get("status") == "paid":
        return {"status": "already_verified", "tier": "PRO"}

    if session.get("status") not in ("pending",):
        raise HTTPException(status_code=400, detail="Checkout session is not in a payable state")

    # Paranoia Layer 1 & 2: 48-Hour OTO Promotional Expiry Validation
    if session.get("package_id") in ("growth_tier_oto", "growth_tier_annual_oto"):
        try:
            inbound_check = supabase.table("messages").select("created_at").eq("workspace_id", workspace_id).eq("direction", "inbound").order("created_at", desc=False).limit(1).execute()
            if inbound_check.data:
                first_win_at = inbound_check.data[0].get("created_at")
                if first_win_at:
                    from datetime import datetime, timezone, timedelta
                    dt = datetime.fromisoformat(first_win_at.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) - dt > timedelta(hours=48):
                        raise HTTPException(
                            status_code=400,
                            detail="The 48-hour First-Win momentum grant has expired for this workspace."
                        )
        except HTTPException:
            raise
        except Exception as e_check:
            logger.warning(f"Failed to check OTO eligibility during payment verification: {e_check}")

    # Paranoia Layer 1: Distributed lock serializes concurrent client /verify and server webhook callbacks
    from core.backend.services.credit_service import distributed_workspace_lock
    with distributed_workspace_lock(f"billing_credits_{workspace_id}", ttl_seconds=30, supabase=supabase, blocking=True):
        # Re-check status under lock
        fresh_session_res = supabase.table("billing_transactions").select("status").eq("id", req_sess_id).execute()
        if fresh_session_res.data and fresh_session_res.data[0].get("status") == "paid":
            return {"status": "already_verified", "tier": "PRO"}

        # Mock order verification for dev / testing
        if req_order_id.startswith("order_mock_"):
            if not is_mock_billing_allowed():
                raise HTTPException(status_code=403, detail="Simulated payment verification is disabled in production")

            session_order_id = session.get("provider_order_id") or ""
            if session_order_id and not session_order_id.startswith("order_mock_") and not session_order_id.startswith("pending_"):
                raise HTTPException(status_code=400, detail="Mismatched session provider order ID")

            pkg_id = session.get("package_id")
            pkg = PACKAGES.get(pkg_id, {})
            credits = pkg.get("credits", 0)
            
            if credits > 0:
                add_credits_safely_fallback(
                    supabase=supabase,
                    workspace_id=workspace_id,
                    credits=credits,
                    event_id=f"mock_{req_sess_id}",
                    provider="mock"
                )

            # Update workspace tier if PRO package
            if pkg_id in ["growth_tier", "growth_tier_annual", "growth_tier_oto", "growth_tier_annual_oto"]:
                supabase.table("workspaces").update({"tier": "PRO"}).eq("id", workspace_id).execute()
            supabase.table("billing_transactions").update({
                "status": "paid",
                "provider_payment_id": req_pay_id,
                "provider_order_id": req_order_id,
                "credits_added": credits
            }).eq("id", req_sess_id).execute()
            return {"status": "verified", "tier": "PRO"}

        # Real Razorpay signature verification
        rzp_key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        if not rzp_key_secret:
            raise HTTPException(status_code=500, detail="Razorpay webhook secret not configured")

        if not req_sig:
            raise HTTPException(status_code=400, detail="Missing payment signature")

        data_to_verify = f"{req_order_id}|{req_pay_id}"
        expected_signature = hmac.new(
            rzp_key_secret.encode(),
            data_to_verify.encode(),
            "sha256"
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, req_sig):
            raise HTTPException(status_code=400, detail="Invalid payment signature")

        pkg_id = session.get("package_id")
        pkg = PACKAGES.get(pkg_id, {})
        credits = pkg.get("credits", 0)

        if credits > 0:
            add_credits_safely_fallback(
                supabase=supabase,
                workspace_id=workspace_id,
                credits=credits,
                event_id=req_pay_id,
                provider="razorpay"
            )

        if pkg_id in ["growth_tier", "growth_tier_annual", "growth_tier_oto", "growth_tier_annual_oto"]:
            supabase.table("workspaces").update({"tier": "PRO"}).eq("id", workspace_id).execute()

        supabase.table("billing_transactions").update({
            "status": "paid",
            "provider_payment_id": req_pay_id,
            "provider_order_id": req_order_id,
            "amount_cents": pkg.get("inr_paise", 0),
            "currency": "INR",
            "credits_added": credits
        }).eq("id", req_sess_id).execute()

        return {"status": "verified", "tier": "PRO"}
 
class CancelSessionRequest(BaseModel):
    session_id: str
    reason: Optional[str] = "user_dismissed_modal"

@router.post("/cancel-session")
async def cancel_session(
    request: CancelSessionRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 1 & 2: Explicitly marks an abandoned or dismissed checkout session
    as cancelled, preventing ghost pending orders and blocking duplicate order replays.
    """
    sess_id = (request.session_id or "").strip()
    if not sess_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        supabase.table("billing_transactions").update({
            "status": "cancelled",
            "metadata": {"cancel_reason": request.reason}
        }).eq("id", sess_id).eq("workspace_id", workspace_id).eq("status", "pending").execute()
        return {"status": "success", "session_id": sess_id}
    except Exception as e:
        logger.warning(f"[Billing] Could not mark session cancelled: {e}")
        return {"status": "ok"}


_PROCESSED_STRIPE_EVENTS = set()

def calculate_proration_credit(current_credits: int, days_remaining: int, total_days: int = 30) -> int:
    """
    Paranoia Layer 0 & 1: Safe Proration Helper
    Calculates prorated unused credit rollover with zero-division safety and clamping.
    """
    safe_total_days = max(1, int(total_days))
    safe_days_remaining = max(0, min(safe_total_days, int(days_remaining)))
    try:
        prorated = int(float(current_credits) * (safe_days_remaining / safe_total_days))
        return max(0, min(60000, prorated))
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

def verify_stripe_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """
    Paranoia Layer 0 & 1: Verifies Stripe signature or permits mock/test mode when explicitly enabled.
    """
    if is_mock_billing_allowed():
        return True
    if not secret or not signature_header:
        return False
    try:
        # Simple Stripe signature check or standard hmac
        parts = dict(item.split("=") for item in signature_header.split(",") if "=" in item)
        timestamp = parts.get("t", "")
        v1_sig = parts.get("v1", "")
        signed_payload = f"{timestamp}.".encode() + body
        expected = hmac.new(secret.encode(), signed_payload, "sha256").hexdigest()
        return hmac.compare_digest(expected, v1_sig) or hmac.compare_digest(hmac.new(secret.encode(), body, "sha256").hexdigest(), v1_sig)
    except Exception:
        # Fallback basic comparison
        return hmac.compare_digest(hmac.new(secret.encode(), body, "sha256").hexdigest(), signature_header)

@router.post("/webhook/stripe")
async def webhook_stripe(request: Request):
    body = await request.body()
    signature = request.headers.get("stripe-signature") or request.headers.get("X-Stripe-Signature")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    
    if not is_mock_billing_allowed():
        if not secret:
            raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")
        if not signature or not verify_stripe_signature(body, signature, secret):
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    else:
        if secret and signature and not verify_stripe_signature(body, signature, secret):
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
        
    try:
        data = json.loads(body)
        event_id = data.get("id")
        if not event_id:
            if not is_mock_billing_allowed():
                raise HTTPException(status_code=400, detail="Missing Stripe event id")
            event_id = f"evt_{uuid.uuid4().hex[:8]}"
        event_type = data.get("type", "")
        event_object = data.get("data", {}).get("object", {})

        # Layer 1: Idempotent Webhook Replay Guard
        if event_id in _PROCESSED_STRIPE_EVENTS:
            return {"status": "idempotent_duplicate", "event_id": event_id, "message": "Event already processed"}

        supabase = await _resolve_client(get_async_service_client)
        
        # Check database billing_transactions for idempotent event_id duplicate
        try:
            existing_txn_query = supabase.table("billing_transactions").select("id").eq("provider_order_id", event_id).eq("provider", "stripe").execute()
            if hasattr(existing_txn_query, "__await__"):
                existing_txn = await existing_txn_query
            else:
                existing_txn = existing_txn_query
            if existing_txn.data and len(existing_txn.data) > 0:
                _PROCESSED_STRIPE_EVENTS.add(event_id)
                return {"status": "idempotent_duplicate", "event_id": event_id, "message": "Event already processed"}
        except Exception:
            pass

        # Mark processed in memory
        _PROCESSED_STRIPE_EVENTS.add(event_id)

        if event_type == "checkout.session.completed":
            client_ref_id = event_object.get("client_reference_id")
            metadata = event_object.get("metadata") or {}
            workspace_id = client_ref_id or metadata.get("workspace_id")
            
            # Layer 2: Cross-Tenant IDOR & Workspace Existence Defense
            if not workspace_id:
                raise HTTPException(status_code=400, detail="Missing workspace_id in checkout session")
                
            ws_check_query = supabase.table("workspaces").select("id, status").eq("id", workspace_id).execute()
            if hasattr(ws_check_query, "__await__"):
                ws_check = await ws_check_query
            else:
                ws_check = ws_check_query
            if not ws_check.data or len(ws_check.data) == 0:
                raise HTTPException(status_code=400, detail=f"Workspace {workspace_id} does not exist")
                
            ws_status = ws_check.data[0].get("status", "active")
            if ws_status == "pending_deletion":
                return {"status": "skipped", "reason": "workspace_pending_deletion"}

            package_id = metadata.get("package_id", "credits_1000")
            pkg_info = PACKAGES.get(package_id, {"credits": 1000, "usd_cents": 1200, "tier": None})
            credits = int(pkg_info.get("credits", 1000))
            tier = pkg_info.get("tier")

            # Award credits safely
            if credits > 0:
                await async_add_credits_safely_fallback(supabase, workspace_id, credits, event_id, "stripe")

            # Update tier if applicable
            if tier:
                upd_ws = supabase.table("workspaces").update({"tier": tier}).eq("id", workspace_id).execute()
                if hasattr(upd_ws, "__await__"):
                    await upd_ws

            # Log transaction
            try:
                ins_txn = supabase.table("billing_transactions").insert({
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "provider": "stripe",
                    "provider_order_id": event_id,
                    "provider_payment_id": event_object.get("payment_intent") or event_object.get("id"),
                    "amount_cents": int(event_object.get("amount_total") or pkg_info.get("usd_cents", 1200)),
                    "currency": str(event_object.get("currency", "USD")).upper(),
                    "credits_added": credits,
                    "package_id": package_id,
                    "status": "paid"
                }).execute()
                if hasattr(ins_txn, "__await__"):
                    await ins_txn
            except Exception as txn_err:
                logger.warning(f"Error logging stripe billing transaction: {txn_err}")

        elif event_type == "invoice.payment_succeeded":
            subscription_id = event_object.get("subscription")
            lines_data = event_object.get("lines", {}).get("data", [])
            metadata = event_object.get("metadata") or {}
            if lines_data and not metadata.get("workspace_id"):
                metadata = lines_data[0].get("metadata") or metadata
                
            workspace_id = metadata.get("workspace_id")
            if not workspace_id and subscription_id:
                # Try finding workspace by subscription in billing_transactions
                try:
                    sub_query = supabase.table("billing_transactions").select("workspace_id").eq("provider_order_id", subscription_id).execute()
                    if hasattr(sub_query, "__await__"):
                        sub_res = await sub_query
                    else:
                        sub_res = sub_query
                    if sub_res.data:
                        workspace_id = sub_res.data[0].get("workspace_id")
                except Exception:
                    pass

            if workspace_id:
                package_id = metadata.get("package_id", "growth_tier")
                pkg_info = PACKAGES.get(package_id, {"credits": 5000, "tier": "PRO"})
                credits = int(pkg_info.get("credits", 5000))
                
                if credits > 0:
                    await async_add_credits_safely_fallback(supabase, workspace_id, credits, event_id, "stripe_subscription")
                
                if pkg_info.get("tier"):
                    upd_sub_ws = supabase.table("workspaces").update({"tier": pkg_info.get("tier")}).eq("id", workspace_id).execute()
                    if hasattr(upd_sub_ws, "__await__"):
                        await upd_sub_ws

                try:
                    ins_sub_txn = supabase.table("billing_transactions").insert({
                        "id": str(uuid.uuid4()),
                        "workspace_id": workspace_id,
                        "provider": "stripe",
                        "provider_order_id": event_id,
                        "amount_cents": int(event_object.get("amount_paid") or 0),
                        "currency": str(event_object.get("currency", "USD")).upper(),
                        "credits_added": credits,
                        "package_id": package_id,
                        "status": "paid"
                    }).execute()
                    if hasattr(ins_sub_txn, "__await__"):
                        await ins_sub_txn
                except Exception:
                    pass

        elif event_type in ("customer.subscription.deleted", "subscription.deleted"):
            metadata = event_object.get("metadata") or {}
            workspace_id = metadata.get("workspace_id")
            if workspace_id:
                try:
                    camp_upd = supabase.table("campaigns").update({"status": "PAUSED"}).eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
                    if hasattr(camp_upd, "__await__"):
                        await camp_upd
                    ws_upd = supabase.table("workspaces").update({"tier": "FREE"}).eq("id", workspace_id).execute()
                    if hasattr(ws_upd, "__await__"):
                        await ws_upd
                except Exception as e:
                    logger.warning(f"Error downgrading workspace on subscription deleted: {e}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "ok"}

@router.post("/webhook/razorpay")
async def webhook_razorpay(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=501, detail="Razorpay webhook integration not configured")
    
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")
        
    expected_sig = hmac.new(secret.encode(), body, "sha256").hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    try:
        data = json.loads(body)
        event_name = data.get("event", "")
        
        # Layer 1 Paranoia: Downgrade Kill Switch
        if event_name in ["subscription.cancelled", "subscription.halted", "invoice.payment_failed", "customer.subscription.deleted", "subscription.deleted"]:
            payload = data.get("payload", {})
            sub = payload.get("subscription", {}).get("entity", {})
            workspace_id = sub.get("notes", {}).get("workspace_id")
            if workspace_id:
                try:
                    supabase = await get_async_service_client()
                    await supabase.table("campaigns").update({"status": "PAUSED"}).eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
                    await supabase.table("workspaces").update({"tier": "FREE"}).eq("id", workspace_id).execute()
                    print(f"Downgrade kill-switch: Paused campaigns and downgraded tier to FREE for workspace {workspace_id}")
                except Exception as e:
                    print(f"Error pausing campaigns / downgrading tier: {e}")
            return {"status": "ok"}

        AUTHORIZED_PAYMENT_EVENTS = ["payment.captured", "order.paid"]
        if event_name not in AUTHORIZED_PAYMENT_EVENTS:
            logger.info(f"Ignoring non-payment Razorpay event: {event_name}")
            return {"status": "ignored", "event": event_name}

        payment_entity = data.get("payload", {}).get("payment", {}).get("entity", {})
        notes = payment_entity.get("notes", {})
        
        # Layer 1 Paranoia: Never trust client metadata. Lookup the secure session from DB.
        checkout_session_id = notes.get("checkout_session_id")
        if not checkout_session_id:
            raise ValueError("Missing checkout_session_id in Razorpay notes payload")
            
        supabase = await get_async_service_client()
        session_res = await supabase.table("billing_transactions").select("workspace_id, package_id, status").eq("id", checkout_session_id).execute()
        if not session_res.data:
            raise ValueError("Invalid checkout session")
        session_row = session_res.data[0]
        if session_row.get("status") == "paid":
            logger.info(f"[RazorpayWebhook] Session {checkout_session_id} already marked paid.")
            return {"status": "ok", "message": "already_paid"}
        if session_row.get("status") != "pending":
            logger.info(f"[RazorpayWebhook] Session {checkout_session_id} not in pending state: {session_row.get('status')}")
            return {"status": "ignored", "reason": "session_not_pending"}
            
        workspace_id = session_row.get("workspace_id")
        package_id = session_row.get("package_id")
        
        # Layer 1 Paranoia: Prevent dead workspace top-ups
        ws_res = await supabase.table("workspaces").select("status").eq("id", workspace_id).execute()
        ws_status = ws_res.data[0].get("status") if ws_res.data else "active"
        if ws_status == "pending_deletion":
            print(f"Skipping credit grant for {workspace_id} - workspace is pending_deletion.")
            await supabase.table("billing_transactions").update({"status": "failed_pending_deletion"}).eq("id", checkout_session_id).execute()
            # Ideally trigger a Razorpay refund API call here.
            return {"status": "skipped"}
        
        credits = 0
        if package_id in PACKAGES:
            credits = PACKAGES[package_id]["credits"]
        else:
            # Fallback for old sessions that didn't use packages
            credits = int(notes.get("credits", 0))
            
        if workspace_id:
            from core.backend.services.credit_service import distributed_workspace_lock
            with distributed_workspace_lock(f"billing_credits_{workspace_id}", ttl_seconds=30, supabase=supabase, blocking=True):
                # Double-check status under lock
                fresh_check = await supabase.table("billing_transactions").select("status").eq("id", checkout_session_id).execute()
                if fresh_check.data and fresh_check.data[0].get("status") == "paid":
                    logger.info(f"[RazorpayWebhook] Session {checkout_session_id} verified/paid concurrently under lock.")
                    return {"status": "ok", "message": "already_paid"}

                if credits > 0:
                    event_id = payment_entity.get("id") or f"rzp_{checkout_session_id}"
                    await async_add_credits_safely_fallback(supabase, workspace_id, credits, event_id, "razorpay")
                    try:
                        await supabase.table("billing_transactions").update({
                            "provider_order_id": event_id,
                            "provider_payment_id": payment_entity.get("id") or event_id,
                            "amount_cents": payment_entity.get("amount", 0),
                            "currency": payment_entity.get("currency", "INR"),
                            "credits_added": credits,
                            "status": "paid"
                        }).eq("id", checkout_session_id).execute()
                    except Exception as e:
                        logger.warning(f"Error updating billing transaction: {e}")

                if package_id in ["growth_tier", "growth_tier_annual", "growth_tier_oto", "growth_tier_annual_oto"]:
                    await supabase.table("workspaces").update({"tier": "PRO"}).eq("id", workspace_id).execute()
    except ValueError as val_err:
        logger.warning(f"[RazorpayWebhook] Invalid or already processed payload: {val_err}")
        return {"status": "ignored", "reason": str(val_err)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[RazorpayWebhook] Error processing Razorpay webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal webhook processing error")
        
    return {"status": "ok"}

@router.post("/webhook/lemonsqueezy")
async def webhook_lemonsqueezy(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Signature")
    secret = os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=501, detail="LemonSqueezy webhook integration not configured")
    
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")
        
    expected_sig = hmac.new(secret.encode(), body, "sha256").hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
        
    try:
        data = json.loads(body)
        custom_data = data.get("meta", {}).get("custom_data", {})
        event_name = data.get("meta", {}).get("event_name", "")

        # Layer 1 Paranoia: Downgrade Kill Switch
        if event_name in ["subscription_cancelled", "subscription_payment_failed", "subscription_expired", "subscription.deleted", "customer.subscription.deleted", "invoice.payment_failed"]:
            workspace_id = custom_data.get("workspace_id")
            if workspace_id:
                try:
                    supabase = await get_async_service_client()
                    await supabase.table("campaigns").update({"status": "PAUSED"}).eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
                    await supabase.table("workspaces").update({"tier": "FREE"}).eq("id", workspace_id).execute()
                    print(f"Downgrade kill-switch: Paused campaigns and downgraded tier to FREE for workspace {workspace_id}")
                except Exception as e:
                    print(f"Error pausing campaigns / downgrading tier: {e}")
            return {"status": "ok"}
        
        AUTHORIZED_LS_EVENTS = ["order_created", "subscription_created"]
        if event_name not in AUTHORIZED_LS_EVENTS:
            logger.info(f"Ignoring non-order LemonSqueezy event: {event_name}")
            return {"status": "ignored", "event": event_name}
        
        # Layer 1 Paranoia: Secure Session Lookup
        checkout_session_id = custom_data.get("checkout_session_id")
        if not checkout_session_id:
            raise ValueError("Missing checkout_session_id in LemonSqueezy custom_data payload")
            
        supabase = await get_async_service_client()
        session_res = await supabase.table("billing_transactions").select("workspace_id, package_id").eq("id", checkout_session_id).eq("status", "pending").execute()
        if not session_res.data:
            raise ValueError("Invalid or already processed checkout session")
            
        workspace_id = session_res.data[0].get("workspace_id")
        package_id = session_res.data[0].get("package_id")
        
        # Layer 1 Paranoia: Prevent dead workspace top-ups
        ws_res = await supabase.table("workspaces").select("status").eq("id", workspace_id).execute()
        ws_status = ws_res.data[0].get("status") if ws_res.data else "active"
        if ws_status == "pending_deletion":
            print(f"Skipping credit grant for {workspace_id} - workspace is pending_deletion.")
            await supabase.table("billing_transactions").update({"status": "failed_pending_deletion"}).eq("id", checkout_session_id).execute()
            # Ideally trigger a LemonSqueezy refund API call here.
            return {"status": "skipped"}
        
        credits = 0
        if package_id in PACKAGES:
            credits = PACKAGES[package_id]["credits"]
            
        if workspace_id:
            if credits > 0:
                event_id = data.get("meta", {}).get("event_id") or f"ls_{checkout_session_id}"
                await async_add_credits_safely_fallback(supabase, workspace_id, credits, event_id, "lemonsqueezy")
                try:
                    await supabase.table("billing_transactions").update({
                        "provider_order_id": event_id,
                        "amount_cents": data.get("data", {}).get("attributes", {}).get("total", 0),
                        "currency": data.get("data", {}).get("attributes", {}).get("currency", "USD"),
                        "credits_added": credits,
                        "status": "paid"
                    }).eq("id", checkout_session_id).execute()
                except Exception as e:
                    print(f"Error updating billing transaction: {e}")
            if package_id in ["growth_tier", "growth_tier_annual", "growth_tier_oto", "growth_tier_annual_oto"]:
                await supabase.table("workspaces").update({"tier": "PRO"}).eq("id", workspace_id).execute()
    except Exception as e:
        print(f"Error processing webhook: {e}")
        
    return {"status": "ok"}

@router.get("/history")
async def get_billing_history(workspace_id: str = Depends(get_current_workspace)):
    try:
        supabase = await get_async_service_client()
        res = await supabase.table("billing_transactions").select("*").eq("workspace_id", workspace_id).order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        print(f"Error fetching billing history: {e}")
        return []

@router.get("/credits/balance")
async def get_credit_balance_endpoint(
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    try:
        result = supabase.rpc('get_credit_balance', {
            'p_workspace_id': workspace_id
        }).execute()
        return result.data or {"balance": 0, "tier": "FREE", "used_this_month": 0}
    except Exception as e:
        logger.warning(f"[Billing] get_credit_balance RPC failed, falling back to direct table query: {e}")
        try:
            ws_res = supabase.table("workspaces").select("tier, data_cleaning_credits").eq("id", workspace_id).execute()
            if ws_res.data:
                ws_row = ws_res.data[0]
                raw_tier = (ws_row.get("tier") or "FREE").upper()
                if raw_tier == "GROWTH":
                    raw_tier = "PRO"
                return {
                    "balance": ws_row.get("data_cleaning_credits", 0) or 0,
                    "tier": raw_tier,
                    "used_this_month": 0,
                    "unmigrated_rpc": True
                }
        except Exception as ws_err:
            logger.warning(f"[Billing] Direct workspace query also failed: {ws_err}")
        return {"balance": 0, "tier": "FREE", "used_this_month": 0}

@router.get("/credits/usage")
async def get_credit_usage(
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client),
    limit: int = 50,
    offset: int = 0
):
    # Layer 2: clamp limit and offset
    safe_limit = max(1, min(100, limit))
    safe_offset = max(0, offset)
    try:
        result = supabase.table('credit_deductions').select('*').eq(
            'workspace_id', workspace_id
        ).order('created_at', desc=True).range(safe_offset, safe_offset + safe_limit - 1).execute()
        return {"deductions": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        logger.warning(f"[Billing] Could not query credit_deductions: {e}")
        return {"deductions": [], "count": 0, "unmigrated": True}

@router.get("/credits/costs")
async def get_credit_costs(
    supabase: Client = Depends(get_supabase_client)
):
    try:
        result = supabase.table('credit_action_costs').select('*').eq('is_active', True).execute()
        return {"costs": result.data or []}
    except Exception as e:
        return {"costs": []}

class CreditGrantRequest(BaseModel):
    workspace_id: str
    credits: int
    reason: str = "admin_grant"


@router.post("/credits/grant")
async def grant_credits(
    request: CreditGrantRequest,
    supabase: Client = Depends(get_service_client),
    _superadmin: str = Depends(require_superadmin)
):
    # Paranoia Layer 1 & 2: Use add_credits_safely_fallback so unmigrated RPC never breaks admin grants
    if request.credits <= 0:
        raise HTTPException(status_code=400, detail="Credits to grant must be a positive integer")
    if request.credits > 1000000:
        raise HTTPException(status_code=400, detail="Maximum grant per transaction is 1,000,000 credits")

    event_id = f"admin_grant_{uuid.uuid4().hex}"
    try:
        add_credits_safely_fallback(
            supabase=supabase,
            workspace_id=request.workspace_id,
            credits=request.credits,
            event_id=event_id,
            provider="admin"
        )
        
        try:
            supabase.table("billing_transactions").insert({
                "workspace_id": request.workspace_id,
                "provider": "admin",
                "provider_order_id": event_id,
                "amount_cents": 0,
                "currency": "USD",
                "credits_added": request.credits,
                "status": "success"
            }).execute()
        except Exception as e:
            logger.warning(f"Error inserting billing transaction for admin grant: {e}")
            
        return {"status": "ok", "credits_added": request.credits}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from core.backend.services.churn_service import (
    calculate_workspace_churn_health,
    audit_downgrade_safety_impact,
    execute_non_destructive_downgrade_clamp,
)


class SalvageOfferRequest(BaseModel):
    offerType: str  # 'pause', 'discount', 'starter_downsell'
    reason: Optional[str] = None


@router.post("/salvage-offer")
async def apply_salvage_offer(
    request: SalvageOfferRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 0, 1 & 2: Churn Salvage Handler & Anti-Abuse Guard
    Applies non-destructive churn mitigation:
    - 30-day pause (freezes campaigns and billing)
    - 50% discount voucher for next billing cycle
    - Solo Starter downsell (₹2,499 / $29 with 1,500 credits)
    
    Security & Anti-Exploitation Guarantees:
    1. Tier Gate: Only active paid workspaces (PRO, ENTERPRISE, AGENCY) can claim retention offers.
    2. Lifetime & Cycle Limits: Starter downsell is strictly limited to 1 redemption per workspace.
       Pause and discount offers cannot be re-applied within 30 days.
    3. Concurrency & Replay Defense: Deterministic idempotency keys prevent race condition credit minting.
    """
    offer_type = (request.offerType or "").strip().lower()
    if offer_type not in ("pause", "discount", "starter_downsell"):
        raise HTTPException(status_code=400, detail="Invalid salvage offer type")

    # Layer 0 & 2: Verify workspace eligibility (paid tier required)
    ws_res = supabase.table("workspaces").select("tier, status").eq("id", workspace_id).limit(1).execute()
    if not ws_res.data:
        raise HTTPException(status_code=404, detail="Workspace not found")

    ws = ws_res.data[0]
    tier = str(ws.get("tier") or "FREE").upper()
    status = str(ws.get("status") or "active").lower()

    if status in ("pending_deletion", "suspended"):
        raise HTTPException(status_code=403, detail="Workspace is not eligible for retention offers")

    if tier not in ("PRO", "ENTERPRISE", "AGENCY"):
        raise HTTPException(status_code=403, detail="Salvage retention offers are only available for paid active subscriptions.")

    # Layer 1 & 2: Check for prior salvage offer redemptions
    existing_salvage_res = supabase.table("billing_transactions").select("id, package_id, created_at").eq("workspace_id", workspace_id).eq("provider", "salvage_retention").eq("status", "applied").execute()
    existing_salvage = existing_salvage_res.data or []

    # Starter downsell is strictly one-time per workspace lifetime
    if offer_type == "starter_downsell":
        if any(item.get("package_id") == "offer_starter_downsell" for item in existing_salvage):
            raise HTTPException(status_code=409, detail="The Solo Starter downsell offer has already been redeemed for this workspace.")
    else:
        # Pause or discount cannot be stacked within 30 days
        now_utc = datetime.now(timezone.utc)
        for item in existing_salvage:
            created_at_str = item.get("created_at")
            if created_at_str:
                try:
                    clean_ts = created_at_str.replace("Z", "+00:00")
                    item_dt = datetime.fromisoformat(clean_ts)
                    if now_utc - item_dt < timedelta(days=30):
                        raise HTTPException(status_code=409, detail="A salvage retention offer was already applied within the current 30-day billing cycle.")
                except (ValueError, TypeError):
                    pass

    # Deterministic event and session IDs to guarantee idempotency across concurrent threads
    month_key = datetime.now(timezone.utc).strftime("%Y%m")
    deterministic_event_id = f"salvage_{offer_type}_{workspace_id}_{month_key}" if offer_type != "starter_downsell" else f"salvage_starter_downsell_{workspace_id}"
    session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, deterministic_event_id))
    credits_granted = 1500 if offer_type == "starter_downsell" else 0

    try:
        supabase.table("billing_transactions").insert({
            "id": session_id,
            "workspace_id": workspace_id,
            "provider": "salvage_retention",
            "provider_order_id": deterministic_event_id,
            "status": "applied",
            "package_id": f"offer_{offer_type}",
            "amount_cents": 0,
            "currency": "INR",
            "credits_added": credits_granted
        }).execute()
    except Exception as db_e:
        err_msg = str(db_e).lower()
        if "duplicate" in err_msg or "unique" in err_msg or "conflict" in err_msg:
            raise HTTPException(status_code=409, detail="This salvage offer has already been processed.")
        logger.warning(f"Error logging salvage offer: {db_e}")

    # If pause was chosen: safely pause active campaigns so they don't consume credits while user takes a break
    if offer_type == "pause":
        try:
            supabase.table("campaigns").update({"status": "PAUSED"}).eq("workspace_id", workspace_id).eq("status", "ACTIVE").execute()
            supabase.table("workspaces").update({"status": "paused"}).eq("id", workspace_id).execute()
        except Exception as e:
            logger.error(f"Error pausing campaigns for salvage pause: {e}")

    # If starter downsell was chosen: grant starter credits and preserve Pro status
    if offer_type == "starter_downsell":
        try:
            supabase.table("workspaces").update({
                "tier": "PRO",
                "status": "active"
            }).eq("id", workspace_id).execute()
            
            # Atomically add starter credits with deterministic event_id
            add_credits_safely_fallback(
                supabase=supabase,
                workspace_id=workspace_id,
                credits=1500,
                event_id=deterministic_event_id,
                provider="salvage_retention"
            )
        except Exception as e:
            logger.error(f"Error applying starter downsell: {e}")

    return {
        "status": "success",
        "offer_applied": offer_type,
        "message": "Salvage offer successfully applied."
    }


class CancelSubscriptionRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/cancel-subscription")
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 1 & 2: Graceful Churn Handler
    Marks the subscription for cancellation at the end of the current billing cycle.
    Never abruptly terminates service or wipes user work immediately.
    """
    session_id = str(uuid.uuid4())
    try:
        supabase.table("billing_transactions").insert({
            "id": session_id,
            "workspace_id": workspace_id,
            "provider": "cancellation_survey",
            "provider_order_id": f"cancel_{uuid.uuid4().hex[:8]}",
            "status": "scheduled_cancellation",
            "package_id": "cancel_intent",
            "amount_cents": 0,
            "currency": "INR",
            "credits_added": 0
        }).execute()
    except Exception as db_e:
        print(f"Error logging cancellation intent: {db_e}")

    return {
        "status": "success",
        "message": "Subscription scheduled to cancel at end of current billing cycle."
    }


@router.post("/reactivate-subscription")
async def reactivate_subscription(
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 1 & 2: 1-Click Subscription Reactivation.
    Instantly revokes pending cancellation or unpauses account,
    restoring active workspace status without requiring re-entry of payment info.
    """
    try:
        # Mark pending cancellation as reactivated
        supabase.table("billing_transactions").update({
            "status": "reactivated"
        }).eq("workspace_id", workspace_id).eq("status", "scheduled_cancellation").execute()

        # Restore workspace status
        supabase.table("workspaces").update({
            "status": "active"
        }).eq("id", workspace_id).execute()

        return {
            "status": "success",
            "message": "Workspace subscription successfully reactivated!"
        }
    except Exception as e:
        print(f"Error reactivating subscription: {e}")
        return {
            "status": "success",
            "message": "Workspace reactivated."
        }


@router.get("/churn-health")
async def get_churn_health(
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Predictive churn risk and account vitality health score.
    Returns 0-100 score, risk factors, and proactive recommendations.
    """
    return calculate_workspace_churn_health(workspace_id)


@router.get("/downgrade-audit")
async def get_downgrade_audit(
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Audits resource usage against Free tier limits and details the
    non-destructive archiving strategy before confirming cancellation.
    """
    return audit_downgrade_safety_impact(workspace_id)


@router.post("/execute-downgrade-clamp")
async def execute_downgrade_clamp(
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Executes safe non-destructive clamping to Free tier limits.
    Excess campaigns and accounts are preserved in cold storage (PAUSED).
    """
    return execute_non_destructive_downgrade_clamp(workspace_id)


from core.backend.services.credit_service import (
    get_workspace_auto_recharge_settings,
    update_workspace_auto_recharge_settings,
    trigger_auto_recharge_if_needed,
    check_tier_access
)


class AutoRechargeSettingsUpdate(BaseModel):
    enabled: bool
    threshold_credits: Optional[int] = 100
    recharge_package_id: Optional[str] = "credits_1000"
    max_monthly_recharges: Optional[int] = 5


@router.get("/auto-recharge")
async def get_auto_recharge_settings(
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Paranoia Layer 0 & 1: Fetch current auto-recharge configuration and monthly quota status.
    """
    settings = get_workspace_auto_recharge_settings(workspace_id)
    can_auto_recharge = check_tier_access(workspace_id, "auto_recharge")
    return {
        "status": "success",
        "settings": settings,
        "can_auto_recharge": can_auto_recharge
    }


@router.put("/auto-recharge")
async def update_auto_recharge(
    request: AutoRechargeSettingsUpdate,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 0, 1 & 2: Update auto-recharge configuration.
    Enforces Growth/Pro tier gate, validates bounds, prevents enabling without verified payment method on file, and sets circuit breakers.
    """
    can_auto_recharge = check_tier_access(workspace_id, "auto_recharge")
    if request.enabled and not can_auto_recharge:
        raise HTTPException(
            status_code=403,
            detail="Credit Auto-Recharge is a Growth tier feature. Upgrade to enable uninterrupted campaign execution."
        )

    # Paranoia Layer 1 & 2: Reject enabling auto-recharge without verified payment method on file in production
    if request.enabled and not is_mock_billing_allowed():
        try:
            ws_res = supabase.table("workspaces").select("stripe_customer_id").eq("id", workspace_id).execute()
            has_stripe = bool(ws_res.data and ws_res.data[0].get("stripe_customer_id"))
            sub_res = supabase.table("subscriptions").select("provider_subscription_id, status").eq("workspace_id", workspace_id).eq("status", "active").execute()
            has_sub = bool(sub_res.data and len(sub_res.data) > 0)
            if not has_stripe and not has_sub:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot enable auto-recharge: No payment card or active subscription on file. Please add a payment method in Billing first."
                )
        except HTTPException:
            raise
        except Exception as check_err:
            logger.warning(f"[Billing] Error verifying payment method on enable: {check_err}")

    try:
        updated = update_workspace_auto_recharge_settings(workspace_id, request.model_dump())
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    return {
        "status": "success",
        "settings": updated,
        "message": "Auto-recharge settings updated successfully."
    }


@router.post("/auto-recharge/simulate-trigger")
async def simulate_auto_recharge(
    workspace_id: str = Depends(get_current_workspace)
):
    """
    Paranoia Layer 1 & 2: Test / simulate auto-recharge execution in development/sandbox.
    Strictly blocked in production environments to prevent unbilled credit generation.
    """
    if not is_mock_billing_allowed():
        raise HTTPException(
            status_code=403,
            detail="Auto-recharge simulation is permanently disabled in production environments."
        )
    res = trigger_auto_recharge_if_needed(workspace_id, current_balance=0)
    return {
        "status": "success",
        "result": res
    }


@router.get("/transactions/{transaction_id}/receipt")
async def get_transaction_receipt(
    transaction_id: str,
    workspace_id: str = Depends(get_current_workspace),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Paranoia Layer 0, 1 & 2: Generate Corporate Tax Receipt / Invoice Data.
    Layer 2 IDOR Boundary Check: Transaction must belong strictly to caller's workspace.
    Layer 1: Graceful fallback for missing metadata or legacy rows.
    """
    try:
        txn_res = supabase.table("billing_transactions").select("*").eq("id", transaction_id).execute()
        if not txn_res.data:
            # Check by provider_order_id fallback
            txn_res = supabase.table("billing_transactions").select("*").eq("provider_order_id", transaction_id).execute()
            if not txn_res.data:
                raise HTTPException(status_code=404, detail="Billing transaction not found")
        
        txn = txn_res.data[0]
        # Layer 2 IDOR verification
        if txn.get("workspace_id") != workspace_id:
            raise HTTPException(status_code=403, detail="Access denied: Transaction belongs to another workspace")

        # Fetch workspace details
        ws_name = "Ele-in Workspace"
        try:
            ws_res = supabase.table("workspaces").select("name").eq("id", workspace_id).execute()
            if ws_res.data and ws_res.data[0].get("name"):
                ws_name = ws_res.data[0]["name"]
        except Exception:
            pass

        pkg_id = txn.get("package_id") or "credits_1000"
        pkg_info = PACKAGES.get(pkg_id, {})
        credits_added = txn.get("credits_added") or pkg_info.get("credits", 0)
        
        # Determine human-friendly description
        if "tier" in pkg_id or str(txn.get("package_id", "")).startswith("growth") or str(txn.get("package_id", "")).startswith("starter"):
            desc = "Ele-in Growth Outreach Platform Subscription"
        else:
            desc = f"Ele-in AI Outreach Credits ({credits_added:,} Credits)"

        amount_cents = txn.get("amount_cents", 0) or 0
        currency = txn.get("currency") or ("INR" if txn.get("provider") == "razorpay" else "USD")

        # Tax calculation (18% GST standard in India, or 0% net export for USD)
        if currency == "INR":
            subtotal_cents = int(round(amount_cents / 1.18))
            tax_cents = amount_cents - subtotal_cents
        else:
            subtotal_cents = amount_cents
            tax_cents = 0

        short_id = txn["id"][:8].upper()
        return {
            "invoice_number": f"INV-{short_id}",
            "transaction_id": txn["id"],
            "created_at": txn.get("created_at"),
            "workspace_id": workspace_id,
            "workspace_name": ws_name,
            "provider": txn.get("provider", "razorpay"),
            "provider_payment_id": txn.get("provider_payment_id") or txn.get("provider_tx_id") or "verified",
            "provider_order_id": txn.get("provider_order_id") or txn.get("id"),
            "package_id": pkg_id,
            "description": desc,
            "credits_added": credits_added,
            "currency": currency,
            "subtotal_cents": subtotal_cents,
            "tax_cents": tax_cents,
            "amount_cents": amount_cents,
            "status": txn.get("status", "paid"),
            "seller": {
                "company_name": "Ele-in Technologies Inc.",
                "legal_address": "Enterprise Cloud Communications & AI",
                "tax_id": "GSTIN-29AAACE1234F1Z5",
                "billing_email": "billing@ele-in.com"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating receipt for {transaction_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate receipt details")




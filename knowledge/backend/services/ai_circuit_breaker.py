"""
AI Upstream Provider Circuit Breaker — Paranoia Layer 1 & 2
===========================================================
Finite State Machine Circuit Breaker for AI LLM and Embedding Providers
(NVIDIA, DeepSeek, OpenAI, Anthropic, Groq).

Prevents thread starvation, socket exhaustion, and request latency spikes
during third-party API outages or degrading health.

States:
- CLOSED: Provider is healthy; all requests route normally.
- OPEN: Provider has failed 5 consecutive requests; calls fail fast or route to fallback.
- HALF_OPEN: Cooldown has elapsed; 1 trial probe tests if the provider has recovered.
"""

import time
import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

STATE_CLOSED = "CLOSED"
STATE_OPEN = "OPEN"
STATE_HALF_OPEN = "HALF_OPEN"

_breaker_lock = threading.RLock()
_CIRCUIT_STATES: Dict[str, Dict[str, Any]] = {}

DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RECOVERY_TIMEOUT_SECONDS = 30.0


def _get_provider_state_locked(provider: str) -> Dict[str, Any]:
    prov = str(provider or "default").lower().strip()
    if prov not in _CIRCUIT_STATES:
        _CIRCUIT_STATES[prov] = {
            "state": STATE_CLOSED,
            "failure_count": 0,
            "last_failure_time": 0.0,
            "last_state_change": time.time(),
            "trial_in_flight": False,
        }
    return _CIRCUIT_STATES[prov]


def is_provider_available(provider: str, recovery_timeout: float = DEFAULT_RECOVERY_TIMEOUT_SECONDS) -> bool:
    """
    Returns True if the provider is eligible to handle requests.
    Transitions OPEN -> HALF_OPEN when the recovery timeout has elapsed.
    """
    now = time.time()
    with _breaker_lock:
        state_data = _get_provider_state_locked(provider)
        current_state = state_data["state"]

        if current_state == STATE_CLOSED:
            return True

        if current_state == STATE_OPEN:
            if (now - state_data["last_failure_time"]) >= recovery_timeout:
                logger.info(f"[AICircuitBreaker] Provider '{provider}' cooldown elapsed ({recovery_timeout}s). Transitioning OPEN -> HALF_OPEN.")
                state_data["state"] = STATE_HALF_OPEN
                state_data["trial_in_flight"] = True
                state_data["last_state_change"] = now
                return True
            return False

        if current_state == STATE_HALF_OPEN:
            # Only allow one probe at a time in HALF_OPEN
            if not state_data.get("trial_in_flight", False):
                state_data["trial_in_flight"] = True
                return True
            return False

    return True


def record_provider_success(provider: str) -> None:
    """Records a successful call, resetting the circuit breaker to CLOSED."""
    with _breaker_lock:
        state_data = _get_provider_state_locked(provider)
        if state_data["state"] != STATE_CLOSED:
            logger.info(f"[AICircuitBreaker] Provider '{provider}' probe succeeded. Circuit breaker RESET to CLOSED.")
        state_data["state"] = STATE_CLOSED
        state_data["failure_count"] = 0
        state_data["trial_in_flight"] = False


def record_provider_failure(
    provider: str,
    error: Optional[Exception] = None,
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
) -> None:
    """
    Records a failure. If failure_count exceeds failure_threshold, trips to OPEN.
    """
    now = time.time()
    with _breaker_lock:
        state_data = _get_provider_state_locked(provider)
        state_data["last_failure_time"] = now
        state_data["trial_in_flight"] = False

        if state_data["state"] == STATE_HALF_OPEN:
            logger.warning(f"[AICircuitBreaker] Provider '{provider}' trial probe failed: {error}. Tripping back to OPEN.")
            state_data["state"] = STATE_OPEN
            state_data["last_state_change"] = now
            return

        state_data["failure_count"] += 1
        if state_data["failure_count"] >= failure_threshold and state_data["state"] == STATE_CLOSED:
            logger.error(
                f"[AICircuitBreaker] Provider '{provider}' reached {state_data['failure_count']} consecutive failures. "
                f"Tripping circuit breaker to OPEN (cooldown active)."
            )
            state_data["state"] = STATE_OPEN
            state_data["last_state_change"] = now


def get_circuit_breaker_status() -> Dict[str, Dict[str, Any]]:
    """Returns telemetry of all tracked AI provider circuit breakers."""
    with _breaker_lock:
        return {k: dict(v) for k, v in _CIRCUIT_STATES.items()}


def reset_circuit_breaker_state() -> None:
    """Hermetic reset helper for test suites."""
    with _breaker_lock:
        _CIRCUIT_STATES.clear()

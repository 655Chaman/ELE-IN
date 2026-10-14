import time
import random
import logging
import threading
from typing import Callable, Optional, Any

logger = logging.getLogger(__name__)

class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    pass

class CircuitBreaker:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == self.CLOSED:
                return True
            elif self.state == self.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    logger.info(f"[CircuitBreaker] {self.name}: transitioning from OPEN to HALF_OPEN")
                    return True
                return False
            elif self.state == self.HALF_OPEN:
                return True
            return True

    def record_success(self):
        with self._lock:
            if self.state != self.CLOSED:
                logger.info(f"[CircuitBreaker] {self.name}: transitioning from {self.state} to CLOSED")
            self.state = self.CLOSED
            self.failure_count = 0

    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == self.HALF_OPEN or self.failure_count >= self.failure_threshold:
                if self.state != self.OPEN:
                    logger.warning(f"[CircuitBreaker] {self.name}: transitioning to OPEN (failures: {self.failure_count})")
                self.state = self.OPEN

    def reset(self):
        with self._lock:
            self.state = self.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0.0

    def get_status(self) -> dict:
        """Returns observable snapshot of the circuit breaker state."""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state,
                "failure_count": self.failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_time": self.last_failure_time,
                "can_execute": self.can_execute()
            }

_REGISTRY = {}
_REGISTRY_LOCK = threading.Lock()

def get_circuit_breaker(name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> CircuitBreaker:
    with _REGISTRY_LOCK:
        if name not in _REGISTRY:
            _REGISTRY[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
        return _REGISTRY[name]

def reset_all_circuit_breakers():
    with _REGISTRY_LOCK:
        for cb in _REGISTRY.values():
            cb.reset()
        _REGISTRY.clear()

def execute_with_resilience(
    name: str,
    request_fn: Callable[[], Any],
    max_retries: int = 3,
    base_backoff: float = 0.5,
    retryable_status_codes: tuple = (429, 500, 502, 503, 504),
    circuit_breaker: Optional[CircuitBreaker] = None
) -> Any:
    cb = circuit_breaker or get_circuit_breaker(name)
    if not cb.can_execute():
        raise CircuitBreakerOpenException(f"Circuit breaker '{name}' is OPEN")

    last_exception = None
    last_response = None

    for attempt in range(max_retries + 1):
        try:
            response = request_fn()
            last_response = response
            
            status_code = getattr(response, "status_code", None)
            if status_code is not None:
                if 200 <= status_code < 300:
                    cb.record_success()
                    return response
                elif status_code in retryable_status_codes:
                    if attempt < max_retries:
                        delay = base_backoff * (2 ** attempt) + random.uniform(0.05, 0.2)
                        logger.warning(f"[Resilience] {name}: received retryable status {status_code}, attempt {attempt+1}/{max_retries}, retrying in {delay:.2f}s")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"[Resilience] {name}: exhausted retries on status {status_code}")
                        cb.record_failure()
                        return response
                else:
                    return response
            else:
                cb.record_success()
                return response

        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_backoff * (2 ** attempt) + random.uniform(0.05, 0.2)
                logger.warning(f"[Resilience] {name}: caught exception {e}, attempt {attempt+1}/{max_retries}, retrying in {delay:.2f}s")
                time.sleep(delay)
                continue
            else:
                logger.error(f"[Resilience] {name}: exhausted retries due to exception {e}")
                cb.record_failure()
                raise e

    if last_exception:
        raise last_exception
    return last_response

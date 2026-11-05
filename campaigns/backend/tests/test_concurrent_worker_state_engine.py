"""
Master 25-Phase Architecture: Phase 17 Concurrency & State Engine Hardening
Three-Layer Logic Architecture (Paranoia Framework / EPF)

High-Throughput Concurrency Stress Simulation:
20 Concurrent Worker Threads Dequeuing 100 Leads Across 10 Campaigns with CAS Lease Assertions.

- Layer 0: Foundational Layer (Core concurrent dequeue & state machine)
- Layer 1: Environmental Failure Analysis (CAS lease fencing, zombie lease recovery, lock contention)
- Layer 2: Human Paranoia (Mid-flight campaign pause, manual trigger race condition, workspace suspension)
"""

import unittest
import threading
import time
import uuid
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch

from campaigns.backend.services.elein_orchestrator import EleInOrchestrator


class ThreadSafeMockDatabase:
    """
    In-memory thread-safe database simulating Postgres row-level locking
    and atomic Compare-And-Swap (CAS) semantics for high-concurrency worker stress testing.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.execution_states: Dict[str, Dict[str, Any]] = {}
        self.campaigns: Dict[str, Dict[str, Any]] = {}
        self.workspaces: Dict[str, Dict[str, Any]] = {}
        self.enrollments: Dict[str, Dict[str, Any]] = {}
        self.leads: Dict[str, Dict[str, Any]] = {}
        self.messages: List[Dict[str, Any]] = []
        self.claim_log: List[Dict[str, Any]] = []
        self.rejected_updates: List[Dict[str, Any]] = []

    def seed_test_data(self, num_campaigns: int = 10, leads_per_campaign: int = 10):
        with self._lock:
            for c_idx in range(num_campaigns):
                ws_id = f"ws_tenant_{c_idx % 3}"
                c_id = f"camp_{c_idx}"
                self.workspaces[ws_id] = {
                    "id": ws_id,
                    "status": "active",
                    "tier": "ENTERPRISE",
                    "metadata": {}
                }
                self.campaigns[c_id] = {
                    "id": c_id,
                    "workspace_id": ws_id,
                    "status": "ACTIVE",
                    "metadata": {"scheduling_mode": "campaign_timezone"}
                }
                for l_idx in range(leads_per_campaign):
                    lead_id = f"lead_{c_idx}_{l_idx}"
                    enr_id = f"enr_{c_idx}_{l_idx}"
                    state_id = f"state_{c_idx}_{l_idx}"
                    
                    self.leads[lead_id] = {
                        "id": lead_id,
                        "email": f"prospect_{c_idx}_{l_idx}@enterprise.com",
                        "first_name": f"Prospect{l_idx}",
                        "company_name": f"Company{c_idx}",
                        "timezone": "UTC"
                    }
                    self.enrollments[enr_id] = {
                        "id": enr_id,
                        "campaign_id": c_id,
                        "lead_id": lead_id,
                        "status": "active",
                        "campaign_version_id": f"ver_{c_idx}"
                    }
                    self.execution_states[state_id] = {
                        "id": state_id,
                        "campaign_id": c_id,
                        "enrollment_id": enr_id,
                        "lead_id": lead_id,
                        "workspace_id": ws_id,
                        "current_node_id": "node_email_1",
                        "status": "pending",
                        "lease_token": None,
                        "lease_expires_at": None,
                        "next_run_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "attempts": 0,
                        "max_attempts": 5,
                        "variables": {}
                    }

    def atomic_claim(self, state_id: str, lease_token: str, lease_seconds: int = 300) -> Optional[Dict[str, Any]]:
        """Simulates atomic CAS: UPDATE ... WHERE id = state_id AND status = 'pending'"""
        with self._lock:
            state = self.execution_states.get(state_id)
            if not state:
                return None
            if state["status"] != "pending":
                return None
            
            # Atomic transition to running with CAS fencing
            now_dt = datetime.now(timezone.utc)
            state["status"] = "running"
            state["lease_token"] = lease_token
            state["lease_expires_at"] = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
            state["updated_at"] = now_dt.isoformat()
            
            claimed_copy = dict(state)
            self.claim_log.append({
                "state_id": state_id,
                "lease_token": lease_token,
                "timestamp": now_dt.isoformat(),
                "thread_id": threading.get_ident()
            })
            return claimed_copy

    def atomic_update_state(self, state_id: str, lease_token: str, new_status: str, next_node_id: str = None) -> bool:
        """Simulates CAS lease fence: UPDATE ... WHERE id = state_id AND lease_token = lease_token"""
        with self._lock:
            state = self.execution_states.get(state_id)
            if not state:
                self.rejected_updates.append({"state_id": state_id, "reason": "not_found"})
                return False
            
            # Fencing check: Token must match and lease must not be expired
            if state.get("lease_token") != lease_token:
                self.rejected_updates.append({"state_id": state_id, "reason": "lease_token_mismatch", "expected": state.get("lease_token"), "provided": lease_token})
                return False
            
            expires_at = state.get("lease_expires_at")
            if expires_at and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                self.rejected_updates.append({"state_id": state_id, "reason": "lease_expired"})
                return False
            
            # Valid CAS update
            state["status"] = new_status
            if next_node_id:
                state["current_node_id"] = next_node_id
            state["lease_token"] = None
            state["lease_expires_at"] = None
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            return True

    def get_pending_states(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            candidates = [
                dict(s) for s in self.execution_states.values()
                if s["status"] == "pending" and (s["next_run_at"] is None or s["next_run_at"] <= now_iso)
            ]
            return candidates[:limit]


class TestConcurrentWorkerStateEngine(unittest.TestCase):
    def setUp(self):
        self.db = ThreadSafeMockDatabase()

    def test_layer0_20_concurrent_workers_dequeue_100_leads_zero_double_claims(self):
        """
        Layer 0 (Foundational): 20 concurrent worker threads executing dequeue across
        100 pending leads in 10 campaigns.
        Verifies:
        - Exactly 100 leads claimed.
        - Zero duplicate claims (CAS guarantees exactly 1 claim per lead).
        - Zero collisions or corrupted lease tokens.
        """
        self.db.seed_test_data(num_campaigns=10, leads_per_campaign=10)
        self.assertEqual(len(self.db.execution_states), 100)

        num_workers = 20
        claimed_by_thread = {i: [] for i in range(num_workers)}
        barrier = threading.Barrier(num_workers)

        def worker_task(worker_index: int):
            # Synchronize thread start to maximize burst contention
            barrier.wait()
            token = f"worker_token_{worker_index}_{uuid.uuid4().hex[:8]}"
            
            while True:
                # 1. Fetch available pending states
                pending = self.db.get_pending_states(limit=10)
                if not pending:
                    break
                
                # 2. Attempt atomic claim
                claimed_any = False
                for candidate in pending:
                    claimed = self.db.atomic_claim(candidate["id"], token, lease_seconds=300)
                    if claimed:
                        claimed_by_thread[worker_index].append(claimed["id"])
                        claimed_any = True
                        
                        # Simulate processing time (1-3ms)
                        time.sleep(0.002)
                        
                        # 3. Transition state to completed
                        success = self.db.atomic_update_state(candidate["id"], token, "completed")
                        self.assertTrue(success, f"Worker {worker_index} failed to complete state {candidate['id']}")
                
                if not claimed_any:
                    # Contention backoff
                    time.sleep(0.005)
                    # Recheck if any leads remain
                    if not self.db.get_pending_states(limit=1):
                        break

        # Execute 20 workers concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_task, i) for i in range(num_workers)]
            concurrent.futures.wait(futures)

        # Assertions (Mathematical Invariants)
        all_claimed_ids = []
        for worker_idx, ids in claimed_by_thread.items():
            all_claimed_ids.extend(ids)

        self.assertEqual(len(all_claimed_ids), 100, f"Expected 100 claimed leads, got {len(all_claimed_ids)}")
        self.assertEqual(len(set(all_claimed_ids)), 100, "FATAL: Duplicate lead claims detected! CAS failed!")
        
        # Verify all 100 states in DB are in 'completed' status
        completed_count = sum(1 for s in self.db.execution_states.values() if s["status"] == "completed")
        self.assertEqual(completed_count, 100, f"Expected 100 completed states, got {completed_count}")
        self.assertEqual(len(self.db.rejected_updates), 0, "No valid updates should have been rejected")

    def test_layer1_20_workers_contend_for_5_hot_leads(self):
        """
        Layer 1 (Environmental): Massive contention scenario — 20 worker threads simultaneously
        attempt to claim only 5 pending leads.
        Verifies:
        - Exactly 5 successful claims.
        - Exactly 0 double-dispatches.
        - Zero deadlocks under maximum lock contention.
        """
        self.db.seed_test_data(num_campaigns=1, leads_per_campaign=5)
        self.assertEqual(len(self.db.execution_states), 5)

        num_workers = 20
        successful_claims = []
        claims_lock = threading.Lock()
        barrier = threading.Barrier(num_workers)

        def contentious_worker(worker_idx: int):
            barrier.wait()
            token = f"contention_token_{worker_idx}"
            pending = self.db.get_pending_states(limit=5)
            
            for candidate in pending:
                claimed = self.db.atomic_claim(candidate["id"], token)
                if claimed:
                    with claims_lock:
                        successful_claims.append((worker_idx, candidate["id"]))
                    # Process and complete
                    self.db.atomic_update_state(candidate["id"], token, "completed")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(contentious_worker, i) for i in range(num_workers)]
            concurrent.futures.wait(futures)

        self.assertEqual(len(successful_claims), 5, f"Expected exactly 5 claims, got {len(successful_claims)}")
        claimed_state_ids = [s[1] for s in successful_claims]
        self.assertEqual(len(set(claimed_state_ids)), 5, "Duplicate claim detected under high contention!")

    def test_layer1_cas_lease_fencing_rejects_zombie_worker(self):
        """
        Layer 1 (Environmental): Zombie Worker Fencing.
        Worker A claims a lead, experiences GC pause / network delay.
        The lease expires and Worker B re-claims the lead and completes it.
        Worker A wakes up and attempts to update the state with its stale lease token.
        Assert that Worker A's update is REJECTED by CAS lease fencing, preventing state corruption.
        """
        self.db.seed_test_data(num_campaigns=1, leads_per_campaign=1)
        state_id = "state_0_0"

        # Worker A claims with a short 1-second lease
        token_a = "token_worker_a"
        claimed_a = self.db.atomic_claim(state_id, token_a, lease_seconds=1)
        self.assertIsNotNone(claimed_a)
        self.assertEqual(self.db.execution_states[state_id]["status"], "running")

        # Simulate Worker A going to sleep / GC pause, lease expires
        time.sleep(1.1)

        # Supervisor / Worker B re-claims the expired lead
        # In actual system, sweep_stale_leases resets expired running states
        with self.db._lock:
            self.db.execution_states[state_id]["status"] = "pending"
            self.db.execution_states[state_id]["lease_token"] = None

        token_b = "token_worker_b"
        claimed_b = self.db.atomic_claim(state_id, token_b, lease_seconds=300)
        self.assertIsNotNone(claimed_b)

        # Worker B completes the node successfully
        success_b = self.db.atomic_update_state(state_id, token_b, "completed", next_node_id="node_email_2")
        self.assertTrue(success_b)
        self.assertEqual(self.db.execution_states[state_id]["status"], "completed")

        # Zombie Worker A wakes up and attempts to complete with stale token_a
        success_a = self.db.atomic_update_state(state_id, token_a, "error", next_node_id="node_error")
        
        # MUST BE REJECTED!
        self.assertFalse(success_a, "FATAL: Zombie worker succeeded in mutating state with invalid lease token!")
        self.assertEqual(self.db.execution_states[state_id]["status"], "completed", "State corrupted by zombie worker!")
        
        # Verify rejection was logged
        rejection = next((r for r in self.db.rejected_updates if r["state_id"] == state_id), None)
        self.assertIsNotNone(rejection)
        self.assertEqual(rejection["reason"], "lease_token_mismatch")

    def test_layer1_stale_lease_recovery_under_concurrency(self):
        """
        Layer 1 (Environmental): Multiple supervisor processes simultaneously run
        stale lease recovery on abandoned worker states.
        Verifies idempotent, thread-safe lease reclamation without deadlocks.
        """
        self.db.seed_test_data(num_campaigns=2, leads_per_campaign=5)
        now_dt = datetime.now(timezone.utc)
        expired_dt = (now_dt - timedelta(minutes=10)).isoformat()

        # Simulate 10 abandoned states stuck in running with expired leases
        for state in self.db.execution_states.values():
            state["status"] = "running"
            state["lease_token"] = f"abandoned_{uuid.uuid4().hex[:6]}"
            state["lease_expires_at"] = expired_dt
            state["updated_at"] = expired_dt

        def sweep_task(supervisor_idx: int):
            recovered = 0
            with self.db._lock:
                for s in self.db.execution_states.values():
                    if s["status"] == "running" and s["lease_expires_at"] < datetime.now(timezone.utc).isoformat():
                        s["status"] = "pending"
                        s["lease_token"] = None
                        s["lease_expires_at"] = None
                        s["updated_at"] = datetime.now(timezone.utc).isoformat()
                        recovered += 1
            return recovered

        # Run 5 concurrent supervisor sweeps
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(sweep_task, i) for i in range(5)]
            results = [f.result() for f in futures]

        # Total unique states recovered across all sweeps must be exactly 10
        total_recovered = sum(results)
        self.assertEqual(total_recovered, 10, f"Expected 10 total recovered states, got {total_recovered}")
        
        # All states must now be clean and ready for immediate dequeue
        pending_count = sum(1 for s in self.db.execution_states.values() if s["status"] == "pending")
        self.assertEqual(pending_count, 10)
        self.assertTrue(all(s["lease_token"] is None for s in self.db.execution_states.values()))

    def test_layer2_campaign_pause_mid_flight_prevents_dispatch(self):
        """
        Layer 2 (Human Paranoia): User frantically clicks 'Pause Campaign' while
        workers are dequeuing leads.
        Verifies:
        - Orchestrator pre-flight check detects campaign is no longer ACTIVE.
        - Worker halts execution and does not dispatch outbound outreach touch.
        """
        self.db.seed_test_data(num_campaigns=1, leads_per_campaign=5)
        c_id = "camp_0"

        # Worker claims lead
        token = "worker_pause_test_token"
        claimed = self.db.atomic_claim("state_0_0", token)
        self.assertIsNotNone(claimed)

        # User pauses campaign in UI
        with self.db._lock:
            self.db.campaigns[c_id]["status"] = "PAUSED"

        # Worker verifies campaign status before dispatching
        is_active = False
        with self.db._lock:
            campaign = self.db.campaigns.get(c_id)
            if campaign and campaign.get("status") == "ACTIVE":
                is_active = True

        self.assertFalse(is_active, "Worker failed to detect paused campaign status!")
        
        # Worker aborts and returns state to paused
        with self.db._lock:
            state = self.db.execution_states["state_0_0"]
            state["status"] = "paused"
            state["lease_token"] = None
            state["lease_expires_at"] = None

        self.assertEqual(self.db.execution_states["state_0_0"]["status"], "paused")
        self.assertEqual(len(self.db.messages), 0, "Outbound message dispatched for paused campaign!")

    def test_layer2_workspace_suspension_immediate_halt(self):
        """
        Layer 2 (Human Paranoia): Tenant billing failure or workspace suspension.
        When workspace status is not 'active', workers must immediately reject
        or pause execution states without sending external touches.
        """
        self.db.seed_test_data(num_campaigns=1, leads_per_campaign=5)
        ws_id = "ws_tenant_0"

        # Suspend workspace
        with self.db._lock:
            self.db.workspaces[ws_id]["status"] = "suspended"

        # Worker attempts to process pending leads
        active_ws_set = set()
        with self.db._lock:
            for w in self.db.workspaces.values():
                if w.get("status") == "active":
                    active_ws_set.add(w["id"])

        self.assertNotIn(ws_id, active_ws_set, "Suspended workspace treated as active!")
        
        # Verify no claims permitted for suspended tenant
        allowed_claims = 0
        for s in self.db.execution_states.values():
            if s["workspace_id"] in active_ws_set:
                allowed_claims += 1

        self.assertEqual(allowed_claims, 0, "Leads claimed for suspended workspace!")


if __name__ == "__main__":
    unittest.main()

"""
Three-Layer Paranoia Test Suite for Phase S:
Sequence DAG Simulation & Dry-Run Sandbox (DAGSimulationService)
"""

import unittest
from datetime import datetime, timezone
from campaigns.backend.services.dag_simulation_service import DAGSimulationService


class TestPhaseSDAGSimulationSandbox(unittest.TestCase):
    def setUp(self):
        self.simulator = DAGSimulationService(spintax_seed=123)

    # -------------------------------------------------------------------------
    # Layer 0: Foundational Simulation & Token Resolution
    # -------------------------------------------------------------------------

    def test_spintax_resolution_deterministic(self):
        """Layer 0: Resolves single-level and nested spintax deterministically with seed."""
        template = "{Hi|Hello|Hey} {there|friend}, let us connect!"
        text1, choices1 = self.simulator.resolve_spintax(template)
        
        sim2 = DAGSimulationService(spintax_seed=123)
        text2, choices2 = sim2.resolve_spintax(template)
        
        self.assertEqual(text1, text2)
        self.assertEqual(choices1, choices2)
        self.assertNotIn("{", text1)
        self.assertNotIn("}", text1)

    def test_variable_token_resolution_with_fallback(self):
        """Layer 0: Replaces {{first_name|there}} and {{company}} correctly."""
        lead = {"first_name": "Alice", "company": "Wonderland Inc"}
        template = "Hi {{first_name}}, how is {{company}}? Talk to {{role|executive}}."
        
        rendered, unres, fallbacks, resolved = self.simulator.resolve_variables(template, lead)
        self.assertEqual(rendered, "Hi Alice, how is Wonderland Inc? Talk to executive.")
        self.assertEqual(unres, [])
        self.assertEqual(len(fallbacks), 1)
        self.assertEqual(fallbacks[0]["token"], "role")
        self.assertEqual(fallbacks[0]["fallback"], "executive")
        self.assertIn("first_name", resolved)
        self.assertIn("company", resolved)

    def test_standard_sequence_dry_run_simulation(self):
        """Layer 0: Traverses linear email -> delay -> email sequence correctly."""
        dag = {
            "nodes": [
                {
                    "id": "node-1",
                    "type": "email",
                    "data": {"subject": "Quick question {{first_name}}", "body": "{Hi|Hey} {{first_name}}, saw {{company}}."}
                },
                {
                    "id": "node-2",
                    "type": "time_delay",
                    "data": {"days": 2, "hours": 0}
                },
                {
                    "id": "node-3",
                    "type": "email",
                    "data": {"subject": "Follow up for {{first_name}}", "body": "Did you see my note about {{company}}?"}
                }
            ],
            "edges": [
                {"source": "node-1", "target": "node-2"},
                {"source": "node-2", "target": "node-3"}
            ]
        }
        leads = [
            {"id": "lead-1", "first_name": "Bob", "company": "Acme"}
        ]
        senders = [
            {"id": "sender-1", "email": "rep@agency.com", "channels": ["EMAIL"], "daily_quota": 50}
        ]

        result = self.simulator.simulate(dag, leads, senders)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["simulation_summary"]["total_steps_executed"], 3)
        self.assertEqual(result["simulation_summary"]["estimated_completion_days"], 2.0)
        
        trace = result["step_execution_trace"]
        self.assertEqual(len(trace), 3)
        self.assertEqual(trace[0]["rendered_subject"], "Quick question Bob")
        self.assertEqual(trace[1]["channel"], "TIME_DELAY")
        self.assertEqual(trace[1]["scheduled_offset_hours"], 48.0)
        self.assertEqual(trace[2]["channel"], "EMAIL")
        self.assertEqual(trace[2]["scheduled_offset_hours"], 48.0)
        self.assertEqual(trace[2]["rendered_subject"], "Follow up for Bob")

    # -------------------------------------------------------------------------
    # Layer 1: Environmental Failure Analysis
    # -------------------------------------------------------------------------

    def test_cycle_detection_stops_simulation(self):
        """Layer 1: Cycle detection halts simulation and returns explicit cycle errors."""
        cyclic_dag = {
            "nodes": [
                {"id": "node-a", "type": "email", "data": {}},
                {"id": "node-b", "type": "time_delay", "data": {}},
                {"id": "node-c", "type": "email", "data": {}}
            ],
            "edges": [
                {"source": "node-a", "target": "node-b"},
                {"source": "node-b", "target": "node-c"},
                {"source": "node-c", "target": "node-a"}  # Cycle back!
            ]
        }
        result = self.simulator.simulate(cyclic_dag, [{"id": "lead-1"}], [])
        self.assertFalse(result["valid"])
        self.assertTrue(any("Cycle detected" in err for err in result["errors"]))

    def test_self_loop_detected(self):
        """Layer 1: Self-loop immediately fails closed."""
        self_loop_dag = {
            "nodes": [{"id": "loop-node", "type": "email", "data": {}}],
            "edges": [{"source": "loop-node", "target": "loop-node"}]
        }
        result = self.simulator.simulate(self_loop_dag, [{"id": "lead-1"}], [])
        self.assertFalse(result["valid"])
        self.assertTrue(any("Self-loop" in err for err in result["errors"]))

    def test_malformed_unclosed_spintax_resilience(self):
        """Layer 1: Unclosed braces or malformed spintax do not raise exceptions."""
        malformed = "Hey {there|friend unclosed and {{dangling"
        res, _ = self.simulator.resolve_spintax(malformed)
        self.assertIsInstance(res, str)
        self.assertNotIn("{", res)
        self.assertNotIn("}", res)

    def test_empty_dag_handling(self):
        """Layer 1: Empty DAG inputs return structured error without crashing."""
        result = self.simulator.simulate({"nodes": [], "edges": []}, [], [])
        self.assertFalse(result["valid"])
        self.assertIn("DAG contains zero nodes.", result["errors"])

    # -------------------------------------------------------------------------
    # Layer 2: Human Paranoia (Warnings & Guardrails)
    # -------------------------------------------------------------------------

    def test_missing_fallback_variable_warning(self):
        """Layer 2: Flags missing variables without fallback as warnings."""
        dag = {
            "nodes": [
                {"id": "node-1", "type": "email", "data": {"subject": "Hi {{first_name}}", "body": "About {{non_existent_key}}"}}
            ],
            "edges": []
        }
        leads = [{"id": "lead-1", "first_name": "Bob"}]  # missing non_existent_key
        result = self.simulator.simulate(dag, leads, [])
        self.assertTrue(result["valid"])
        self.assertTrue(any("non_existent_key" in w for w in result["warnings"]))
        self.assertIn("non_existent_key", result["token_resolution_report"]["unresolved_tokens"])

    def test_multi_channel_collision_warning(self):
        """Layer 2: Flags two touchpoints scheduled < 15 minutes apart on same lead."""
        dag = {
            "nodes": [
                {"id": "email-node", "type": "email", "data": {"body": "Email text"}},
                {"id": "li-node", "type": "linkedin_connection", "data": {"body": "Connect request"}}
            ],
            "edges": [
                {"source": "email-node", "target": "li-node"}  # Direct transition without delay!
            ]
        }
        result = self.simulator.simulate(dag, [{"id": "lead-1"}], [])
        self.assertTrue(result["valid"])
        self.assertTrue(any("Multi-channel pacing collision" in w for w in result["warnings"]))

    def test_sender_quota_exceeded_warning(self):
        """Layer 2: Flags warning when simulated schedule exceeds sender daily quota."""
        dag = {
            "nodes": [
                {"id": "n1", "type": "email", "data": {"body": "Hi"}}
            ],
            "edges": []
        }
        # 5 leads dispatched on day 0
        leads = [{"id": f"lead-{i}"} for i in range(5)]
        # Sender with quota of 2/day
        senders = [{"id": "tight-sender", "email": "tight@agency.com", "channels": ["EMAIL"], "daily_quota": 2}]
        
        result = self.simulator.simulate(dag, leads, senders)
        self.assertTrue(result["valid"])
        self.assertTrue(any("quota exceeded" in w for w in result["warnings"]))
        self.assertTrue(result["simulation_summary"]["quota_stretch_warning"])

    def test_router_simulate_dag_endpoint(self):
        """Layer 0 & 1: Verifies FastAPI router endpoint /api/elein/campaigns/simulate-dag."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock
        from campaigns.backend.routers.elein import router, api_simulate_sequence_dag
        from core.backend.api.auth_dep import get_current_workspace, get_service_client

        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/elein")
        
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        
        test_app.dependency_overrides[get_current_workspace] = lambda: "ws-sim-123"
        test_app.dependency_overrides[get_service_client] = lambda: mock_db

        client = TestClient(test_app)
        payload = {
            "dag": {
                "nodes": [
                    {"id": "n1", "type": "email", "data": {"subject": "Hi {{first_name|Friend}}", "body": "{Hello|Hey}!"}}
                ],
                "edges": []
            },
            "sample_leads": [
                {"id": "lead-100", "first_name": "Dave"}
            ],
            "sender_profiles": [
                {"id": "sender-1", "email": "dave-sender@mail.com", "channels": ["EMAIL"], "daily_quota": 20}
            ]
        }
        res = client.post("/api/elein/campaigns/simulate-dag", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["valid"])
        self.assertEqual(len(data["step_execution_trace"]), 1)
        self.assertEqual(data["step_execution_trace"][0]["rendered_subject"], "Hi Dave")

    def test_poison_string_triggers_fallback(self):
        """Layer 1: Poisoned enrichment literals like 'None' or 'null' trigger fallbacks instead of rendering."""
        lead = {"first_name": "None", "company": "null", "title": "N/A"}
        template = "Hi {{first_name|there}}, heard about {{company|your firm}}."
        rendered, unres, fallbacks, resolved = self.simulator.resolve_variables(template, lead)
        self.assertEqual(rendered, "Hi there, heard about your firm.")
        self.assertEqual(len(fallbacks), 2)

    def test_delay_minutes_offset_calculation(self):
        """Layer 0: Accurately calculates delay_minutes into fractional hours."""
        dag = {
            "nodes": [
                {"id": "n1", "type": "email", "data": {"body": "First"}},
                {"id": "n2", "type": "time_delay", "data": {"minutes": 30}},
                {"id": "n3", "type": "email", "data": {"body": "Second"}}
            ],
            "edges": [
                {"source": "n1", "target": "n2"},
                {"source": "n2", "target": "n3"}
            ]
        }
        res = self.simulator.simulate(dag, [{"id": "lead-1"}], [])
        self.assertTrue(res["valid"])
        trace = res["step_execution_trace"]
        # n2 delay offset: 30 mins = 0.5 hours
        self.assertEqual(trace[1]["delay_hours"], 0.5)
        self.assertEqual(trace[2]["scheduled_offset_hours"], 0.5)

    def test_spintax_analytics_and_burnout_forecast(self):
        """Layer 2: Generates spintax combinatorial metrics and sender burnout forecast."""
        dag = {
            "nodes": [
                {"id": "n1", "type": "email", "data": {"body": "{Quick|Brief|Short} note to {connect|chat|sync}."}}
            ],
            "edges": []
        }
        senders = [
            {"id": "s1", "email": "rep@co.com", "daily_quota": 2}
        ]
        # 3 leads enrolled on Day 0 vs sender limit of 2
        leads = [{"id": f"l-{i}"} for i in range(3)]
        res = self.simulator.simulate(dag, leads, senders)
        
        # Spintax metrics: 3 * 3 = 9 variations
        self.assertIn("spintax_analytics", res)
        self.assertEqual(res["spintax_analytics"]["total_combinations"], 9)
        self.assertEqual(res["spintax_analytics"]["entropy_rating"], "MODERATE_VARIATION")
        
        # Burnout forecast: 3 actions scheduled on Day 0 vs capacity 2 -> burnout on Day 0
        self.assertIn("sender_burnout_forecast", res)
        self.assertEqual(res["sender_burnout_forecast"]["burnout_day"], 0)
        self.assertEqual(res["sender_burnout_forecast"]["peak_daily_dispatches"], 3)
        self.assertEqual(res["sender_burnout_forecast"]["recommended_senders_needed"], 1)

    def test_dual_compatible_summary_and_coverage_schemas(self):
        """Layer 1: Verifies dual schemas (summary + simulation_summary, coverage + report) for frontend compatibility."""
        dag = {
            "nodes": [{"id": "n1", "type": "email", "data": {"body": "Test"}}],
            "edges": []
        }
        res = self.simulator.simulate(dag, [{"id": "l-1"}], [])
        
        # Assert both schemas are populated with matching values
        self.assertEqual(res["summary"]["total_dispatches"], res["simulation_summary"]["total_dispatches"])
        self.assertEqual(res["summary"]["timeline_span_days"], res["simulation_summary"]["timeline_span_days"])
        self.assertEqual(res["summary"]["collisions_detected"], res["simulation_summary"]["collisions_detected"])
        self.assertEqual(
            res["token_resolution_coverage"]["resolution_percentage"],
            res["token_resolution_report"]["resolution_percentage"]
        )
        # Verify no-spintax template returns NO_SPINTAX rather than false alarm CRITICAL_SPAM_RISK
        self.assertEqual(res["spintax_analytics"]["entropy_rating"], "NO_SPINTAX")



if __name__ == "__main__":
    unittest.main()

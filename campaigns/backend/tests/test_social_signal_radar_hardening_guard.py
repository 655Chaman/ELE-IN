import unittest
from datetime import datetime, timezone, timedelta
from leads.backend.services.social_radar_service import (
    parse_relative_social_date,
    extract_voyager_post_fields,
    calculate_scrape_jitter,
    detect_scraping_challenge,
    scan_lead_social_feed,
    batch_scan_list_social_signals,
    export_social_radar_feed_csv,
    sanitize_text,
    MAX_BATCH_SCAN_SIZE
)

class MockSupabaseTable:
    def __init__(self, data=None):
        self._data = data or []
        self._filters = {}

    def select(self, *args, **kwargs):
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def gt(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def insert(self, data):
        self._inserted = data
        return self

    def update(self, data):
        self._updated = data
        return self

    def upsert(self, data, on_conflict=None):
        self._upserted = data
        return self

    def delete(self, *args, **kwargs):
        return self

    def execute(self):
        class Result:
            def __init__(self, data):
                self.data = data
        return Result(self._data)


class MockSupabaseClient:
    def __init__(self, leads=None, lists=None, posts=None, signals=None):
        self.leads = leads or []
        self.lists = lists or []
        self.posts = posts or []
        self.signals = signals or []

    def table(self, name):
        if name == "leads":
            return MockSupabaseTable(self.leads)
        elif name == "lead_lists":
            return MockSupabaseTable(self.lists)
        elif name == "list_members":
            return MockSupabaseTable([])
        elif name == "lead_social_posts":
            return MockSupabaseTable(self.posts)
        elif name == "lead_social_signals":
            return MockSupabaseTable(self.signals)
        elif name == "campaigns":
            return MockSupabaseTable([{"id": "c1", "name": "Test Camp", "status": "active"}])
        return MockSupabaseTable([])


class TestSocialSignalRadarHardeningGuard(unittest.TestCase):

    def test_parse_relative_social_date(self):
        ref = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)
        
        # Test hours
        res_h = parse_relative_social_date("2h", reference_dt=ref)
        dt_h = datetime.fromisoformat(res_h.replace("Z", "+00:00"))
        self.assertEqual(dt_h, ref - timedelta(hours=2))

        # Test days
        res_d = parse_relative_social_date("3d", reference_dt=ref)
        dt_d = datetime.fromisoformat(res_d.replace("Z", "+00:00"))
        self.assertEqual(dt_d, ref - timedelta(days=3))

        # Test weeks
        res_w = parse_relative_social_date("1w", reference_dt=ref)
        dt_w = datetime.fromisoformat(res_w.replace("Z", "+00:00"))
        self.assertEqual(dt_w, ref - timedelta(weeks=1))

        # Test months/years or verbose
        res_yr = parse_relative_social_date("1yr", reference_dt=ref)
        self.assertIsInstance(res_yr, str)

        res_now = parse_relative_social_date("just now", reference_dt=ref)
        self.assertEqual(res_now, ref.isoformat())

        # ISO string pass-through
        iso_str = "2026-10-10T12:00:00Z"
        res_iso = parse_relative_social_date(iso_str, reference_dt=ref)
        self.assertIn("2026-10-10T12:00:00", res_iso)

        # Invalid fallback
        fallback = parse_relative_social_date(None, reference_dt=ref)
        self.assertEqual(fallback, ref.isoformat())

    def test_extract_voyager_post_fields_fallback_paths(self):
        # Nested commentary text path
        node1 = {
            "commentary": {
                "text": {
                    "text": "Excited to launch our new product line!"
                }
            },
            "permalink": "https://linkedin.com/posts/test-1",
            "socialDetail": {
                "likesCount": 42,
                "commentsCount": 5,
                "sharesCount": 2
            },
            "createdTime": "2026-10-10T10:00:00Z"
        }
        res1 = extract_voyager_post_fields(node1)
        self.assertIn("Excited to launch", res1["post_text"])
        self.assertEqual(res1["engagement_count"]["likes"], 42)
        self.assertEqual(res1["engagement_count"]["comments"], 5)
        self.assertEqual(res1["engagement_count"]["reposts"], 2)

        # Alternative ugc ShareContent path
        node2 = {
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": "Building the future of recruitment."
                    }
                }
            },
            "updateUrl": "https://linkedin.com/posts/test-2"
        }
        res2 = extract_voyager_post_fields(node2)
        self.assertIn("Building the future", res2["post_text"])
        self.assertEqual(res2["post_url"], "https://linkedin.com/posts/test-2")

    def test_detect_scraping_challenge(self):
        # 429 Rate limit
        is_chal, reason = detect_scraping_challenge(429, "Too many requests")
        self.assertTrue(is_chal)
        self.assertIn("rate limit", reason.lower())

        # 999 Security block
        is_chal, reason = detect_scraping_challenge(999, "")
        self.assertTrue(is_chal)

        # HTML checkpoint challenge
        is_chal, reason = detect_scraping_challenge(200, "Please verify your account via security verification checkpoint")
        self.assertTrue(is_chal)
        self.assertIn("checkpoint", reason.lower())

        # Normal response
        is_chal, reason = detect_scraping_challenge(200, "Welcome to LinkedIn feed")
        self.assertFalse(is_chal)

    def test_calculate_scrape_jitter(self):
        delay = calculate_scrape_jitter(base_delay=2.0, max_jitter=4.0)
        self.assertGreaterEqual(delay, 2.5)
        self.assertLessEqual(delay, 6.0)

        # Seeded determinism
        d1 = calculate_scrape_jitter(seed="test-seed")
        d2 = calculate_scrape_jitter(seed="test-seed")
        self.assertEqual(d1, d2)

    def test_scan_lead_social_feed_cooldown_and_cache(self):
        now_str = datetime.now(timezone.utc).isoformat()
        leads = [{
            "id": "lead-1",
            "workspace_id": "ws-1",
            "first_name": "Alice",
            "company_name": "Acme",
            "last_social_scan_at": now_str, # recent scan within 15 mins
            "social_intent_score": 80,
            "social_intent_tier": "HOT"
        }]
        supabase = MockSupabaseClient(leads=leads)

        # Should hit cache (cooldown active)
        result = scan_lead_social_feed("lead-1", "ws-1", supabase, force_refresh=False)
        self.assertTrue(result["is_cached"])
        self.assertEqual(result["social_intent_score"], 80)

    def test_batch_scan_list_clamping(self):
        self.assertEqual(MAX_BATCH_SCAN_SIZE, 100)
        lists = [{"id": "list-1", "name": "Key Accounts"}]
        supabase = MockSupabaseClient(lists=lists)

        # Even if max_leads > 100 or batch scan size is requested
        res = batch_scan_list_social_signals("list-1", "ws-1", supabase, max_leads=200)
        self.assertEqual(res["status"], "success")

    def test_cross_tenant_workspace_isolation(self):
        # Lead belongs to ws-2, query specifies ws-1 -> should raise PermissionError
        leads = [{
            "id": "lead-foreign",
            "workspace_id": "ws-2",
            "first_name": "Bob"
        }]
        supabase = MockSupabaseClient(leads=leads)

        with self.assertRaises(PermissionError):
            scan_lead_social_feed("lead-foreign", "ws-1", supabase)

    def test_formula_injection_defense_in_export_csv(self):
        # Verify sanitization prefixing
        self.assertEqual(sanitize_text("=SUM(A1:A10)"), "SUM(A1:A10)")
        self.assertEqual(sanitize_text("+12345"), "12345")
        self.assertEqual(sanitize_text("@cmd"), "cmd")
        self.assertEqual(sanitize_text("Safe Text"), "Safe Text")

        # Verify CSV export contains sanitized values
        leads = [{
            "id": "lead-formula",
            "workspace_id": "ws-1",
            "first_name": "=Malicious",
            "last_name": "User",
            "company_name": "@Acme",
            "job_title": "-CEO",
            "social_intent_score": 90,
            "social_intent_tier": "HOT",
            "recommended_timing": "IMMEDIATE_ACTION",
            "best_outreach_angle": "Direct",
            "social_icebreaker": "Hi"
        }]
        supabase = MockSupabaseClient(leads=leads)
        csv_data = export_social_radar_feed_csv("ws-1", supabase, include_demo_fallback=False)
        self.assertNotIn("=Malicious", csv_data)
        self.assertNotIn("@Acme", csv_data)
        self.assertNotIn("-CEO", csv_data)
        self.assertIn("Malicious", csv_data)


if __name__ == "__main__":
    unittest.main()

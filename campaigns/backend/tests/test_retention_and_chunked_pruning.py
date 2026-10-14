"""
Unit tests for Step 26: Retention Horizon & Chunked Pruning Service (Paranoia Framework)
"""
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from core.backend.services.retention_service import (
    prune_expired_outbox_events,
    prune_expired_notifications,
    run_retention_prune_cycle
)

class MockSupabaseQueryBuilder:
    def __init__(self, table_name, rows=None, workspace_id=None, filters=None, limit_val=None):
        self.table_name = table_name
        self.rows = rows or []
        self.workspace_id = workspace_id
        self.filters = filters or []
        self.limit_val = limit_val

    def select(self, cols):
        return self

    def insert(self, val):
        return self

    def update(self, val):
        return self

    def delete(self):
        return self

    def eq(self, col, val):
        new_filters = self.filters + [('eq', col, val)]
        if col == 'workspace_id':
            self.workspace_id = val
        return MockSupabaseQueryBuilder(self.table_name, self.rows, self.workspace_id, new_filters, self.limit_val)

    def in_(self, col, vals):
        new_filters = self.filters + [('in', col, vals)]
        return MockSupabaseQueryBuilder(self.table_name, self.rows, self.workspace_id, new_filters, self.limit_val)

    def lt(self, col, val):
        new_filters = self.filters + [('lt', col, val)]
        return MockSupabaseQueryBuilder(self.table_name, self.rows, self.workspace_id, new_filters, self.limit_val)

    @property
    def not_(self):
        class NotBuilder:
            def __init__(self, outer):
                self.outer = outer
            def is_(self, col, val):
                new_filters = self.outer.filters + [('is_not', col, val)]
                return MockSupabaseQueryBuilder(self.outer.table_name, self.outer.rows, self.outer.workspace_id, new_filters, self.outer.limit_val)
        return NotBuilder(self)

    def is_(self, col, val):
        new_filters = self.filters + [('is', col, val)]
        return MockSupabaseQueryBuilder(self.table_name, self.rows, self.workspace_id, new_filters, self.limit_val)

    def filter(self, col, op, val):
        new_filters = self.filters + [(op, col, val)]
        return MockSupabaseQueryBuilder(self.table_name, self.rows, self.workspace_id, new_filters, self.limit_val)

    def limit(self, n):
        return MockSupabaseQueryBuilder(self.table_name, self.rows, self.workspace_id, self.filters, n)

    def execute(self):
        # Filter rows based on conditions
        matched = []
        for r in self.rows:
            # Workspace filter
            if self.workspace_id and r.get('workspace_id') and r.get('workspace_id') != self.workspace_id:
                continue
            
            # Evaluate filters
            include = True
            for f_type, col, val in self.filters:
                if f_type == 'eq':
                    if r.get(col) != val:
                        include = False
                        break
                elif f_type == 'in':
                    if r.get(col) not in val:
                        include = False
                        break
                elif f_type == 'lt':
                    row_val = r.get(col)
                    if not row_val or row_val >= val:
                        include = False
                        break
                elif f_type == 'is':
                    row_val = r.get(col)
                    if val in (None, 'null', 'NULL') and row_val is not None:
                        include = False
                        break
                    elif val not in (None, 'null', 'NULL') and row_val != val:
                        include = False
                        break
                elif f_type == 'not.is':
                    row_val = r.get(col)
                    if val == 'null' and row_val is None:
                        include = False
                        break
            if include:
                matched.append(r)
        
        if self.limit_val is not None:
            matched = matched[:self.limit_val]

        class Res:
            def __init__(self, d):
                self.data = d
        return Res(matched)


class MockSupabaseClient:
    def __init__(self, outbox_rows=None, notif_rows=None):
        self.outbox_rows = outbox_rows or []
        self.notif_rows = notif_rows or []
        self.deleted_ids = []

    def table(self, name):
        if name == 'outbox_events':
            return MockSupabaseTable(self.outbox_rows, self.deleted_ids, name)
        elif name == 'notifications':
            return MockSupabaseTable(self.notif_rows, self.deleted_ids, name)
        return MockSupabaseTable([], self.deleted_ids, name)


class MockSupabaseTable:
    def __init__(self, rows, deleted_sink, table_name):
        self.rows = rows
        self.deleted_sink = deleted_sink
        self.table_name = table_name

    def select(self, cols):
        return MockSupabaseQueryBuilder(self.table_name, self.rows)

    def delete(self):
        return MockSupabaseDeleteBuilder(self.rows, self.deleted_sink, self.table_name)


class MockSupabaseDeleteBuilder:
    def __init__(self, rows, deleted_sink, table_name):
        self.rows = rows
        self.deleted_sink = deleted_sink
        self.table_name = table_name
        self.filters = []
        self.workspace_id = None

    def eq(self, col, val):
        self.filters.append(('eq', col, val))
        if col == 'workspace_id':
            self.workspace_id = val
        return self

    def in_(self, col, vals):
        self.filters.append(('in', col, vals))
        return self

    def execute(self):
        ids_to_delete = set()
        for f in self.filters:
            if f[0] == 'in' and f[1] == 'id':
                ids_to_delete.update(f[2])
            if f[0] == 'eq' and f[1] == 'id':
                ids_to_delete.add(f[2])
        
        surviving = []
        for r in self.rows:
            if self.workspace_id and r.get('workspace_id') and r.get('workspace_id') != self.workspace_id:
                surviving.append(r)
                continue
            
            if r.get('id') in ids_to_delete:
                # Check status whitelist if outbox
                if self.table_name == 'outbox_events':
                    status = r.get('status')
                    # Ensure pending/processing never deleted
                    if status in ['pending', 'processing']:
                        surviving.append(r)
                        continue
                self.deleted_sink.append(r['id'])
            else:
                surviving.append(r)
        self.rows[:] = surviving
        class Res:
            data = []
        return Res()


class TestRetentionAndChunkedPruning(unittest.TestCase):

    def test_prune_delivered_outbox_events_respects_cutoff(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        recent_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        
        rows = [
            {"id": "ev-1", "status": "delivered", "delivered_at": old_time, "workspace_id": "ws-1"},
            {"id": "ev-2", "status": "delivered", "delivered_at": recent_time, "workspace_id": "ws-1"}
        ]
        svc = MockSupabaseClient(outbox_rows=rows)
        res = prune_expired_outbox_events(svc, retention_days=14, workspace_id="ws-1")
        
        self.assertEqual(res["deleted_delivered"], 1)
        self.assertIn("ev-1", svc.deleted_ids)
        self.assertNotIn("ev-2", svc.deleted_ids)

    def test_pending_and_processing_outbox_events_immune_to_pruning(self):
        ancient_time = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        rows = [
            {"id": "pending-1", "status": "pending", "created_at": ancient_time, "workspace_id": "ws-1"},
            {"id": "processing-1", "status": "processing", "created_at": ancient_time, "workspace_id": "ws-1"}
        ]
        svc = MockSupabaseClient(outbox_rows=rows)
        res = prune_expired_outbox_events(svc, retention_days=1, workspace_id="ws-1")
        
        self.assertEqual(res["total_deleted"], 0)
        self.assertEqual(len(svc.deleted_ids), 0)

    def test_failed_outbox_events_pruned_with_longer_cutoff(self):
        old_failed = (datetime.now(timezone.utc) - timedelta(days=70)).isoformat()
        rows = [
            {"id": "fail-1", "status": "failed", "updated_at": old_failed, "workspace_id": "ws-1"}
        ]
        svc = MockSupabaseClient(outbox_rows=rows)
        res = prune_expired_outbox_events(svc, failed_retention_days=60, workspace_id="ws-1")
        
        self.assertEqual(res["deleted_failed"], 1)
        self.assertIn("fail-1", svc.deleted_ids)

    def test_chunked_deletion_respects_chunk_size_and_max_chunks(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        rows = [{"id": f"ev-{i}", "status": "delivered", "delivered_at": old_time, "workspace_id": "ws-1"} for i in range(12)]
        svc = MockSupabaseClient(outbox_rows=rows)
        res = prune_expired_outbox_events(svc, retention_days=14, chunk_size=5, max_chunks=2, workspace_id="ws-1")
        
        # Max chunks = 2, chunk size = 5 -> max 10 deleted in 2 cycles (or total available if chunk size wasn't enforced by mock delete)
        # In our test mock delete deletes all ids passed in in_('id', ids), which receives chunk_size ids per query loop.
        # But wait, in prune_expired_outbox_events, it selects chunk_size items per query.
        # In chunk 1: selects 5, deletes 5. In chunk 2: selects 5, deletes 5. Total deleted = 10. Surviving = 2.
        self.assertEqual(res["deleted_delivered"], 10)
        self.assertEqual(len(svc.outbox_rows), 2)

    def test_dry_run_mode_counts_candidates_without_deleting(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        rows = [{"id": f"ev-{i}", "status": "delivered", "delivered_at": old_time, "workspace_id": "ws-1"} for i in range(3)]
        svc = MockSupabaseClient(outbox_rows=rows)
        res = prune_expired_outbox_events(svc, retention_days=14, dry_run=True, workspace_id="ws-1")
        
        self.assertEqual(res["deleted_delivered"], 3)
        self.assertTrue(res["dry_run"])
        self.assertEqual(len(svc.outbox_rows), 3)  # Nothing actually deleted

    def test_operator_negative_retention_days_clamped_safely(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        rows = [{"id": "ev-1", "status": "delivered", "delivered_at": old_time, "workspace_id": "ws-1"}]
        svc = MockSupabaseClient(outbox_rows=rows)
        # Negative days should be clamped to 1
        res = prune_expired_outbox_events(svc, retention_days=-5, workspace_id="ws-1")
        self.assertEqual(res["deleted_delivered"], 1)

    def test_prune_read_notifications_respects_cutoff(self):
        old_read = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        recent_read = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        rows = [
            {"id": "notif-1", "read_at": old_read, "workspace_id": "ws-1"},
            {"id": "notif-2", "read_at": recent_read, "workspace_id": "ws-1"}
        ]
        svc = MockSupabaseClient(notif_rows=rows)
        res = prune_expired_notifications(svc, read_retention_days=30, workspace_id="ws-1")
        
        self.assertEqual(res["deleted_read"], 1)
        self.assertIn("notif-1", svc.deleted_ids)

    def test_prune_unread_notifications_respects_minimum_floor(self):
        ancient_created = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        rows = [
            {"id": "unread-1", "read_at": None, "created_at": ancient_created, "workspace_id": "ws-1"}
        ]
        svc = MockSupabaseClient(notif_rows=rows)
        res = prune_expired_notifications(svc, unread_retention_days=10, workspace_id="ws-1")
        
        self.assertEqual(res["deleted_unread"], 1)
        self.assertIn("unread-1", svc.deleted_ids)

    def test_workspace_isolation_filters_by_workspace_id(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        rows = [
            {"id": "ev-ws1", "status": "delivered", "delivered_at": old_time, "workspace_id": "ws-1"},
            {"id": "ev-ws2", "status": "delivered", "delivered_at": old_time, "workspace_id": "ws-2"}
        ]
        svc = MockSupabaseClient(outbox_rows=rows)
        res = prune_expired_outbox_events(svc, retention_days=14, workspace_id="ws-1")
        
        self.assertEqual(res["deleted_delivered"], 1)
        self.assertIn("ev-ws1", svc.deleted_ids)
        self.assertTrue(any(r["id"] == "ev-ws2" for r in svc.outbox_rows))

    def test_run_retention_prune_cycle_aggregates(self):
        pass # covered by cycle test below

    def test_run_retention_prune_cycle_aggregates_outbox_and_notifications(self):
        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        outbox_rows = [{"id": "ev-1", "status": "delivered", "delivered_at": old_time, "workspace_id": "ws-1"}]
        notif_rows = [{"id": "notif-1", "read_at": old_time, "workspace_id": "ws-1"}]
        svc = MockSupabaseClient(outbox_rows=outbox_rows, notif_rows=notif_rows)
        
        res = run_retention_prune_cycle(svc, workspace_id="ws-1")
        self.assertEqual(res["total_deleted"], 2)
        self.assertIn("outbox", res)
        self.assertIn("notifications", res)


if __name__ == "__main__":
    unittest.main()

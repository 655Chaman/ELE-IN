"""
Tests for backend/scripts/apply_migrations.py

Run from the scripts directory:
    python -m pytest test_apply_migrations.py -v
  or
    python test_apply_migrations.py
"""
import io
import unittest
from unittest.mock import MagicMock, PropertyMock, call, mock_open, patch

import apply_migrations


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tracking_inserts(mock_cur):
    """Return the list of (filename,) tuples passed to schema_migrations INSERTs."""
    results = []
    for c in mock_cur.execute.call_args_list:
        args, kwargs = c
        if args and "INSERT INTO schema_migrations" in args[0]:
            # args[1] is the params tuple, e.g. ("001_test.sql",)
            if len(args) > 1 and args[1]:
                results.append(args[1])
    return results


def _sql_executed(mock_cur):
    """Return list of first-positional-arg strings for every cur.execute() call."""
    return [c[0][0] for c in mock_cur.execute.call_args_list if c[0]]


# ─────────────────────────────────────────────────────────────────────────────
# Base test fixture
# ─────────────────────────────────────────────────────────────────────────────

class MigrationTestBase(unittest.TestCase):
    """
    Sets up a fully mocked psycopg2 connection/cursor and captures stdout.
    Tests should set ORDERED_MIGRATIONS to a small list before calling
    apply_migrations.apply_migrations().
    """

    def setUp(self):
        self.mock_conn = MagicMock()
        self.mock_cur = MagicMock()

        # cursor() used as context manager → return the same mock_cur
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cur
        self.mock_conn.autocommit = False

        # Default: no migrations already applied
        def _default_execute(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = []
        self.mock_cur.execute.side_effect = _default_execute

        # Capture stdout
        self._stdout_patch = patch("sys.stdout", new_callable=io.StringIO)
        self.mock_stdout = self._stdout_patch.start()

        # Inject a fake psycopg2 into sys.modules
        self._psycopg2_patch = patch.dict("sys.modules", {"psycopg2": MagicMock()})
        self._psycopg2_patch.start()
        import psycopg2
        psycopg2.connect.return_value = self.mock_conn

        # Always return a fake DATABASE_URL so we take the psycopg2 path
        self._getenv_patch = patch("apply_migrations.os.getenv")
        self.mock_getenv = self._getenv_patch.start()
        self.mock_getenv.side_effect = (
            lambda key: "postgres://fake" if key == "DATABASE_URL" else None
        )

        # Override ORDERED_MIGRATIONS so tests don't touch real files
        apply_migrations.ORDERED_MIGRATIONS = ["001_test.sql"]

    def tearDown(self):
        self._stdout_patch.stop()
        self._psycopg2_patch.stop()
        self._getenv_patch.stop()

    def output(self):
        return self.mock_stdout.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Parser tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGetExecutionMode(unittest.TestCase):

    def test_empty_sql_is_transactional(self):
        self.assertEqual(apply_migrations.get_execution_mode(""), "TRANSACTIONAL")

    def test_blank_lines_only_is_transactional(self):
        self.assertEqual(apply_migrations.get_execution_mode("\n\n\n"), "TRANSACTIONAL")

    def test_ordinary_sql_is_transactional(self):
        self.assertEqual(
            apply_migrations.get_execution_mode("CREATE TABLE foo (id SERIAL);"),
            "TRANSACTIONAL",
        )

    def test_ordinary_comment_then_sql_is_transactional(self):
        sql = "-- This is an ordinary comment\nCREATE TABLE foo (id SERIAL);"
        self.assertEqual(apply_migrations.get_execution_mode(sql), "TRANSACTIONAL")

    def test_explicit_transactional_directive(self):
        sql = "-- EXECUTION: TRANSACTIONAL\nCREATE TABLE foo (id SERIAL);"
        self.assertEqual(apply_migrations.get_execution_mode(sql), "TRANSACTIONAL")

    def test_explicit_non_transactional_directive(self):
        sql = "-- EXECUTION: NON-TRANSACTIONAL\nCREATE INDEX CONCURRENTLY idx ON foo(id);"
        self.assertEqual(apply_migrations.get_execution_mode(sql), "NON-TRANSACTIONAL")

    def test_directive_with_leading_blank_lines_accepted(self):
        sql = "\n\n-- EXECUTION: NON-TRANSACTIONAL\nCREATE INDEX CONCURRENTLY idx ON foo(id);"
        self.assertEqual(apply_migrations.get_execution_mode(sql), "NON-TRANSACTIONAL")

    def test_unknown_directive_value_raises(self):
        with self.assertRaises(ValueError):
            apply_migrations.get_execution_mode("-- EXECUTION: ASYNC\nSELECT 1;")

    def test_malformed_directive_empty_value_raises(self):
        with self.assertRaises(ValueError):
            apply_migrations.get_execution_mode("-- EXECUTION: \nSELECT 1;")

    def test_malformed_directive_prefix_only_raises(self):
        with self.assertRaises(ValueError):
            apply_migrations.get_execution_mode("-- EXECUTION:\nSELECT 1;")

    def test_directive_after_sql_raises(self):
        sql = "CREATE TABLE foo (id SERIAL);\n-- EXECUTION: NON-TRANSACTIONAL"
        with self.assertRaises(ValueError):
            apply_migrations.get_execution_mode(sql)

    def test_directive_after_ordinary_comment_raises(self):
        sql = "-- some comment\n-- EXECUTION: NON-TRANSACTIONAL\nCREATE TABLE foo;"
        with self.assertRaises(ValueError):
            apply_migrations.get_execution_mode(sql)

    def test_duplicate_directive_raises(self):
        sql = (
            "-- EXECUTION: TRANSACTIONAL\n"
            "CREATE TABLE foo (id SERIAL);\n"
            "-- EXECUTION: NON-TRANSACTIONAL\n"
        )
        with self.assertRaises(ValueError):
            apply_migrations.get_execution_mode(sql)

    def test_two_identical_directives_raises(self):
        sql = "-- EXECUTION: TRANSACTIONAL\n-- EXECUTION: TRANSACTIONAL\n"
        with self.assertRaises(ValueError):
            apply_migrations.get_execution_mode(sql)

    def test_valid_directive_then_unrelated_comments_accepted(self):
        sql = (
            "-- EXECUTION: NON-TRANSACTIONAL\n"
            "-- This comment is fine\n"
            "CREATE INDEX CONCURRENTLY idx ON foo(id);\n"
        )
        self.assertEqual(apply_migrations.get_execution_mode(sql), "NON-TRANSACTIONAL")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Transactional execution tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTransactionalExecution(MigrationTestBase):

    @patch("builtins.open", new_callable=mock_open, read_data="CREATE TABLE test;")
    def test_success_executes_sql_tracks_and_commits(self, _mock_file):
        apply_migrations.apply_migrations(dry_run=False)

        executed = _sql_executed(self.mock_cur)
        self.assertIn("CREATE TABLE test;", executed)

        inserts = _tracking_inserts(self.mock_cur)
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][0], "001_test.sql")

        self.assertTrue(self.mock_conn.commit.called)

    @patch("builtins.open", new_callable=mock_open, read_data="CREATE TABLE test;")
    def test_ddl_failure_rolls_back_and_does_not_track(self, _mock_file):
        def side_effect(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = []
            elif "CREATE TABLE test" in query:
                raise Exception("Simulated DDL failure")
        self.mock_cur.execute.side_effect = side_effect

        apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        self.assertIn("Phase: SQL execution or tracking INSERT", out)
        self.assertTrue(self.mock_conn.rollback.called)
        self.assertEqual(len(_tracking_inserts(self.mock_cur)), 0)

    @patch("builtins.open", new_callable=mock_open, read_data="CREATE TABLE test;")
    def test_tracking_failure_rolls_back_and_halts(self, _mock_file):
        def side_effect(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = []
            elif "INSERT INTO schema_migrations" in query:
                raise Exception("Simulated tracking failure")
        self.mock_cur.execute.side_effect = side_effect

        apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        self.assertIn("Phase: SQL execution or tracking INSERT", out)
        self.assertTrue(self.mock_conn.rollback.called)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Non-transactional execution tests
# ─────────────────────────────────────────────────────────────────────────────

NON_TX_SQL = "-- EXECUTION: NON-TRANSACTIONAL\nCREATE INDEX CONCURRENTLY idx ON foo(id);"


class TestNonTransactionalSuccess(MigrationTestBase):
    """
    Verify the exact autocommit state-machine transition:
      commit (prep)
      → autocommit=True
      → DDL execute
      → autocommit=False   (try/finally)
      → tracking INSERT
      → commit
    """

    @patch("builtins.open", new_callable=mock_open, read_data=NON_TX_SQL)
    def test_autocommit_transition_order_and_success(self, _mock_file):
        # Use a list to record the order in which autocommit is set
        autocommit_set_sequence = []

        # PropertyMock lets us intercept setter calls
        type(self.mock_conn).autocommit = PropertyMock(
            side_effect=lambda self_inner=None: None  # getter returns None (truthy enough)
        )
        # We patch at the instance level instead so we can record both get and set
        original_autocommit_values = []

        real_sets = []

        def autocommit_setter(val):
            real_sets.append(val)

        # Replace the property with a descriptor that records sets
        type(self.mock_conn).autocommit = property(
            fget=lambda s: real_sets[-1] if real_sets else False,
            fset=lambda s, v: real_sets.append(v),
        )

        apply_migrations.apply_migrations(dry_run=False)

        # Verify autocommit was set True, then False (in that order)
        self.assertIn(True, real_sets, "autocommit was never set True")
        self.assertIn(False, real_sets, "autocommit was never restored to False")

        true_idx = next(i for i, v in enumerate(real_sets) if v is True)
        # The first False that appears AFTER the True is the restoration
        restore_false_idx = next(
            (i for i, v in enumerate(real_sets) if i > true_idx and v is False),
            None,
        )
        self.assertIsNotNone(
            restore_false_idx,
            "autocommit=False was not set after autocommit=True",
        )

        # Tracking INSERT must exist
        inserts = _tracking_inserts(self.mock_cur)
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][0], "001_test.sql")

        out = self.output()
        self.assertIn("Successfully applied 001_test.sql (NON-TRANSACTIONAL)", out)


class TestNonTransactionalDDLFailure(MigrationTestBase):

    @patch("builtins.open", new_callable=mock_open, read_data=NON_TX_SQL)
    def test_ddl_failure_restores_autocommit_and_does_not_track(self, _mock_file):
        real_sets = []

        type(self.mock_conn).autocommit = property(
            fget=lambda s: real_sets[-1] if real_sets else False,
            fset=lambda s, v: real_sets.append(v),
        )

        def side_effect(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = []
            elif "CREATE INDEX" in query:
                raise Exception("Simulated concurrent index failure")
        self.mock_cur.execute.side_effect = side_effect

        apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        self.assertIn("Execution Mode: NON-TRANSACTIONAL", out)
        self.assertIn("Phase: SQL execution", out)
        self.assertIn("explicitly check for an INVALID index", out)

        # autocommit must have been restored to False after the DDL failure
        # Find the True, then confirm a False follows it
        true_idx = next((i for i, v in enumerate(real_sets) if v is True), None)
        self.assertIsNotNone(true_idx, "autocommit=True was never set")
        restore_idx = next(
            (i for i, v in enumerate(real_sets) if i > true_idx and v is False),
            None,
        )
        self.assertIsNotNone(restore_idx, "autocommit=False was not restored after DDL failure")

        # No tracking INSERT
        self.assertEqual(len(_tracking_inserts(self.mock_cur)), 0)

    @patch("builtins.open", new_callable=mock_open, read_data=NON_TX_SQL)
    def test_ddl_failure_halts_pipeline(self, _mock_file):
        """No subsequent migration must run after non-transactional DDL failure."""
        apply_migrations.ORDERED_MIGRATIONS = ["001_F1.sql", "002_F2.sql"]

        def open_side_effect(filename, mode="r"):
            return mock_open(read_data=NON_TX_SQL).return_value

        def execute_side_effect(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = []
            elif "CREATE INDEX" in query:
                raise Exception("Simulated failure on every concurrent index")

        self.mock_cur.execute.side_effect = execute_side_effect

        with patch("builtins.open", side_effect=open_side_effect):
            apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        # 002_F2.sql must never appear in output as "Successfully applied"
        self.assertNotIn("Successfully applied 002_F2.sql", out)
        # And the error message must be for 001_F1.sql only
        self.assertIn("ERROR: Failed to apply 001_F1.sql", out)


class TestNonTransactionalTrackingFailure(MigrationTestBase):

    @patch("builtins.open", new_callable=mock_open, read_data=NON_TX_SQL)
    def test_tracking_failure_emits_critical_error_and_halts(self, _mock_file):
        def side_effect(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = []
            elif "INSERT INTO schema_migrations" in query:
                raise Exception("Simulated tracking failure")
        self.mock_cur.execute.side_effect = side_effect

        apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        self.assertIn("CRITICAL ERROR", out)
        self.assertIn("Phase: tracking INSERT", out)
        # Must explicitly acknowledge DDL is already committed
        self.assertIn(
            "Migration SQL succeeded and is committed, but schema_migrations tracking failed",
            out,
        )
        # The rollback is on the tracking transaction, NOT on the DDL
        self.assertTrue(self.mock_conn.rollback.called)


# ─────────────────────────────────────────────────────────────────────────────
# 4. F1 / F2 sequencing
# ─────────────────────────────────────────────────────────────────────────────

class TestF1F2Sequencing(MigrationTestBase):

    def test_f1_succeeds_f2_fails_f1_tracked_f2_not_tracked(self):
        apply_migrations.ORDERED_MIGRATIONS = ["001_F1.sql", "002_F2.sql"]

        def open_side_effect(filename, mode="r"):
            if "F1" in filename:
                return mock_open(
                    read_data="-- EXECUTION: NON-TRANSACTIONAL\nCREATE INDEX F1;"
                ).return_value
            elif "F2" in filename:
                return mock_open(
                    read_data="-- EXECUTION: NON-TRANSACTIONAL\nCREATE INDEX F2;"
                ).return_value
            # tracking table creation / schema_migrations files
            return mock_open(read_data="").return_value

        def execute_side_effect(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = []
            elif "CREATE INDEX F2" in query:
                raise Exception("Concurrent index failure in F2")
            # F1 DDL, tracking INSERTs, CREATE TABLE, etc. succeed silently

        self.mock_cur.execute.side_effect = execute_side_effect

        with patch("builtins.open", side_effect=open_side_effect):
            apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        self.assertIn("Successfully applied 001_F1.sql (NON-TRANSACTIONAL)", out)
        self.assertIn("ERROR: Failed to apply 002_F2.sql", out)
        self.assertNotIn("Successfully applied 002_F2.sql", out)

        # Only F1 must be tracked
        inserts = _tracking_inserts(self.mock_cur)
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][0], "001_F1.sql")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Already-applied migration
# ─────────────────────────────────────────────────────────────────────────────

class TestAlreadyApplied(MigrationTestBase):

    @patch("builtins.open", new_callable=mock_open, read_data="CREATE TABLE test;")
    def test_already_applied_skips_sql_execution(self, _mock_file):
        def side_effect(query, params=None):
            if query.strip().startswith("SELECT filename"):
                self.mock_cur.fetchall.return_value = [("001_test.sql",)]
        self.mock_cur.execute.side_effect = side_effect

        apply_migrations.apply_migrations(dry_run=False)

        executed = _sql_executed(self.mock_cur)
        self.assertNotIn("CREATE TABLE test;", executed)
        self.assertEqual(len(_tracking_inserts(self.mock_cur)), 0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Parser-error path in full runner (directive caught before SQL)
# ─────────────────────────────────────────────────────────────────────────────

class TestParserErrorInRunner(MigrationTestBase):

    @patch("builtins.open", new_callable=mock_open, read_data="-- EXECUTION: INVALID\nSQL;")
    def test_malformed_directive_halts_before_executing_sql(self, _mock_file):
        apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        self.assertIn("Phase: Parser", out)
        self.assertIn("Unknown or malformed execution directive", out)

        # SQL must NOT have been executed
        executed = _sql_executed(self.mock_cur)
        self.assertNotIn("SQL;", executed)

    @patch("builtins.open", new_callable=mock_open,
           read_data="CREATE TABLE x;\n-- EXECUTION: NON-TRANSACTIONAL")
    def test_directive_after_sql_halts_before_executing_any_migration_sql(self, _mock_file):
        apply_migrations.apply_migrations(dry_run=False)

        out = self.output()
        self.assertIn("Phase: Parser", out)
        executed = _sql_executed(self.mock_cur)
        self.assertNotIn("CREATE TABLE x;", executed)


if __name__ == "__main__":
    unittest.main()

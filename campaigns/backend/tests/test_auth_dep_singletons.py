import os
import unittest
import asyncio
import threading
from unittest.mock import MagicMock, patch, AsyncMock

from core.backend.api.auth_dep import (
    get_service_client,
    get_async_service_client,
    reset_client_singletons,
)


class TestAuthDepSingletonsAndConcurrency(unittest.TestCase):
    """
    Three-Layer Paranoia Framework Test Suite for Supabase Client Singletons:
    - Layer 0: Core mechanics of singleton reuse for sync and async clients.
    - Layer 1: Concurrency races (threading lock, async single-flight lock), loop recycling, and network drop recovery.
    - Layer 2: Test isolation, mock containment, and environment variable dynamic updates.
    """

    def setUp(self):
        # Ensure clean state before each test
        reset_client_singletons()

    def tearDown(self):
        # Ensure clean state after each test to prevent cross-test leakage
        reset_client_singletons()

    # =========================================================================
    # Layer 0: Foundational Mechanics (Singleton Reuse)
    # =========================================================================

    def test_layer0_get_service_client_reuses_singleton(self):
        """
        Verify that consecutive invocations of get_service_client() return the exact
        same Client instance, preventing duplicate connection pools and SSL contexts.
        """
        mock_client = MagicMock(name="MockSyncClient")
        with patch("core.backend.api.auth_dep.create_client", return_value=mock_client) as mock_create:
            c1 = get_service_client()
            c2 = get_service_client()
            c3 = get_service_client()

            self.assertIs(c1, mock_client)
            self.assertIs(c1, c2)
            self.assertIs(c2, c3)
            # create_client must only be called once
            self.assertEqual(mock_create.call_count, 1)

    def test_layer0_get_async_service_client_reuses_singleton(self):
        """
        Verify that consecutive invocations of get_async_service_client() return the exact
        same AsyncClient instance within the event loop.
        """
        mock_async_client = MagicMock(name="MockAsyncClient")

        async def _test():
            with patch("core.backend.api.auth_dep.create_async_client", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = mock_async_client
                c1 = await get_async_service_client()
                c2 = await get_async_service_client()
                c3 = await get_async_service_client()

                self.assertIs(c1, mock_async_client)
                self.assertIs(c1, c2)
                self.assertIs(c2, c3)
                self.assertEqual(mock_create.call_count, 1)

        asyncio.run(_test())

    # =========================================================================
    # Layer 1: Environmental Failures & High Concurrency (Races & Recovery)
    # =========================================================================

    def test_layer1_concurrent_threads_race_safety(self):
        """
        Race condition test: 25 concurrent threads calling get_service_client()
        simultaneously. Threading lock must ensure create_client is called exactly once.
        """
        mock_client = MagicMock(name="ThreadSafeClient")
        clients = []
        barrier = threading.Barrier(25)

        def worker():
            barrier.wait()  # Align all threads to start at the exact same microsecond
            client = get_service_client()
            clients.append(client)

        with patch("core.backend.api.auth_dep.create_client", return_value=mock_client) as mock_create:
            threads = [threading.Thread(target=worker) for _ in range(25)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(len(clients), 25)
            self.assertEqual(len(set(id(c) for c in clients)), 1)
            self.assertEqual(mock_create.call_count, 1)

    def test_layer1_async_single_flight_concurrency(self):
        """
        Single-flight test: 25 concurrent coroutines calling get_async_service_client()
        concurrently with asyncio.gather. The async lock must ensure create_async_client
        is called exactly once.
        """
        mock_async_client = MagicMock(name="AsyncSingleFlightClient")

        async def _test():
            with patch("core.backend.api.auth_dep.create_async_client", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = mock_async_client

                # Launch 25 coroutines concurrently
                tasks = [get_async_service_client() for _ in range(25)]
                results = await asyncio.gather(*tasks)

                self.assertEqual(len(results), 25)
                self.assertEqual(len(set(id(c) for c in results)), 1)
                self.assertEqual(mock_create.call_count, 1)

        asyncio.run(_test())

    def test_layer1_connection_drop_resilience_via_reset(self):
        """
        Verify that reset_client_singletons() enables connection recovery:
        after a simulated network fault, calling reset_client_singletons() clears
        the stale client and allows creation of a fresh singleton on next access.
        """
        mock_client_old = MagicMock(name="StaleClient")
        mock_client_new = MagicMock(name="FreshClient")

        with patch("core.backend.api.auth_dep.create_client", side_effect=[mock_client_old, mock_client_new]) as mock_create:
            c1 = get_service_client()
            self.assertIs(c1, mock_client_old)

            # Simulate network fault trigger -> caller resets singletons
            reset_client_singletons()

            c2 = get_service_client()
            self.assertIs(c2, mock_client_new)
            self.assertIsNot(c1, c2)
            self.assertEqual(mock_create.call_count, 2)

    def test_layer1_async_event_loop_recycling_resilience(self):
        """
        Environmental resilience test: If an event loop closes and a subsequent
        asynchronous call runs in a newly created event loop, get_async_service_client()
        must cleanly detect that the previous loop is closed and instantiate a fresh client
        without throwing 'RuntimeError: Event loop is closed' or 'Future attached to different loop'.
        """
        mock_client_loop1 = MagicMock(name="ClientLoop1")
        mock_client_loop2 = MagicMock(name="ClientLoop2")

        with patch("core.backend.api.auth_dep.create_async_client", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [mock_client_loop1, mock_client_loop2]

            # Run in first loop
            c1 = asyncio.run(get_async_service_client())
            self.assertIs(c1, mock_client_loop1)

            # Run in second, separate loop (first loop is closed by asyncio.run)
            c2 = asyncio.run(get_async_service_client())
            self.assertIs(c2, mock_client_loop2)
            self.assertIsNot(c1, c2)
            self.assertEqual(mock_create.call_count, 2)

    # =========================================================================
    # Layer 2: Human Paranoia & Test Isolation
    # =========================================================================

    def test_layer2_environment_variable_override_after_reset(self):
        """
        Verify that unit tests or operators modifying environment variables (SUPABASE_URL,
        SUPABASE_SERVICE_KEY) can call reset_client_singletons() and have the new values
        immediately respected on the next get_service_client() invocation.
        """
        with patch.dict(os.environ, {"SUPABASE_URL": "https://first-test.supabase.co", "SUPABASE_SERVICE_KEY": "key-1"}):
            with patch("core.backend.api.auth_dep.create_client") as mock_create:
                get_service_client()
                mock_create.assert_called_with("https://first-test.supabase.co", "key-1")

        # Now change environment variables
        with patch.dict(os.environ, {"SUPABASE_URL": "https://second-test.supabase.co", "SUPABASE_SERVICE_KEY": "key-2"}):
            reset_client_singletons()
            with patch("core.backend.api.auth_dep.create_client") as mock_create:
                get_service_client()
                mock_create.assert_called_with("https://second-test.supabase.co", "key-2")


if __name__ == "__main__":
    unittest.main()

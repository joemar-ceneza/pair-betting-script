"""
Tests for riding out a short LEO outage at the start of a run (no browser needed).
Run from the project folder:  python -m unittest discover tests
"""

import os
import sys
import logging
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import account_search
import leo_session

_CREDENTIALS = ("user", "secret")
_OUTAGE = RuntimeError("HTTP Error 503. The service is unavailable.")


class FirstLoginTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        patches = [
            mock.patch.object(config, "RELOGIN_RETRY_DELAY", 0),
            mock.patch.object(leo_session, "save_error_screenshot"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self) -> None:
        logging.disable(logging.NOTSET)

    def test_short_outage_is_ridden_out(self) -> None:
        with mock.patch.object(leo_session, "login", side_effect=[_OUTAGE, _OUTAGE, None]) as login:
            leo_session.first_login(mock.Mock(), _CREDENTIALS)
        self.assertEqual(login.call_count, 3)
        self.assertEqual(leo_session.save_error_screenshot.call_count, 2)

    def test_long_outage_still_fails_loudly(self) -> None:
        with mock.patch.object(leo_session, "login", side_effect=_OUTAGE) as login:
            with self.assertRaises(RuntimeError):
                leo_session.first_login(mock.Mock(), _CREDENTIALS)
        self.assertEqual(login.call_count, config.RETRY_ATTEMPTS)


class SearchAttemptTests(unittest.TestCase):
    def test_every_attempt_logs_in_fresh_and_screenshots_on_failure(self) -> None:
        with (
            mock.patch.object(leo_session, "login") as login,
            mock.patch.object(leo_session, "pause"),
            mock.patch.object(leo_session, "save_error_screenshot") as screenshot,
            mock.patch.object(account_search, "_open_advanced_search", side_effect=_OUTAGE),
        ):
            with self.assertRaises(RuntimeError):
                account_search._search_accounts(mock.Mock(), _CREDENTIALS, date(2026, 11, 24), "VND")
        login.assert_called_once()
        screenshot.assert_called_once()


if __name__ == "__main__":
    unittest.main()

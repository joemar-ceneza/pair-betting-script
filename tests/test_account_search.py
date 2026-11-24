"""
Tests for reading the Advanced Search (MKT) results table in account_search.py, using made-up rows.
Run from the project folder:  python -m unittest discover tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import account_search

_HEADER = [
    "#",
    "ACCOUNT ID",
    "FIRST NAME",
    "SURNAME",
    "LOGIN NAME",
    "CREATED DATE",
    "LAST LOGIN IP",
    "CURRENCY",
    "SERVICE PROVIDER",
    "DEPOSIT STATUS",
    "INITIAL DEPOSIT DATE",
    "PROMOTION CODE",
    "PROMOTION STATUS",
]


def _row(number: int, account_id: str, provider: str = "PayA", promo: str = "", promo_status: str = "") -> list[str]:
    """One result row laid out like LEO's table (names and IPs are fake)."""
    return [
        str(number),
        account_id,
        "Test",
        "User",
        f"login{number}",
        "11/23/2026 9:09:29 PM",
        "10.0.0.1",
        "TB",
        provider,
        "Deposited",
        "11/23/2026 9:12:01 PM",
        promo,
        promo_status,
    ]


def _find(rows: list[list[str]]) -> tuple[list[dict], int]:
    """Parse and clean rows the same way run_account_search does."""
    return account_search._clean_accounts(account_search._parse_result_rows(rows))


class ParseTests(unittest.TestCase):
    def test_columns_are_read_by_header_name(self) -> None:
        accounts, _ = _find([_HEADER, _row(1, "2124529514", promo="MAX125", promo_status="Activated")])
        self.assertEqual(
            accounts[0],
            {
                "account_id": "2124529514",
                "created_date": "11/23/2026 9:09:29 PM",
                "currency": "TB",
                "deposit_status": "Deposited",
                "promotion_code": "MAX125",
                "promotion_status": "Activated",
            },
        )

    def test_column_order_does_not_matter(self) -> None:
        rows = [["CURRENCY", "ACCOUNT ID"], ["RM", "2114529471"]]
        accounts, _ = _find(rows)
        self.assertEqual(accounts[0]["account_id"], "2114529471")
        self.assertEqual(accounts[0]["currency"], "RM")

    def test_missing_or_empty_columns_become_dash(self) -> None:
        accounts, _ = _find([["ACCOUNT ID", "PROMOTION CODE"], ["2114529471", ""]])
        self.assertEqual(accounts[0]["promotion_code"], "-")
        self.assertEqual(accounts[0]["created_date"], "-")

    def test_table_without_account_id_fails_loudly(self) -> None:
        with self.assertRaises(ValueError):
            account_search._parse_result_rows([["FIRST NAME", "SURNAME"], ["a", "b"]])

    def test_no_table_gives_no_accounts(self) -> None:
        self.assertEqual(_find([]), ([], 0))

    def test_header_only_gives_no_accounts(self) -> None:
        self.assertEqual(_find([_HEADER]), ([], 0))


class CleanTests(unittest.TestCase):
    def test_account_repeated_per_service_provider_is_kept_once(self) -> None:
        rows = [_HEADER, _row(1, "2104499117", "StarPay"), _row(2, "2104499117", "VtPay"), _row(3, "2144521510")]
        accounts, invalid = _find(rows)
        self.assertEqual([a["account_id"] for a in accounts], ["2104499117", "2144521510"])
        self.assertEqual(invalid, 0)

    def test_invalid_account_ids_are_skipped_and_counted(self) -> None:
        rows = [_HEADER, _row(1, "2104499117"), _row(2, "bad id!"), _row(3, "")]
        accounts, invalid = _find(rows)
        self.assertEqual([a["account_id"] for a in accounts], ["2104499117"])
        self.assertEqual(invalid, 2)

    def test_original_order_is_kept(self) -> None:
        rows = [_HEADER, _row(1, "3"), _row(2, "1"), _row(3, "2")]
        accounts, _ = _find(rows)
        self.assertEqual([a["account_id"] for a in accounts], ["3", "1", "2"])


class CreatedRangeTests(unittest.TestCase):
    def test_range_is_day_before_report_date_to_report_date(self) -> None:
        from datetime import date

        self.assertEqual(account_search._created_range(date(2026, 11, 24)), ("11/23/2026", "11/24/2026"))
        self.assertEqual(account_search._created_range(date(2026, 12, 1)), ("11/30/2026", "12/01/2026"))


if __name__ == "__main__":
    unittest.main()

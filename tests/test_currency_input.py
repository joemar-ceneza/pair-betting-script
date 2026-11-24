"""
Tests for reading the currency filter (prompt / --currency) in main.py.
Run from the project folder:  python -m unittest discover tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import main


class NormalizeCurrencyTests(unittest.TestCase):
    def test_codes_are_case_insensitive(self) -> None:
        self.assertEqual(main._normalize_currency("vnd"), "VND")
        self.assertEqual(main._normalize_currency(" THB "), "THB")

    def test_leo_display_labels_map_to_codes(self) -> None:
        self.assertEqual(main._normalize_currency("TB"), "THB")
        self.assertEqual(main._normalize_currency("rm"), "MYR")
        self.assertEqual(main._normalize_currency("Pp"), "IDR")

    def test_empty_means_all_currencies(self) -> None:
        self.assertEqual(main._normalize_currency(""), config.MKT_ALL_CURRENCIES)

    def test_unknown_currency_is_rejected(self) -> None:
        self.assertIsNone(main._normalize_currency("XYZ"))


class CollectCurrencyTests(unittest.TestCase):
    def test_flag_wins_even_in_auto_mode(self) -> None:
        self.assertEqual(main._collect_currency("vnd", auto=True), "VND")

    def test_auto_without_flag_means_all(self) -> None:
        self.assertEqual(main._collect_currency(None, auto=True), config.MKT_ALL_CURRENCIES)

    def test_bad_flag_fails_loudly(self) -> None:
        with self.assertRaises(ValueError):
            main._collect_currency("XYZ", auto=True)


if __name__ == "__main__":
    unittest.main()

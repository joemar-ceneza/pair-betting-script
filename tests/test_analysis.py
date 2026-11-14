"""
Tests for the pair-betting detection rules in analysis.py, using made-up bets.
Run from the project folder:  python -m unittest discover tests
"""

import os
import sys
import logging
import unittest
from datetime import datetime, timedelta
from itertools import count

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analysis

_BASE_TIME = datetime(2026, 11, 13, 20, 0, 0)
_ROUND_GAP_SECONDS = 60
_REF_NUMBERS = count(1)


def _bet(username: str, round_no: int, winlost: float, stake: float = 100.0, game: str = "Baccarat B1") -> dict:
    """One settled bet in round round_no (rounds are 60s apart, bets placed 20s before settling)."""
    settle_time = _BASE_TIME + timedelta(seconds=round_no * _ROUND_GAP_SECONDS)
    return {
        "username": username,
        "ref_no": f"R{next(_REF_NUMBERS)}",
        "bet_time": settle_time - timedelta(seconds=20),
        "settle_time": settle_time,
        "game": game,
        "stake": stake,
        "turnover": stake,
        "winlost": winlost,
        "status": "WON" if winlost > 0 else "LOSE" if winlost < 0 else "DRAW",
        "inferred_side": "-",
        "ip": "-",
        "product_id": "",
    }


def _player(username: str, currency: str = "VND", ip: str = "-") -> dict:
    """Minimal player record as the scraper returns it."""
    return {"username": username, "currency": currency, "last_login_ip": ip}


def _opposite_rounds(winners: str) -> list[dict]:
    """Bets for alice/bob on opposite sides; winners is e.g. 'abab' (who wins each round)."""
    bets = []
    for round_no, winner in enumerate(winners):
        bets.append(_bet("alice", round_no, 100.0 if winner == "a" else -100.0))
        bets.append(_bet("bob", round_no, 100.0 if winner == "b" else -100.0))
    return bets


def _only_pair(result: dict) -> dict:
    """Return the single pair summary in an analysis result."""
    assert len(result["pairs"]) == 1, result["pairs"]
    return result["pairs"][0]


class PatternTests(unittest.TestCase):
    def test_swapping_wins_is_high_risk_hedge(self) -> None:
        pair = _only_pair(analysis.run_analysis([_player("alice"), _player("bob")], _opposite_rounds("abab")))
        self.assertEqual(pair["risk"], "HIGH")
        self.assertEqual(pair["pattern"], "HEDGE")
        self.assertEqual(pair["opposite_rounds"], 4)
        self.assertIn("hedged net", pair["signals"])
        self.assertIn("similar stakes", pair["signals"])
        self.assertNotIn("one-way flow", pair["signals"])

    def test_one_account_always_losing_is_chip_dump(self) -> None:
        pair = _only_pair(analysis.run_analysis([_player("alice"), _player("bob")], _opposite_rounds("aaaa")))
        self.assertEqual(pair["pattern"], "CHIP DUMP")
        self.assertEqual(pair["flow_direction"], "bob -> alice")
        self.assertEqual(pair["flow_amount"], 400.0)
        self.assertIn("one-way flow", pair["signals"])

    def test_both_winning_is_conflict_and_not_flagged(self) -> None:
        bets = [_bet(user, round_no, 100.0) for round_no in range(4) for user in ("alice", "bob")]
        pair = _only_pair(analysis.run_analysis([_player("alice"), _player("bob")], bets))
        self.assertEqual(pair["conflict_rounds"], 4)
        self.assertEqual(pair["risk"], "NONE")
        self.assertEqual(pair["pattern"], "-")

    def test_both_pushing_counts_as_tie(self) -> None:
        bets = _opposite_rounds("ab") + [_bet("alice", 5, 0.0), _bet("bob", 5, 0.0)]
        pair = _only_pair(analysis.run_analysis([_player("alice"), _player("bob")], bets))
        self.assertEqual(pair["tie_rounds"], 1)
        self.assertEqual(pair["consistency_pct"], 100.0)

    def test_no_shared_rounds_and_no_shared_ip_is_left_out(self) -> None:
        bets = [_bet("alice", 0, 100.0), _bet("bob", 10, -100.0)]
        result = analysis.run_analysis([_player("alice"), _player("bob")], bets)
        self.assertEqual(result["pairs"], [])

    def test_shared_ip_alone_is_low_risk(self) -> None:
        players = [_player("alice", ip="1.2.3.4"), _player("bob", ip="1.2.3.4")]
        pair = _only_pair(analysis.run_analysis(players, []))
        self.assertEqual(pair["risk"], "LOW")
        self.assertEqual(pair["shared_ips"], "1.2.3.4")


class CurrencyTests(unittest.TestCase):
    def test_mixed_currencies_never_add_amounts(self) -> None:
        players = [_player("alice", "VND"), _player("bob", "THB")]
        pair = _only_pair(analysis.run_analysis(players, _opposite_rounds("abab")))
        self.assertEqual(pair["currencies"], "VND/THB")
        self.assertEqual(pair["opposite_turnover"], "-")
        self.assertEqual(pair["opposite_net"], "-")
        self.assertEqual(pair["net_pct"], "-")
        self.assertNotIn("hedged net", pair["signals"])
        self.assertNotIn("similar stakes", pair["signals"])

    def test_mixed_currencies_still_detected_from_rounds(self) -> None:
        players = [_player("alice", "VND"), _player("bob", "THB")]
        pair = _only_pair(analysis.run_analysis(players, _opposite_rounds("abab")))
        self.assertEqual(pair["opposite_rounds"], 4)
        self.assertEqual(pair["risk"], "MEDIUM")  # consistent, but only 'close timing' left as a signal

    def test_unknown_currency_is_not_treated_as_same(self) -> None:
        players = [_player("alice", "-"), _player("bob", "-")]
        pair = _only_pair(analysis.run_analysis(players, _opposite_rounds("abab")))
        self.assertEqual(pair["opposite_net"], "-")


class RoundTests(unittest.TestCase):
    def test_bets_in_same_round_are_merged(self) -> None:
        bets = [_bet("alice", 0, 100.0), _bet("alice", 0, 100.0), _bet("alice", 1, -50.0)]
        rounds = analysis._build_rounds(bets)
        self.assertEqual(len(rounds), 2)
        self.assertEqual(rounds[0]["bet_count"], 2)
        self.assertEqual(rounds[0]["stake"], 200.0)

    def test_different_tables_never_match(self) -> None:
        bets = [_bet("alice", 0, 100.0, game="Baccarat B1"), _bet("bob", 0, -100.0, game="Baccarat B2")]
        result = analysis.run_analysis([_player("alice"), _player("bob")], bets)
        self.assertEqual(result["pairs"], [])

    def test_partner_is_the_closest_round_not_the_earliest(self) -> None:
        def round_at(second: int, ref: str) -> dict:
            return {"game": "Baccarat B1", "settle_time": _BASE_TIME + timedelta(seconds=second), "ref_nos": [ref]}

        index = analysis._build_round_index([round_at(8, "early"), round_at(10, "exact")])
        partner = analysis._find_partner(round_at(10, "mine"), index, used=set())
        self.assertEqual(partner["ref_nos"], ["exact"])


def setUpModule() -> None:
    """Keep analysis report logging out of the test output."""
    logging.disable(logging.CRITICAL)


def tearDownModule() -> None:
    """Restore logging after the tests."""
    logging.disable(logging.NOTSET)


if __name__ == "__main__":
    unittest.main()

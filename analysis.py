import logging
from collections import defaultdict
from itertools import combinations
from typing import Optional

import config
import log_utils

_RISK_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}
_FLAGGED_RISKS = ("HIGH", "MEDIUM", "LOW")


# ======================================================
# ROUND BUILDING (one record per account per round)
# ======================================================
def _start_round(bet: dict) -> dict:
    """Create a round record from the first bet an account placed in it."""
    return {
        "username": bet["username"],
        "game": bet["game"],
        "settle_time": bet["settle_time"],
        "last_settle": bet["settle_time"],
        "first_bet_time": bet["bet_time"],
        "stake": bet["stake"],
        "winlost": bet["winlost"],
        "bet_count": 1,
        "ref_nos": [bet["ref_no"]],
        "sides": {bet["inferred_side"]} - {"-"},
    }


def _add_to_round(round_: dict, bet: dict) -> None:
    """Add another bet from the same account into an existing round."""
    round_["last_settle"] = bet["settle_time"]
    round_["first_bet_time"] = min(round_["first_bet_time"], bet["bet_time"])
    round_["stake"] += bet["stake"]
    round_["winlost"] += bet["winlost"]
    round_["bet_count"] += 1
    round_["ref_nos"].append(bet["ref_no"])
    round_["sides"] |= {bet["inferred_side"]} - {"-"}


def _is_same_round(round_: dict, bet: dict) -> bool:
    """True when a bet belongs to the account's current round on the same table."""
    gap = (bet["settle_time"] - round_["last_settle"]).total_seconds()
    same_place = bet["username"] == round_["username"] and bet["game"] == round_["game"]
    return same_place and gap <= config.SETTLE_TOLERANCE_SECONDS


def _round_result(round_: dict) -> str:
    """WON / LOSE by the account's net result in the round, DRAW when it netted zero."""
    if round_["winlost"] > 0:
        return "WON"
    if round_["winlost"] < 0:
        return "LOSE"
    return "DRAW"


def _build_rounds(bets: list[dict]) -> list[dict]:
    """Merge each account's bets per round (e.g. 2 x 100k on one round = one 200k round)."""
    rounds = []
    for bet in sorted(bets, key=lambda b: (b["username"], b["game"], b["settle_time"])):
        if rounds and _is_same_round(rounds[-1], bet):
            _add_to_round(rounds[-1], bet)
        else:
            rounds.append(_start_round(bet))
    for round_ in rounds:
        round_["result"] = _round_result(round_)
    return rounds


def _group_rounds_by_user(rounds: list[dict]) -> dict[str, list[dict]]:
    """Group round records by username."""
    grouped = defaultdict(list)
    for round_ in rounds:
        grouped[round_["username"]].append(round_)
    return grouped


def _build_round_index(rounds: list[dict]) -> dict[tuple, list[dict]]:
    """Index rounds by (game/table, settle second) for fast lookup."""
    index = defaultdict(list)
    for round_ in rounds:
        index[(round_["game"], int(round_["settle_time"].timestamp()))].append(round_)
    return index


def _collect_user_ips(players: list[dict], bets: list[dict]) -> dict[str, set[str]]:
    """Collect every IP seen per user: last login IP plus all bet IPs."""
    ips = defaultdict(set)
    for player in players:
        if player["last_login_ip"] != "-":
            ips[player["username"]].add(player["last_login_ip"].split()[0])
    for bet in bets:
        if bet["ip"] != "-":
            ips[bet["username"]].add(bet["ip"])
    return ips


# ======================================================
# ROUND MATCHING
# ======================================================
def _find_partner(round_: dict, index: dict, used: set[str]) -> Optional[dict]:
    """Find the other account's unused round on the same table within the tolerance."""
    base_second = int(round_["settle_time"].timestamp())
    tolerance = config.SETTLE_TOLERANCE_SECONDS
    for offset in range(-tolerance, tolerance + 1):
        for candidate in index.get((round_["game"], base_second + offset), []):
            if candidate["ref_nos"][0] not in used:
                return candidate
    return None


def _match_rounds(rounds_a: list[dict], index_b: dict) -> list[tuple[dict, dict]]:
    """Pair each round of user A with at most one same-round record of user B."""
    matches, used = [], set()
    for round_a in rounds_a:
        round_b = _find_partner(round_a, index_b, used)
        if round_b:
            used.add(round_b["ref_nos"][0])
            matches.append((round_a, round_b))
    return matches


# ======================================================
# SCORING
# ======================================================
def _classify_round(round_a: dict, round_b: dict) -> str:
    """OPPOSITE = one won / one lost, TIE = both pushed, CONFLICT = anything else."""
    results = {round_a["result"], round_b["result"]}
    if results == {"WON", "LOSE"}:
        return "OPPOSITE"
    if results == {"DRAW"}:
        return "TIE"
    return "CONFLICT"


def _split_by_type(matches: list[tuple]) -> dict[str, list[tuple]]:
    """Split matched rounds into OPPOSITE / TIE / CONFLICT lists."""
    groups = {"OPPOSITE": [], "TIE": [], "CONFLICT": []}
    for match in matches:
        groups[_classify_round(*match)].append(match)
    return groups


def _is_similar_stake(round_a: dict, round_b: dict) -> bool:
    """True when the smaller round stake is at least STAKE_SIMILARITY_RATIO of the bigger."""
    bigger = max(round_a["stake"], round_b["stake"])
    return bigger > 0 and min(round_a["stake"], round_b["stake"]) / bigger >= config.STAKE_SIMILARITY_RATIO


def _bet_gap_seconds(round_a: dict, round_b: dict) -> float:
    """Seconds between each account's first bet in the round."""
    return abs((round_a["first_bet_time"] - round_b["first_bet_time"]).total_seconds())


def _rate(part: int, whole: int) -> float:
    """Safe part / whole."""
    return part / whole if whole else 0.0


def _measure_hedge(opposite: list[tuple]) -> tuple[float, float, Optional[float]]:
    """Return (combined stake, combined net, |net| as % of stake) for opposite rounds."""
    turnover = sum(a["stake"] + b["stake"] for a, b in opposite)
    net = sum(a["winlost"] + b["winlost"] for a, b in opposite)
    net_pct = abs(net) / turnover * 100 if turnover else None
    return turnover, net, net_pct


def _collect_signals(
    similar_rate: float, timing_rate: float, net_pct: Optional[float], shared_ips: set[str]
) -> list[str]:
    """List the supporting signals present for a pair."""
    signals = []
    if similar_rate >= config.MIN_SIMILAR_STAKE_RATE:
        signals.append("similar stakes")
    if timing_rate >= config.MIN_CLOSE_TIMING_RATE:
        signals.append("close timing")
    if net_pct is not None and net_pct <= config.MAX_HEDGE_NET_PCT:
        signals.append("hedged net")
    if shared_ips:
        signals.append("shared IP")
    return signals


def _rate_risk(opposite_count: int, consistency: float, signals: list[str], has_shared_rounds: bool) -> Optional[str]:
    """HIGH / MEDIUM / LOW / NONE, or None when the pair has nothing in common."""
    is_consistent = opposite_count >= config.MIN_OPPOSITE_ROUNDS and consistency >= config.MIN_CONSISTENCY_RATE
    if is_consistent and len(signals) >= 2:
        return "HIGH"
    if is_consistent:
        return "MEDIUM"
    if "shared IP" in signals or opposite_count >= config.MIN_OPPOSITE_ROUNDS:
        return "LOW"
    if has_shared_rounds:
        return "NONE"
    return None


def _summarize_pair(
    user_a: str, user_b: str, matches: list[tuple], shared_ips: set[str], currencies: tuple[str, str]
) -> dict:
    """Build the summary record for one pair of users."""
    groups = _split_by_type(matches)
    opposite = groups["OPPOSITE"]
    same_currency = currencies[0] == currencies[1]
    similar = [m for m in opposite if _is_similar_stake(*m)] if same_currency else []
    close = [m for m in matches if _bet_gap_seconds(*m) <= config.BET_TIME_WINDOW_SECONDS]
    consistency = _rate(len(opposite) + len(groups["TIE"]), len(matches))
    turnover, net, net_pct = _measure_hedge(opposite)
    signals = _collect_signals(_rate(len(similar), len(opposite)), _rate(len(close), len(matches)), net_pct, shared_ips)
    return {
        "risk": _rate_risk(len(opposite), consistency, signals, bool(matches)),
        "user_a": user_a,
        "user_b": user_b,
        "currencies": currencies[0] if same_currency else f"{currencies[0]}/{currencies[1]}",
        "shared_rounds": len(matches),
        "opposite_rounds": len(opposite),
        "tie_rounds": len(groups["TIE"]),
        "conflict_rounds": len(groups["CONFLICT"]),
        "consistency_pct": round(consistency * 100, 1),
        "similar_stake_rounds": len(similar),
        "close_timing_rounds": len(close),
        "opposite_turnover": round(turnover, 2),
        "opposite_net": round(net, 2),
        "net_pct": round(net_pct, 2) if net_pct is not None else "-",
        "shared_ips": ", ".join(sorted(shared_ips)) or "-",
        "signals": ", ".join(signals) or "-",
    }


# ======================================================
# EVIDENCE
# ======================================================
def _round_columns(round_: dict, suffix: str) -> dict:
    """Return one account's round fields with an _a / _b suffix."""
    return {
        f"bets_{suffix}": round_["bet_count"],
        f"stake_{suffix}": round_["stake"],
        f"winlost_{suffix}": round_["winlost"],
        f"result_{suffix}": round_["result"],
        f"side_{suffix}": "/".join(sorted(round_["sides"])) or "-",
        f"ref_nos_{suffix}": " | ".join(round_["ref_nos"]),
    }


def _build_evidence(summary: dict, matches: list[tuple]) -> list[dict]:
    """List every matched round for a pair as proof rows."""
    rows = []
    for round_a, round_b in matches:
        rows.append(
            {
                "risk": summary["risk"],
                "user_a": round_a["username"],
                "user_b": round_b["username"],
                "game": round_a["game"],
                "settle_time": round_a["settle_time"],
                "round_type": _classify_round(round_a, round_b),
                "bet_gap_seconds": round(_bet_gap_seconds(round_a, round_b), 1),
                **_round_columns(round_a, "a"),
                **_round_columns(round_b, "b"),
                "similar_stake": "Y" if _is_similar_stake(round_a, round_b) else "N",
            }
        )
    return rows


# ======================================================
# REPORTING
# ======================================================
def _log_pair_report(summary: dict) -> None:
    """Log one flagged pair: '=' header, then one aligned line per field."""
    net_pct = f"{summary['net_pct']}%" if summary["net_pct"] != "-" else "-"
    log_utils.log_section(f"{summary['risk']} | {summary['user_a']} <-> {summary['user_b']}")
    log_utils.log_lines(
        [
            log_utils.field("Currency", summary["currencies"]),
            log_utils.field("Shared rounds", summary["shared_rounds"]),
            log_utils.field("Opposite rounds", summary["opposite_rounds"]),
            log_utils.field("Tie rounds", summary["tie_rounds"]),
            log_utils.field("Conflict rounds", summary["conflict_rounds"]),
            log_utils.field("Consistency", f"{summary['consistency_pct']}%"),
            log_utils.field("Similar stakes", summary["similar_stake_rounds"]),
            log_utils.field("Close timing", summary["close_timing_rounds"]),
            log_utils.field("Opposite turnover", f"{summary['opposite_turnover']:,.2f}"),
            log_utils.field("Opposite net", f"{summary['opposite_net']:+,.2f} ({net_pct})"),
            log_utils.field("Shared IPs", summary["shared_ips"]),
            log_utils.field("Signals", summary["signals"]),
        ]
    )


def _log_results(pairs: list[dict], user_count: int) -> None:
    """Log every flagged pair, then the totals."""
    flagged = [pair for pair in pairs if pair["risk"] in _FLAGGED_RISKS]
    for summary in flagged:
        _log_pair_report(summary)
    total_compared = user_count * (user_count - 1) // 2
    logging.info("Flagged pairs: %d of %d compared.", len(flagged), total_compared)
    logging.info("Unflagged pairs with shared rounds (CSV only): %d", len(pairs) - len(flagged))


# ======================================================
# PUBLIC ENTRY POINT
# ======================================================
def run_analysis(players: list[dict], bets: list[dict]) -> dict:
    """Compare every pair of users round by round; return pair summaries plus round evidence."""
    if not bets:
        logging.warning("No bets collected — only shared-IP links can be checked.")

    rounds_by_user = _group_rounds_by_user(_build_rounds(bets))
    round_indexes = {user: _build_round_index(rounds) for user, rounds in rounds_by_user.items()}
    user_ips = _collect_user_ips(players, bets)
    usernames = sorted({p["username"] for p in players})
    currency_by_user = {p["username"]: p["currency"] for p in players}

    pairs, evidence = [], []
    for user_a, user_b in combinations(usernames, 2):
        matches = _match_rounds(rounds_by_user.get(user_a, []), round_indexes.get(user_b, {}))
        currencies = (currency_by_user[user_a], currency_by_user[user_b])
        summary = _summarize_pair(user_a, user_b, matches, user_ips[user_a] & user_ips[user_b], currencies)
        if summary["risk"] is None:
            continue
        pairs.append(summary)
        evidence.extend(_build_evidence(summary, matches))

    pairs.sort(key=lambda s: (_RISK_ORDER[s["risk"]], -s["opposite_rounds"]))
    _log_results(pairs, len(usernames))
    return {"pairs": pairs, "evidence": evidence}

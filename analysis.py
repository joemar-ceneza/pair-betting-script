import logging
from collections import defaultdict
from itertools import combinations
from typing import Optional

import config
import log_utils

_OPPOSITE_STATUSES = {"WON", "LOSE"}
_RISK_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


# ======================================================
# INDEXING
# ======================================================
def _group_bets_by_user(bets: list[dict]) -> dict[str, list[dict]]:
    """Group bet records by username."""
    grouped = defaultdict(list)
    for bet in bets:
        grouped[bet["username"]].append(bet)
    return grouped


def _build_round_index(bets: list[dict]) -> dict[tuple, list[dict]]:
    """Index bets by (game/table, settle second) for fast round lookup."""
    index = defaultdict(list)
    for bet in bets:
        index[(bet["game"], int(bet["settle_time"].timestamp()))].append(bet)
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
def _find_partner(bet: dict, index: dict, used: set[str]) -> Optional[dict]:
    """Find an unused bet on the same table settling within the tolerance."""
    base_second = int(bet["settle_time"].timestamp())
    tolerance = config.SETTLE_TOLERANCE_SECONDS
    for offset in range(-tolerance, tolerance + 1):
        for candidate in index.get((bet["game"], base_second + offset), []):
            if candidate["ref_no"] not in used:
                return candidate
    return None


def _match_rounds(bets_a: list[dict], index_b: dict) -> list[tuple[dict, dict]]:
    """Pair each bet of user A with at most one same-round bet of user B."""
    matches, used = [], set()
    for bet_a in bets_a:
        bet_b = _find_partner(bet_a, index_b, used)
        if bet_b:
            used.add(bet_b["ref_no"])
            matches.append((bet_a, bet_b))
    return matches


# ======================================================
# SCORING
# ======================================================
def _is_opposite(bet_a: dict, bet_b: dict) -> bool:
    """True when one bet WON and the other LOST in the same round."""
    return {bet_a["status"], bet_b["status"]} == _OPPOSITE_STATUSES


def _is_similar_stake(bet_a: dict, bet_b: dict) -> bool:
    """True when the smaller stake is at least STAKE_SIMILARITY_RATIO of the bigger."""
    bigger = max(bet_a["stake"], bet_b["stake"])
    return bigger > 0 and min(bet_a["stake"], bet_b["stake"]) / bigger >= config.STAKE_SIMILARITY_RATIO


def _rate_risk(opposite_count: int, opposite_rate: float, similar_rate: float, has_shared_ip: bool) -> Optional[str]:
    """Return HIGH / MEDIUM / LOW, or None when the pair is not suspicious."""
    is_strong = opposite_count >= config.MIN_OPPOSITE_ROUNDS and opposite_rate >= config.MIN_OPPOSITE_RATE
    if is_strong and (has_shared_ip or similar_rate >= config.MIN_SIMILAR_STAKE_RATE):
        return "HIGH"
    if is_strong:
        return "MEDIUM"
    if has_shared_ip or opposite_count >= config.MIN_OPPOSITE_ROUNDS:
        return "LOW"
    return None


def _summarize_pair(
    user_a: str, user_b: str, matches: list[tuple], shared_ips: set[str], currencies: tuple[str, str]
) -> dict:
    """Build the summary record for one pair of users."""
    same_currency = currencies[0] == currencies[1]
    opposite = [m for m in matches if _is_opposite(*m)]
    similar = [m for m in opposite if _is_similar_stake(*m)] if same_currency else []
    opposite_rate = len(opposite) / len(matches) if matches else 0.0
    similar_rate = len(similar) / len(opposite) if opposite else 0.0
    turnover = sum(a["stake"] + b["stake"] for a, b in opposite)
    net = sum(a["winlost"] + b["winlost"] for a, b in opposite)
    return {
        "risk": _rate_risk(len(opposite), opposite_rate, similar_rate, bool(shared_ips)),
        "user_a": user_a,
        "user_b": user_b,
        "currencies": currencies[0] if same_currency else f"{currencies[0]}/{currencies[1]}",
        "shared_rounds": len(matches),
        "opposite_rounds": len(opposite),
        "opposite_rate_pct": round(opposite_rate * 100, 1),
        "similar_stake_rounds": len(similar),
        "opposite_turnover": round(turnover, 2),
        "opposite_net": round(net, 2),
        "shared_ips": ", ".join(sorted(shared_ips)) or "-",
    }


def _build_evidence(summary: dict, matches: list[tuple]) -> list[dict]:
    """List every matched round for a flagged pair as proof rows."""
    rows = []
    for bet_a, bet_b in matches:
        rows.append(
            {
                "risk": summary["risk"],
                "user_a": bet_a["username"],
                "user_b": bet_b["username"],
                "game": bet_a["game"],
                "settle_time": bet_a["settle_time"],
                "ref_no_a": bet_a["ref_no"],
                "status_a": bet_a["status"],
                "stake_a": bet_a["stake"],
                "winlost_a": bet_a["winlost"],
                "side_a": bet_a["inferred_side"],
                "ref_no_b": bet_b["ref_no"],
                "status_b": bet_b["status"],
                "stake_b": bet_b["stake"],
                "winlost_b": bet_b["winlost"],
                "side_b": bet_b["inferred_side"],
                "opposite": "Y" if _is_opposite(bet_a, bet_b) else "N",
            }
        )
    return rows


# ======================================================
# REPORTING
# ======================================================
def _log_pair_report(summary: dict) -> None:
    """Log one flagged pair: '=' header, then one aligned line per field."""
    log_utils.log_section(f"{summary['risk']} | {summary['user_a']} <-> {summary['user_b']}")
    log_utils.log_lines(
        [
            log_utils.field("Currency", summary["currencies"]),
            log_utils.field("Shared rounds", summary["shared_rounds"]),
            log_utils.field("Opposite rounds", f"{summary['opposite_rounds']} ({summary['opposite_rate_pct']}%)"),
            log_utils.field("Similar stakes", summary["similar_stake_rounds"]),
            log_utils.field("Opposite turnover", f"{summary['opposite_turnover']:,.2f}"),
            log_utils.field("Opposite net", f"{summary['opposite_net']:+,.2f}"),
            log_utils.field("Shared IPs", summary["shared_ips"]),
        ]
    )


# ======================================================
# PUBLIC ENTRY POINT
# ======================================================
def run_analysis(players: list[dict], bets: list[dict]) -> dict:
    """Compare every pair of users and return flagged pairs plus round evidence."""
    if not bets:
        logging.warning("No bets collected — only shared-IP links can be checked.")

    bets_by_user = _group_bets_by_user(bets)
    round_indexes = {user: _build_round_index(user_bets) for user, user_bets in bets_by_user.items()}
    user_ips = _collect_user_ips(players, bets)
    usernames = sorted({p["username"] for p in players})
    currency_by_user = {p["username"]: p["currency"] for p in players}

    pairs, evidence = [], []
    for user_a, user_b in combinations(usernames, 2):
        matches = _match_rounds(bets_by_user.get(user_a, []), round_indexes.get(user_b, {}))
        currencies = (currency_by_user[user_a], currency_by_user[user_b])
        summary = _summarize_pair(user_a, user_b, matches, user_ips[user_a] & user_ips[user_b], currencies)
        if summary["risk"] is None:
            continue
        pairs.append(summary)
        evidence.extend(_build_evidence(summary, matches))

    pairs.sort(key=lambda s: (_RISK_ORDER[s["risk"]], -s["opposite_rounds"]))
    for summary in pairs:
        _log_pair_report(summary)
    total_compared = len(usernames) * (len(usernames) - 1) // 2
    logging.info("Flagged pairs: %d of %d compared.", len(pairs), total_compared)
    return {"pairs": pairs, "evidence": evidence}

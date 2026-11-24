import os
import logging
from datetime import date

import config
import utils

ACCOUNT_COLUMNS = [
    "account_id",
    "created_date",
    "currency",
    "deposit_status",
    "promotion_code",
    "promotion_status",
]
PLAYER_COLUMNS = [
    "username",
    "customer",
    "currency",
    "login_name",
    "contact",
    "remark",
    "vip_level",
    "last_login_ip",
    "last_logged_url",
    "status",
    "cash_balance",
    "promotion_code",
    "promotion_status",
    "turnover",
    "winloss",
    "bet_count",
]
BET_COLUMNS = [
    "username",
    "ref_no",
    "bet_time",
    "settle_time",
    "game",
    "stake",
    "turnover",
    "winlost",
    "status",
    "inferred_side",
    "ip",
    "product_id",
]
PAIR_COLUMNS = [
    "risk",
    "pattern",
    "user_a",
    "user_b",
    "currencies",
    "shared_rounds",
    "opposite_rounds",
    "tie_rounds",
    "conflict_rounds",
    "consistency_pct",
    "similar_stake_rounds",
    "close_timing_rounds",
    "opposite_turnover",
    "opposite_net",
    "net_pct",
    "one_way_rate_pct",
    "flow_direction",
    "flow_amount",
    "shared_ips",
    "promotion_a",
    "promotion_b",
    "signals",
]
EVIDENCE_COLUMNS = [
    "risk",
    "pattern",
    "user_a",
    "user_b",
    "game",
    "settle_time",
    "round_type",
    "bet_gap_seconds",
    "bets_a",
    "stake_a",
    "winlost_a",
    "result_a",
    "side_a",
    "ref_nos_a",
    "bets_b",
    "stake_b",
    "winlost_b",
    "result_b",
    "side_b",
    "ref_nos_b",
    "similar_stake",
]


def _save_report(rows: list[dict], columns: list[str], filename: str, report_date: date) -> str:
    """Write one CSV to data/output/<Month>/<MM-DD-YYYY>/, log it, and return its path."""
    path = os.path.join(utils.build_dated_folder(config.OUTPUT_DIR, report_date), filename)
    utils.write_csv(rows, columns, path)
    logging.info("Saved: %s (%d rows)", filename, len(rows))
    return path


def save_accounts(accounts: list[dict], report_date: date) -> str:
    """Write the Advanced Search (MKT) account list right after the search; return its path."""
    return _save_report(accounts, ACCOUNT_COLUMNS, f"accounts_{report_date.strftime('%Y%m%d')}.csv", report_date)


def save_outputs(scrape_result: dict, analysis_result: dict, report_date: date) -> list[str]:
    """Write the four scrape/analysis CSV reports and return their paths."""
    stamp = report_date.strftime("%Y%m%d")
    reports = [
        (scrape_result["players"], PLAYER_COLUMNS, f"player_info_{stamp}.csv"),
        (scrape_result["bets"], BET_COLUMNS, f"bets_{stamp}.csv"),
        (analysis_result["pairs"], PAIR_COLUMNS, f"pair_betting_{stamp}.csv"),
        (analysis_result["evidence"], EVIDENCE_COLUMNS, f"pair_rounds_{stamp}.csv"),
    ]
    return [_save_report(rows, columns, filename, report_date) for rows, columns, filename in reports]

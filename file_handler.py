import os
import logging
from datetime import date

import config
import utils

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
    "user_a",
    "user_b",
    "currencies",
    "shared_rounds",
    "opposite_rounds",
    "opposite_rate_pct",
    "similar_stake_rounds",
    "opposite_turnover",
    "opposite_net",
    "shared_ips",
]
EVIDENCE_COLUMNS = [
    "risk",
    "user_a",
    "user_b",
    "game",
    "settle_time",
    "ref_no_a",
    "status_a",
    "stake_a",
    "winlost_a",
    "side_a",
    "ref_no_b",
    "status_b",
    "stake_b",
    "winlost_b",
    "side_b",
    "opposite",
]


def save_outputs(scrape_result: dict, analysis_result: dict, report_date: date) -> list[str]:
    """Write all four CSV reports to data/output/ and return their paths."""
    stamp = report_date.strftime("%Y%m%d")
    reports = [
        (scrape_result["players"], PLAYER_COLUMNS, f"player_info_{stamp}.csv"),
        (scrape_result["bets"], BET_COLUMNS, f"bets_{stamp}.csv"),
        (analysis_result["pairs"], PAIR_COLUMNS, f"pair_betting_{stamp}.csv"),
        (analysis_result["evidence"], EVIDENCE_COLUMNS, f"pair_rounds_{stamp}.csv"),
    ]
    paths = []
    for rows, columns, filename in reports:
        path = os.path.join(config.OUTPUT_DIR, filename)
        utils.write_csv(rows, columns, path)
        logging.info("  Saved: %s (%d rows)", filename, len(rows))
        paths.append(path)
    return paths

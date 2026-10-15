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


def save_outputs(scrape_result: dict, analysis_result: dict, report_date: date) -> list[str]:
    """Write all four CSV reports to data/output/<Month>/<MM-DD-YYYY>/ and return their paths."""
    folder = utils.build_dated_folder(config.OUTPUT_DIR, report_date)
    stamp = report_date.strftime("%Y%m%d")
    reports = [
        (scrape_result["players"], PLAYER_COLUMNS, f"player_info_{stamp}.csv"),
        (scrape_result["bets"], BET_COLUMNS, f"bets_{stamp}.csv"),
        (analysis_result["pairs"], PAIR_COLUMNS, f"pair_betting_{stamp}.csv"),
        (analysis_result["evidence"], EVIDENCE_COLUMNS, f"pair_rounds_{stamp}.csv"),
    ]
    paths = []
    for rows, columns, filename in reports:
        path = os.path.join(folder, filename)
        utils.write_csv(rows, columns, path)
        logging.info("Saved: %s (%d rows)", filename, len(rows))
        paths.append(path)
    return paths

import os
import re
import sys
import time
import getpass
import logging
from collections import Counter
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

import config
import log_utils
import utils
import scraper
import analysis
import file_handler


# ======================================================
# SETUP AND INPUT HELPERS
# ======================================================
def _setup_logging() -> str:
    """Plain-text log file in a dated folder plus a console that is colored when supported."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    log_dir = utils.build_dated_folder(config.LOG_ROOT, date.today())
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(log_dir, config.LOG_FILENAME)

    log_file = logging.FileHandler(log_path, encoding="utf-8")
    log_file.setFormatter(logging.Formatter(config.LOG_FORMAT))
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(log_utils.build_console_formatter(sys.stderr, config.LOG_FORMAT, config.SUCCESS_PREFIXES))
    logging.basicConfig(level=logging.INFO, handlers=[log_file, console])
    return log_path


def _configure_bundled_browser() -> None:
    """When compiled, point Playwright at the Chromium bundled in the exe. Silent on success."""
    if not config.IS_COMPILED:
        return
    candidates = [
        os.path.join(config.BUNDLE_DIR, config.BUNDLED_BROWSERS_DIRNAME),
        os.path.join(config.BASE_DIR, config.BUNDLED_BROWSERS_DIRNAME),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = candidate
            return
    logging.warning(
        "Bundled browser folder not found (checked: %s). Playwright will use its default location.",
        ", ".join(candidates),
    )


def _load_usernames(path: str) -> list[str]:
    """Read one username per line, dropping blanks, duplicates and invalid entries."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Usernames file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    valid = [name for name in lines if re.match(config.USERNAME_PATTERN, name)]
    if len(valid) != len(lines):
        logging.warning("Skipped %d invalid username line(s).", len(lines) - len(valid))
    return list(dict.fromkeys(valid))


def _collect_credentials() -> tuple[str, str]:
    """Read LEO credentials from the .env beside the script/exe, prompting if missing."""
    load_dotenv(config.ENV_FILE)
    username = os.getenv("LEO_USERNAME") or input("LEO username: ").strip()
    password = os.getenv("LEO_PASSWORD") or getpass.getpass("LEO password: ")
    if not username or not password:
        raise ValueError("LEO username and password are required.")
    return username, password


def _collect_report_date() -> date:
    """Ask for the report date (MM/DD/YYYY). Pressing Enter uses yesterday."""
    yesterday = date.today() - timedelta(days=1)
    default_text = yesterday.strftime(config.INPUT_DATE_FORMAT)
    while True:
        text = input(f"Report date (MM/DD/YYYY) [Enter = {default_text}]: ").strip()
        if not text:
            return yesterday
        try:
            return datetime.strptime(text, config.INPUT_DATE_FORMAT).date()
        except ValueError:
            logging.warning("Invalid date '%s' — use MM/DD/YYYY.", text)


# ======================================================
# LOG BLOCKS
# ======================================================
def _log_step(number: int, title: str) -> None:
    """Log a framed step header."""
    log_utils.log_section(f"STEP {number} — {title}")


def _log_banner(report_date: date, player_count: int, log_path: str) -> None:
    """Log the run settings once the date is known."""
    log_utils.log_section(f"PAIR BETTING CHECK v{config.APP_VERSION}")
    log_utils.log_lines(
        [
            log_utils.field("Report date", report_date.strftime(config.INPUT_DATE_FORMAT)),
            log_utils.field("Time window", f"{config.DAY_START} - {config.DAY_END}"),
            log_utils.field("Product", "Live Casino & Casino Games"),
            log_utils.field("Players", player_count),
            log_utils.field("Headless", config.HEADLESS),
            log_utils.field("Settle tolerance", f"{config.SETTLE_TOLERANCE_SECONDS}s"),
            log_utils.field("Min opposite", config.MIN_OPPOSITE_ROUNDS),
            log_utils.field("Min consistency", f"{config.MIN_CONSISTENCY_RATE:.0%}"),
            log_utils.field("Bet time window", f"{config.BET_TIME_WINDOW_SECONDS}s"),
            log_utils.field("Max hedge net", f"{config.MAX_HEDGE_NET_PCT}%"),
            log_utils.field("Output folder", utils.build_dated_folder(config.OUTPUT_DIR, report_date)),
            log_utils.field("Log file", log_path),
        ]
    )


def _log_summary(scrape_result: dict, analysis_result: dict, output_files: list[str], elapsed: float) -> None:
    """Log the final RUN SUMMARY block."""
    risk_counts = Counter(pair["risk"] for pair in analysis_result["pairs"])
    lines = [
        log_utils.field("Players OK", len(scrape_result["players"])),
        log_utils.field("Players failed", len(scrape_result["failures"])),
        log_utils.field("Bets collected", len(scrape_result["bets"])),
        log_utils.field("Pairs HIGH", risk_counts["HIGH"]),
        log_utils.field("Pairs MEDIUM", risk_counts["MEDIUM"]),
        log_utils.field("Pairs LOW", risk_counts["LOW"]),
        log_utils.field("Pairs NONE (CSV)", risk_counts["NONE"]),
        log_utils.field("Execution time", f"{elapsed:.1f}s"),
    ]
    for reason, count in Counter(reason for _, reason in scrape_result["failures"]).most_common():
        lines.append(log_utils.field(f"Failed x{count}", reason))
    lines.extend(log_utils.field("Output file", os.path.basename(path)) for path in output_files)
    log_utils.log_section("RUN SUMMARY")
    log_utils.log_lines(lines)


# ======================================================
# WORKFLOW
# ======================================================
def main() -> None:
    """Run the full workflow: load users → login → scrape → detect pairs → save CSVs."""
    log_path = _setup_logging()
    _configure_bundled_browser()
    started = time.monotonic()

    # Step 1: Load usernames
    _log_step(1, "Loading usernames")
    usernames = _load_usernames(config.USERNAMES_FILE)
    if len(usernames) < 2:
        logging.warning("Need at least 2 usernames to compare. Exiting.")
        return
    logging.info("%s", log_utils.field("Usernames", len(usernames)))

    # Step 2: Collect credentials
    _log_step(2, "Collecting credentials")
    leo_username, leo_password = _collect_credentials()
    logging.info("Logging in as: %s with password: ***", leo_username)

    # Step 3: Collect report date
    _log_step(3, "Collecting report date")
    report_date = _collect_report_date()
    _log_banner(report_date, len(usernames), log_path)

    # Step 4: Scrape basic info and bet lists
    _log_step(4, f"Scraping {len(usernames)} players")
    scrape_result = scraper.run_scraper(usernames, leo_username, leo_password, report_date)

    # Step 5: Detect pair betting
    _log_step(5, "Analysing pair betting")
    analysis_result = analysis.run_analysis(scrape_result["players"], scrape_result["bets"])

    # Step 6: Save outputs
    _log_step(6, "Saving output files")
    output_files = file_handler.save_outputs(scrape_result, analysis_result, report_date)

    _log_summary(scrape_result, analysis_result, output_files, time.monotonic() - started)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.exception("Run failed: %s", error)
        sys.exit(1)

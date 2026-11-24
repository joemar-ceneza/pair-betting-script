import os
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
import account_search
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
    # Playwright's internal asyncio tasks dump tracebacks when a run is stopped mid-way; hide them
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
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


def _collect_credentials() -> tuple[str, str]:
    """Read LEO credentials from the .env beside the script/exe, prompting if missing."""
    load_dotenv(config.ENV_FILE)
    username = os.getenv("LEO_USERNAME") or input("LEO username: ").strip()
    password = os.getenv("LEO_PASSWORD") or getpass.getpass("LEO password: ")
    if not username or not password:
        raise ValueError("LEO username and password are required.")
    return username, password


def _default_report_date() -> date:
    """Today from REPORT_DATE_SWITCH_HOUR (12:00 PM) onwards, yesterday before it."""
    now = datetime.now()
    days_back = 0 if now.hour >= config.REPORT_DATE_SWITCH_HOUR else 1
    return now.date() - timedelta(days=days_back)


def _ask_report_date() -> date:
    """Ask for the report date (MM/DD/YYYY) until it parses. Pressing Enter uses _default_report_date()."""
    default_date = _default_report_date()
    default_text = default_date.strftime(config.INPUT_DATE_FORMAT)
    while True:
        text = input(f"Report date (MM/DD/YYYY) [Enter = {default_text}]: ").strip()
        if not text:
            return default_date
        try:
            return datetime.strptime(text, config.INPUT_DATE_FORMAT).date()
        except ValueError:
            logging.warning("Invalid date '%s' — use MM/DD/YYYY.", text)


def _is_report_date_accepted(report_date: date) -> bool:
    """Reject future dates; ask for confirmation when the date is unusually old (e.g. a year typo)."""
    date_text = report_date.strftime(config.INPUT_DATE_FORMAT)
    age_days = (date.today() - report_date).days
    if age_days < 0:
        logging.warning("Report date %s is in the future — enter today or a past date.", date_text)
        return False
    if age_days <= config.MAX_REPORT_DATE_AGE_DAYS:
        return True
    logging.warning("Report date %s is %d days ago.", date_text, age_days)
    return input("Is that the right date? [y/N]: ").strip().lower() == "y"


def _collect_report_date() -> date:
    """Ask for the report date until a valid, confirmed one is entered."""
    while True:
        report_date = _ask_report_date()
        if _is_report_date_accepted(report_date):
            return report_date


def _warn_if_no_bets(scrape_result: dict) -> None:
    """Warn when every player returned zero bets, so it is not mistaken for a clean result."""
    player_count = len(scrape_result["players"])
    if player_count and not scrape_result["bets"]:
        logging.warning("No Live Casino bets found for any of the %d players on this date.", player_count)


# ======================================================
# LOG BLOCKS
# ======================================================
def _log_step(number: int, title: str) -> None:
    """Log a framed step header."""
    log_utils.log_section(f"STEP {number} — {title}")


def _log_banner(report_date: date, log_path: str) -> None:
    """Log the run settings once the date is known."""
    created_from = report_date - timedelta(days=config.MKT_CREATED_DAYS_BACK)
    log_utils.log_section(f"PAIR BETTING CHECK v{config.APP_VERSION}")
    log_utils.log_lines(
        [
            log_utils.field("Report date", report_date.strftime(config.INPUT_DATE_FORMAT)),
            log_utils.field("Time window", f"{config.DAY_START} - {config.DAY_END}"),
            log_utils.field("Product", config.LIVE_CASINO_PRODUCT_NAME),
            log_utils.field("Accounts from", "Advanced Search (MKT), deposited only"),
            log_utils.field(
                "Accounts created",
                f"{created_from.strftime(config.INPUT_DATE_FORMAT)} - {report_date.strftime(config.INPUT_DATE_FORMAT)}",
            ),
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


def _log_summary(
    account_count: int, scrape_result: dict, analysis_result: dict, output_files: list[str], elapsed: float
) -> None:
    """Log the final RUN SUMMARY block."""
    risk_counts = Counter(pair["risk"] for pair in analysis_result["pairs"])
    lines = [
        log_utils.field("Accounts found", account_count),
        log_utils.field("Players OK", len(scrape_result["players"])),
        log_utils.field("Players failed", len(scrape_result["failures"])),
        log_utils.field("Recovered on retry", scrape_result["recovered"]),
        log_utils.field("LEO re-logins", scrape_result["relogins"]),
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
    if scrape_result["stopped"]:
        logging.error("Run stopped early — LEO was unreachable. Results are PARTIAL; re-run this date.")


# ======================================================
# WORKFLOW
# ======================================================
def main() -> None:
    """Run the full workflow: credentials → date → find accounts → scrape → detect pairs → save CSVs."""
    log_path = _setup_logging()
    _configure_bundled_browser()
    started = time.monotonic()

    # Step 1: Collect credentials
    _log_step(1, "Collecting credentials")
    leo_username, leo_password = _collect_credentials()
    logging.info("Logging in as: %s with password: ***", leo_username)

    # Step 2: Collect report date
    _log_step(2, "Collecting report date")
    report_date = _collect_report_date()
    _log_banner(report_date, log_path)

    # Step 3: Find the accounts to check with Advanced Search (MKT)
    _log_step(3, "Finding accounts (Advanced Search MKT)")
    accounts = account_search.run_account_search((leo_username, leo_password), report_date)
    usernames = [account["account_id"] for account in accounts]
    if len(usernames) < 2:
        logging.warning("Need at least 2 accounts to compare, found %d. Exiting.", len(usernames))
        return

    # Step 4: Scrape basic info, statement figures and bet lists
    _log_step(4, f"Scraping {len(usernames)} players")
    scrape_result = scraper.run_scraper(usernames, leo_username, leo_password, report_date)
    _warn_if_no_bets(scrape_result)

    # Step 5: Detect pair betting
    _log_step(5, "Analysing pair betting")
    analysis_result = analysis.run_analysis(scrape_result["players"], scrape_result["bets"])

    # Step 6: Save outputs
    _log_step(6, "Saving output files")
    output_files = file_handler.save_outputs(accounts, scrape_result, analysis_result, report_date)

    _log_summary(len(accounts), scrape_result, analysis_result, output_files, time.monotonic() - started)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.warning("Run cancelled by user.")
        sys.exit(130)
    except Exception as error:
        logging.exception("Run failed: %s", error)
        sys.exit(1)

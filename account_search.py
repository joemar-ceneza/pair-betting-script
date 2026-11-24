import re
import time
import logging
from datetime import date, timedelta

from playwright.sync_api import Frame, Page, sync_playwright

import config
import leo_session
import log_utils
import utils

_WMA_LINK = "a[href*='WMAMgmt/default.aspx']"  # top toolbar
_MKT_LINK = "a[href*='advanced-search-mkt.aspx']"  # WMA toolbar
_FORM_FRAME_NAME = "icontents"
_SEARCH_BUTTON = "input#btnSearch[value='Search']"  # 'Save As Excel' shares the same id
_SECTIONS = ("basicInfo", "payment", "aInfo")  # collapsed form sections holding our fields
_DISPLAY_COLUMNS = ("username", "createdOn", "currency", "initDepositStatus", "coupon", "status")

# (record key, result-table header). Only ACCOUNT ID is required; missing columns become "-".
_RESULT_COLUMNS = (
    ("account_id", "ACCOUNT ID"),
    ("created_date", "CREATED DATE"),
    ("currency", "CURRENCY"),
    ("deposit_status", "DEPOSIT STATUS"),
    ("promotion_code", "PROMOTION CODE"),
    ("promotion_status", "PROMOTION STATUS"),
)

# The created-date inputs use a datepicker, so set them directly (no popup in the way).
_SET_CREATED_RANGE_JS = """
([fromText, toText]) => {
    document.getElementById('ycreatedon').value = fromText;
    document.getElementById('ycreatedon2').value = toText;
}
"""

# Returns every row of the results table (the table.DT whose header has ACCOUNT ID), or null if none.
_EXTRACT_RESULTS_JS = """
() => {
    const table = [...document.querySelectorAll('table.DT')]
        .find(t => t.rows.length && t.rows[0].innerText.includes('ACCOUNT ID'));
    if (!table) return null;
    return [...table.rows].map(row => [...row.cells].map(cell => cell.innerText.trim()));
}
"""


# ======================================================
# NAVIGATION (WMA → Advanced Search (MKT))
# ======================================================
def _open_advanced_search(leo_page: Page) -> Frame:
    """Click WMA in the top toolbar, then Advanced Search (MKT), and wait for the form."""
    toolbar_frame = utils.find_frame_with(leo_page, _WMA_LINK, config.FRAME_TIMEOUT)
    toolbar_frame.click(_WMA_LINK)
    leo_session.pause(leo_page)
    wma_frame = utils.find_frame_with(leo_page, _MKT_LINK, config.FRAME_TIMEOUT)
    wma_frame.click(_MKT_LINK)
    form_frame = utils.get_frame(leo_page, _FORM_FRAME_NAME, config.FRAME_TIMEOUT)
    form_frame.locator(_SEARCH_BUTTON).wait_for(timeout=config.PAGE_TIMEOUT)
    return form_frame


def _expand_section(form_frame: Frame, section: str) -> None:
    """Open a collapsed form section by clicking its title; leave it alone if already open."""
    header = form_frame.locator(f"#{section}Header")
    if "Collapse" in (header.get_attribute("class") or ""):
        header.locator("td.FoldedIcon").click()
    form_frame.locator(f"#{section}Row").wait_for(state="visible", timeout=config.ELEMENT_TIMEOUT)


# ======================================================
# FILTERS
# ======================================================
def _created_range(report_date: date, today: date | None = None) -> tuple[str, str]:
    """('MM/DD/YYYY', 'MM/DD/YYYY') from the report date to MKT_CREATED_DAYS_AFTER days later, capped at today."""
    today = today or date.today()
    created_to = min(report_date + timedelta(days=config.MKT_CREATED_DAYS_AFTER), today)
    return report_date.strftime(config.INPUT_DATE_FORMAT), created_to.strftime(config.INPUT_DATE_FORMAT)


def _fill_filters(form_frame: Frame, report_date: date, currency: str) -> None:
    """Set the created-date range, currency, deposit status, provider, promotion status and row limit."""
    form_frame.evaluate(_SET_CREATED_RANGE_JS, list(_created_range(report_date)))
    form_frame.select_option("select[id='selcei.Currency']", value=currency)
    form_frame.select_option("#selInitdepositstatus", value=config.MKT_DEPOSIT_STATUS)
    form_frame.select_option("select[id='selcpa.ServiceProvider']", value=config.MKT_SERVICE_PROVIDER)
    form_frame.select_option("#promotionStatus", value=config.MKT_PROMOTION_STATUS)
    form_frame.select_option("#selTop", value=config.MKT_ROW_LIMIT)


def _tick_display_columns(form_frame: Frame) -> None:
    """Make sure the result table shows the columns we read."""
    for column_id in _DISPLAY_COLUMNS:
        checkbox = form_frame.locator(f"input#{column_id}[name='displayCols']")
        if not checkbox.is_checked():
            checkbox.check()


def _submit_search(form_frame: Frame) -> None:
    """Click Search and wait until the page comes back with the form (and results) again."""
    with form_frame.expect_navigation(timeout=config.MKT_SEARCH_TIMEOUT):
        form_frame.click(_SEARCH_BUTTON)
    form_frame.locator(_SEARCH_BUTTON).wait_for(timeout=config.MKT_SEARCH_TIMEOUT)


# ======================================================
# RESULTS
# ======================================================
def _cell(row: list[str], index: int | None) -> str:
    """Cell text at index, or '-' when the column is missing or empty."""
    if index is None or index >= len(row):
        return "-"
    return row[index].strip() or "-"


def _parse_result_rows(rows: list[list[str]]) -> list[dict]:
    """Turn the raw table (header row + data rows) into records, matching columns by header name."""
    if not rows:
        return []
    header = [name.strip().upper() for name in rows[0]]
    if "ACCOUNT ID" not in header:
        raise ValueError(f"Results table has no ACCOUNT ID column (headers: {', '.join(header)})")
    positions = {key: header.index(label) if label in header else None for key, label in _RESULT_COLUMNS}
    return [{key: _cell(row, index) for key, index in positions.items()} for row in rows[1:]]


def _clean_accounts(records: list[dict]) -> tuple[list[dict], int]:
    """
    Drop invalid account IDs and keep the first row per account (LEO repeats an account
    once per service provider). Returns (accounts, invalid row count).
    """
    accounts, seen, invalid = [], set(), 0
    for record in records:
        account_id = record["account_id"]
        # '-' is an empty cell (see _cell), not an account, even though it matches the pattern
        if account_id == "-" or not re.match(config.USERNAME_PATTERN, account_id):
            invalid += 1
            continue
        if account_id not in seen:
            seen.add(account_id)
            accounts.append(record)
    return accounts, invalid


def _read_results(form_frame: Frame) -> list[list[str]]:
    """Read the raw results table; an empty list when LEO shows no results table."""
    rows = form_frame.evaluate(_EXTRACT_RESULTS_JS)
    if rows is None:
        logging.warning("Advanced Search (MKT) returned no results table.")
        return []
    return rows


# ======================================================
# SEARCH + REPORT
# ======================================================
def _search_accounts(leo_page: Page, report_date: date, currency: str) -> list[list[str]]:
    """Open the MKT form, fill it, search, and return the raw result rows (screenshot on failure)."""
    try:
        form_frame = _open_advanced_search(leo_page)
        for section in _SECTIONS:
            _expand_section(form_frame, section)
        _fill_filters(form_frame, report_date, currency)
        _tick_display_columns(form_frame)
        leo_session.pause(leo_page)
        _submit_search(form_frame)
        return _read_results(form_frame)
    except Exception:
        leo_session.save_error_screenshot(leo_page, "advanced search")
        raise


def _log_search_report(
    report_date: date, currency: str, rows: list[list[str]], accounts: list[dict], invalid: int
) -> None:
    """Log the filters used and what came back, then warn if the row limit was reached."""
    created_from, created_to = _created_range(report_date)
    data_rows = max(len(rows) - 1, 0)
    log_utils.log_lines(
        [
            log_utils.field("Created", f"{created_from} - {created_to}"),
            log_utils.field("Currency", "all" if currency == config.MKT_ALL_CURRENCIES else currency),
            log_utils.field("Deposit status", config.MKT_DEPOSIT_STATUS),
            log_utils.field("Service provider", config.MKT_SERVICE_PROVIDER),
            log_utils.field("Promotion status", config.MKT_PROMOTION_STATUS),
            log_utils.field("Row limit", config.MKT_ROW_LIMIT),
            log_utils.field("Rows returned", data_rows),
            log_utils.field("Invalid IDs skipped", invalid),
            log_utils.field("Accounts found", len(accounts)),
        ]
    )
    if data_rows >= config.MKT_ROW_LIMIT_COUNT:
        logging.warning("Search hit the %d-row limit — some accounts may be missing.", config.MKT_ROW_LIMIT_COUNT)


# ======================================================
# PUBLIC ENTRY POINT
# ======================================================
def run_account_search(credentials: tuple[str, str], report_date: date, currency: str) -> list[dict]:
    """
    Log into LEO, run Advanced Search (MKT) for deposited accounts in currency
    (MKT_ALL_CURRENCIES = any) created from report_date up to MKT_CREATED_DAYS_AFTER
    days later (never past today), and return
    one record per account (account_id, created_date, currency, deposit_status, promotion_*).
    """
    started = time.monotonic()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            leo_page = browser.new_context().new_page()
            leo_session.first_login(leo_page, credentials)
            leo_session.pause(leo_page)
            rows = utils.retry(
                lambda: _search_accounts(leo_page, report_date, currency),
                retries=config.RETRY_ATTEMPTS,
                delay=config.RETRY_DELAY,
            )
        finally:
            leo_session.close_browser(browser)
    accounts, invalid = _clean_accounts(_parse_result_rows(rows))
    _log_search_report(report_date, currency, rows, accounts, invalid)
    logging.info("Advanced Search (MKT) done: %d account(s) (%.1fs)", len(accounts), time.monotonic() - started)
    return accounts

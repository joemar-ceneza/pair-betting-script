import time
import logging
from datetime import date, datetime
from typing import Optional

from playwright.sync_api import Browser, Frame, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import config
import log_utils
import utils

_BET_ROWS_SELECTOR = "table.MgmtTableBorder > tbody > tr"
_STATEMENT_ROWS_SELECTOR = "#tblExchange > tbody > tr"

# Reads every bet row in one browser call; rows without 8 cells are skipped.
_EXTRACT_ROWS_JS = """
rows => rows.map(row => {
    const cells = [...row.querySelectorAll(':scope > td')];
    if (cells.length < 8) return null;
    const spanTexts = cell => [...cell.querySelectorAll(':scope > span')].map(s => s.innerText.trim());
    const link = cells[2].querySelector('a[data-refno]');
    return {
        info: spanTexts(cells[1]),
        selection: spanTexts(cells[2]),
        stake: spanTexts(cells[3]),
        winlost: spanTexts(cells[4]),
        status: cells[5].innerText.trim(),
        operator: cells[7].innerText.trim(),
        product_id: link ? link.dataset.productid : '',
    };
}).filter(Boolean)
"""

# Reads every daily-statement row: date, type, product, cash balance (win/loss),
# turnover and the absolute URL of the date link (the bet list for Betting rows).
_EXTRACT_STATEMENT_JS = """
rows => rows.filter(row => row.id !== 'totalRow').map(row => {
    const cells = [...row.querySelectorAll(':scope > td')];
    if (cells.length < 4) return null;
    const link = cells[1].querySelector('a');
    const cash = row.querySelector('td[name="cashBal"]');
    const turnover = row.querySelector('td[name="turnover"]');
    return {
        date: cells[1].textContent.trim(),
        type: cells[2].textContent.trim(),
        product: cells[3].textContent.trim(),
        winloss: cash ? cash.textContent.trim() : '',
        turnover: turnover ? turnover.textContent.trim() : '',
        href: link ? link.href : '',
    };
}).filter(Boolean)
"""

# The statement date inputs are readonly, so set them directly.
_SET_DATE_RANGE_JS = """
([fromText, toText]) => {
    document.getElementById('dpFrom').value = fromText;
    document.getElementById('dpTo').value = toText;
}
"""

_INFO_LABELS = [
    ("customer", "Customer"),
    ("currency", "Currency"),
    ("login_name", "Login Name"),
    ("contact", "Contact 1"),
    ("remark", "Remark"),
    ("vip_level", "Vip Level"),
    ("last_login_ip", "Last Login IP"),
    ("last_logged_url", "Last Logged On Url"),
    ("status", "Status"),
    ("cash_balance", "Cash Balance"),
]


# ======================================================
# LOGIN
# ======================================================
def _dismiss_login_warning(leo_page: Page) -> None:
    """Click 'continue' on the login warning popup if it appears."""
    try:
        leo_page.locator("#tblExchange").wait_for(state="visible", timeout=config.POPUP_TIMEOUT)
    except PlaywrightTimeoutError:
        return
    leo_page.click("#continue")
    logging.info("Login warning popup dismissed.")


def _login(leo_page: Page, username: str, password: str) -> None:
    """Log into LEO and wait until the menu frame is available."""
    leo_page.goto(config.LEO_LOGIN_URL, timeout=config.PAGE_TIMEOUT)
    leo_page.fill("#txtUsername", username)
    leo_page.fill("#txtPassword", password)
    leo_page.click("#btnLogin")
    leo_page.wait_for_load_state("load")
    _dismiss_login_warning(leo_page)
    utils.get_frame(leo_page, "menu", config.FRAME_TIMEOUT)
    logging.info("Logged in to LEO.")


def _refresh_if_due(leo_page: Page, position: int) -> None:
    """Reload the LEO page every N players to free browser memory."""
    if position > 1 and (position - 1) % config.LEO_REFRESH_INTERVAL == 0:
        logging.info("Refreshing LEO page to clear browser memory...")
        leo_page.reload()
        leo_page.wait_for_load_state("load")
        utils.get_frame(leo_page, "menu", config.FRAME_TIMEOUT)


def _close_browser(browser: Browser) -> None:
    """Close the browser; if it is already gone (e.g. run stopped with Ctrl+C), just note it."""
    try:
        browser.close()
        logging.info("Browser closed cleanly.")
    except Exception as error:
        logging.warning("Browser was already closed (%s).", type(error).__name__)


# ======================================================
# BASIC INFORMATION (Balance page in 'contents' frame)
# ======================================================
def _search_player(leo_page: Page, username: str) -> Frame:
    """Search a player by Account ID and wait for their Balance page to load."""
    menu_frame = utils.get_frame(leo_page, "menu", config.FRAME_TIMEOUT)
    menu_frame.fill("#T1", username)
    menu_frame.click(".Button")
    contents_frame = utils.get_frame(leo_page, "contents", config.FRAME_TIMEOUT)
    # Exact prefix match so '123' never matches a stale page for '1234'
    customer_cell = (
        f"xpath=//tr[th[normalize-space()='Customer :']]" f"/td[starts-with(normalize-space(), '{username} (')]"
    )
    contents_frame.locator(customer_cell).first.wait_for(timeout=config.ELEMENT_TIMEOUT)
    return contents_frame


def _read_field(frame: Frame, header: str, cell_path: str = "") -> str:
    """Return the cleaned text of the cell next to a '<header> :' row heading."""
    cells = frame.locator(f"xpath=//tr[th[normalize-space()='{header} :']]/td{cell_path}")
    if cells.count() == 0:
        return "-"
    text = " ".join(cells.first.inner_text().split())
    return text or "-"


def _is_button_on(frame: Frame, button_id: str) -> bool:
    """Return True if a YES/NO status button exists and is set to YES."""
    button = frame.locator(f"#{button_id}")
    return button.count() > 0 and button.first.get_attribute("value") == "YES"


def _read_status(frame: Frame) -> str:
    """Return Closed, Suspended or Open from the status buttons."""
    if _is_button_on(frame, "btnClosed") or _is_button_on(frame, "btnClosedByCompany"):
        return "Closed"
    if _is_button_on(frame, "btnSuspend") or _is_button_on(frame, "btnSuspendedByCompany"):
        return "Suspended"
    return "Open"


def _read_currency(cash_balance: str) -> str:
    """Take the currency code from 'VND 0.00' and apply LEO_CURRENCY_MAP."""
    if cash_balance == "-":
        return "-"
    raw_currency = cash_balance.split()[0]
    return config.LEO_CURRENCY_MAP.get(raw_currency, raw_currency)


def _read_player_info(frame: Frame, username: str) -> dict:
    """Collect the basic information fields from the Balance page."""
    cash_balance = _read_field(frame, "Cash Balance", "//span")
    return {
        "username": username,
        "customer": _read_field(frame, "Customer"),
        "currency": _read_currency(cash_balance),
        "login_name": _read_field(frame, "Login Name"),
        "contact": _read_field(frame, "Contact 1"),
        "remark": _read_field(frame, "Remark"),
        "vip_level": _read_field(frame, "Vip Level"),
        "last_login_ip": _read_field(frame, "Last Login IP"),
        "last_logged_url": _read_field(frame, "Last Logged On Url").split(" (")[0],
        "status": _read_status(frame),
        "cash_balance": cash_balance,
    }


# ======================================================
# DAILY STATEMENT (Stmt button → 'contents' frame)
# ======================================================
def _wait_for_statement(frame: Frame, username: str) -> None:
    """Wait until the statement table for this player is shown."""
    caption = frame.locator("#tblExchange caption", has_text=f"Statement : {username}")
    caption.wait_for(timeout=config.PAGE_TIMEOUT)


def _open_statement(leo_page: Page, username: str) -> Frame:
    """Click the Stmt account button and wait for the daily statement to load."""
    menu_frame = utils.get_frame(leo_page, "menu", config.FRAME_TIMEOUT)
    menu_frame.click("#stmt")
    contents_frame = utils.get_frame(leo_page, "contents", config.FRAME_TIMEOUT)
    _wait_for_statement(contents_frame, username)
    return contents_frame


def _show_turnover(frame: Frame, username: str, report_date: date) -> None:
    """
    Narrow the statement to the report date, tick 'Show Turnover' (accepting the
    'heavy action' confirm, which reloads the page), then tick 'Show all columns'.
    """
    date_text = report_date.strftime(config.INPUT_DATE_FORMAT)
    frame.evaluate(_SET_DATE_RANGE_JS, [f"{date_text} {config.DAY_START}", f"{date_text} {config.DAY_END}"])
    frame.page.once("dialog", lambda dialog: dialog.accept())
    with frame.expect_navigation(timeout=config.PAGE_TIMEOUT):
        frame.click("#chkShowTurnover")
    _wait_for_statement(frame, username)
    frame.click("#showCols")


def _find_live_casino_row(frame: Frame, report_date: date) -> Optional[dict]:
    """Return the Live Casino 'Betting' row for the report date, or None if there was no play."""
    date_text = report_date.strftime(config.INPUT_DATE_FORMAT)
    for row in frame.eval_on_selector_all(_STATEMENT_ROWS_SELECTOR, _EXTRACT_STATEMENT_JS):
        is_betting = row["type"] == "Betting" and row["product"] == config.LIVE_CASINO_PRODUCT_NAME
        if is_betting and row["date"] == date_text:
            return row
    return None


def _statement_figures(live_row: Optional[dict]) -> dict:
    """Win/loss (Cash Balance column) and turnover from the Live Casino row; 0 when no play."""
    if live_row is None:
        return {"turnover": 0.0, "winloss": 0.0}
    return {
        "turnover": utils.parse_amount(live_row["turnover"]) if live_row["turnover"] else 0.0,
        "winloss": utils.parse_amount(live_row["winloss"]) if live_row["winloss"] else 0.0,
    }


# ======================================================
# BET LIST (opened from the statement's own link)
# ======================================================
def _read_betlist_rows(betlist_page: Page, url: str, username: str) -> list[dict]:
    """Open the bet list and return the raw text of every bet row."""
    betlist_page.goto(url, timeout=config.PAGE_TIMEOUT)
    caption = betlist_page.locator("table.MgmtTableBorder caption", has_text=username)
    caption.wait_for(timeout=config.ELEMENT_TIMEOUT)
    return betlist_page.eval_on_selector_all(_BET_ROWS_SELECTOR, _EXTRACT_ROWS_JS)


def _parse_datetime(text: str) -> datetime:
    """Parse '10/14/2026 08:13:48 PM' (line breaks allowed) into a datetime."""
    return datetime.strptime(" ".join(text.split()), config.BET_TIME_FORMAT)


def _infer_side(game: str, status: str, stake: float, winlost: float) -> str:
    """For winning baccarat bets: 0.95 payout = Banker, 1.00 payout = Player."""
    if "baccarat" not in game.lower() or status != "WON" or stake <= 0:
        return "-"
    payout_ratio = winlost / stake
    if abs(payout_ratio - 0.95) < 0.01:
        return "Banker"
    if abs(payout_ratio - 1.00) < 0.01:
        return "Player"
    return "-"


def _parse_bet(raw: dict, username: str) -> dict:
    """Convert one raw bet row into a clean bet record."""
    game = raw["selection"][0]
    status = raw["status"].upper()
    stake = utils.parse_amount(raw["stake"][0])
    winlost = utils.parse_amount(raw["winlost"][0])
    return {
        "username": username,
        "ref_no": raw["info"][0],
        "bet_time": _parse_datetime(raw["info"][1]),
        "settle_time": _parse_datetime(raw["selection"][-1]),
        "game": game,
        "stake": stake,
        "turnover": utils.parse_amount(raw["stake"][1]),
        "winlost": winlost,
        "status": status,
        "inferred_side": _infer_side(game, status, stake, winlost),
        "ip": raw["operator"].split()[-1] if raw["operator"] else "-",
        "product_id": raw["product_id"],
    }


def _parse_bets(raw_rows: list[dict], username: str) -> list[dict]:
    """Parse all raw rows, skipping (and counting) any that are malformed."""
    bets, skipped = [], 0
    for raw in raw_rows:
        try:
            bets.append(_parse_bet(raw, username))
        except (IndexError, ValueError) as error:
            skipped += 1
            logging.debug("Unparsed bet row: %s", error)
    if skipped:
        logging.warning("%d bet row(s) could not be parsed.", skipped)
    return bets


def _read_live_casino_bets(betlist_page: Page, live_row: Optional[dict], username: str) -> list[dict]:
    """Follow the statement's Live Casino link (old or recent date) and parse the bets."""
    if live_row is None or not live_row["href"]:
        return []
    bets = _parse_bets(_read_betlist_rows(betlist_page, live_row["href"], username), username)
    if not bets:
        logging.warning("Statement shows Live Casino betting but the bet list returned no rows.")
    return bets


# ======================================================
# PER-PLAYER PROCESSING
# ======================================================
def _process_player(leo_page: Page, betlist_page: Page, username: str, report_date: date) -> tuple[dict, list[dict]]:
    """Search → basic info → Stmt (win/loss, turnover) → bet list for one player."""
    balance_frame = _search_player(leo_page, username)
    info = _read_player_info(balance_frame, username)
    statement_frame = _open_statement(leo_page, username)
    _show_turnover(statement_frame, username, report_date)
    live_row = _find_live_casino_row(statement_frame, report_date)
    info.update(_statement_figures(live_row))
    bets = _read_live_casino_bets(betlist_page, live_row, username)
    info["bet_count"] = len(bets)
    return info, bets


def _build_player_report(info: dict) -> list[str]:
    """Build the aligned info + statement figures lines for one player."""
    lines = [log_utils.field(label, info[key]) for key, label in _INFO_LABELS]
    lines.append(log_utils.field("Turnover", f"{info['turnover']:,.2f}"))
    lines.append(log_utils.field("Win/Loss", f"{info['winloss']:+,.2f}"))
    lines.append(log_utils.field("Bets", info["bet_count"]))
    return lines


def _save_error_screenshot(page: Page, label: str) -> None:
    """Save the next numbered screenshot to data/screenshots/<Month>/<MM-DD-YYYY>/."""
    try:
        folder = utils.build_dated_folder(config.SCREENSHOT_ROOT, date.today())
        path = utils.next_numbered_path(folder, config.SCREENSHOT_PREFIX, ".png")
        page.screenshot(path=path)
        logging.info("Screenshot for %s: %s", label, path)
    except Exception as error:
        logging.warning("Could not save screenshot for %s: %s", label, error)


def _handle_player(
    pages: tuple[Page, Page], username: str, report_date: date, position: str
) -> tuple[Optional[dict], list[dict], Optional[str]]:
    """Process one player with retries and log their lines under their header."""
    leo_page, betlist_page = pages
    log_utils.log_section(f"[{position}] {username}")
    started = time.monotonic()
    try:
        info, bets = utils.retry(
            lambda: _process_player(leo_page, betlist_page, username, report_date),
            retries=config.RETRY_ATTEMPTS,
            delay=config.RETRY_DELAY,
        )
    except Exception as error:
        logging.error("Failed: %s", error)
        _save_error_screenshot(leo_page, username)
        logging.info("[%s] %s — ERROR (%.1fs)", position, username, time.monotonic() - started)
        return None, [], str(error)
    log_utils.log_lines(_build_player_report(info))
    logging.info("[%s] %s — done, %d bets (%.1fs)", position, username, len(bets), time.monotonic() - started)
    return info, bets, None


# ======================================================
# PUBLIC ENTRY POINT
# ======================================================
def run_scraper(usernames: list[str], leo_username: str, leo_password: str, report_date: date) -> dict:
    """
    Log into LEO once, then for each player collect basic info, the Live Casino
    win/loss and turnover from the daily statement, and the bet list for report_date.
    Returns players, bets and failures.
    """
    players, bets, failures = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS)
        try:
            context = browser.new_context()
            leo_page, betlist_page = context.new_page(), context.new_page()
            try:
                _login(leo_page, leo_username, leo_password)
            except Exception:
                _save_error_screenshot(leo_page, "login")
                raise
            for index, username in enumerate(usernames, start=1):
                _refresh_if_due(leo_page, index)
                position = f"{index}/{len(usernames)}"
                info, player_bets, error = _handle_player((leo_page, betlist_page), username, report_date, position)
                if error:
                    failures.append((username, error))
                    continue
                players.append(info)
                bets.extend(player_bets)
        finally:
            _close_browser(browser)
    return {"players": players, "bets": bets, "failures": failures}

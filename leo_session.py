import logging
from datetime import date

from playwright.sync_api import Browser, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import config
import utils


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


def login(leo_page: Page, credentials: tuple[str, str]) -> None:
    """Log into LEO and wait until the menu frame is available."""
    username, password = credentials
    leo_page.goto(config.LEO_LOGIN_URL, timeout=config.PAGE_TIMEOUT)
    leo_page.fill("#txtUsername", username)
    leo_page.fill("#txtPassword", password)
    leo_page.click("#btnLogin")
    leo_page.wait_for_load_state("load")
    _dismiss_login_warning(leo_page)
    utils.get_frame(leo_page, "menu", config.FRAME_TIMEOUT)
    logging.info("Logged in to LEO.")


def first_login(leo_page: Page, credentials: tuple[str, str]) -> None:
    """Log in at the start of a browser session; screenshot and re-raise if it fails."""
    try:
        login(leo_page, credentials)
    except Exception:
        save_error_screenshot(leo_page, "login")
        raise


# ======================================================
# PAGE ACTIONS
# ======================================================
def pause(page: Page) -> None:
    """Deliberate pause between LEO actions so the site is not hit too fast (STEP_DELAY_SECONDS)."""
    page.wait_for_timeout(config.STEP_DELAY_SECONDS * 1000)


def save_error_screenshot(page: Page, label: str) -> None:
    """Save the next numbered screenshot to data/screenshots/<Month>/<MM-DD-YYYY>/."""
    try:
        folder = utils.build_dated_folder(config.SCREENSHOT_ROOT, date.today())
        path = utils.next_numbered_path(folder, config.SCREENSHOT_PREFIX, ".png")
        page.screenshot(path=path)
        logging.info("Screenshot for %s: %s", label, path)
    except Exception as error:
        logging.warning("Could not save screenshot for %s: %s", label, error)


def close_browser(browser: Browser) -> None:
    """Close the browser; if it is already gone (e.g. run stopped with Ctrl+C), just note it."""
    try:
        browser.close()
        logging.info("Browser closed cleanly.")
    except Exception as error:
        logging.warning("Browser was already closed (%s).", type(error).__name__)

import os
import sys

# When running as a PyInstaller exe, resolve paths relative to the exe.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ======================================================
# PATHS
# ======================================================
USERNAMES_FILE = os.path.join(BASE_DIR, "usernames.txt")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(BASE_DIR, "logs")
SCREENSHOT_DIR = os.path.join(LOG_DIR, "screenshots")
LOG_FILE = os.path.join(LOG_DIR, "automation.log")

# ======================================================
# LEO SITE
# ======================================================
LEO_LOGIN_URL = "http://leo-a01.sbobet.com.tw:8088/Default.aspx"
BETLIST_PATH = "/modules/misc/betlist-lc.aspx"
LIVE_CASINO_PRODUCT_ID = "7"  # Live Casino & Casino Games
LEO_CURRENCY_MAP = {"TB": "Tb"}
USERNAME_PATTERN = r"^[A-Za-z0-9_.@-]+$"

# ======================================================
# BROWSER
# ======================================================
HEADLESS = True
PAGE_TIMEOUT = 30000
ELEMENT_TIMEOUT = 15000
POPUP_TIMEOUT = 5000
FRAME_TIMEOUT = 15000
LEO_REFRESH_INTERVAL = 300
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2

# ======================================================
# DATES
# ======================================================
INPUT_DATE_FORMAT = "%m/%d/%Y"
BET_TIME_FORMAT = "%m/%d/%Y %I:%M:%S %p"
DAY_START = "00:00"
DAY_END = "23:59"

# ======================================================
# PAIR-BETTING DETECTION
# ======================================================
SETTLE_TOLERANCE_SECONDS = 2  # bets settling this close = same round
MIN_OPPOSITE_ROUNDS = 5  # minimum WON-vs-LOSE rounds to flag
MIN_OPPOSITE_RATE = 0.70  # opposite rounds / shared rounds
STAKE_SIMILARITY_RATIO = 0.80  # smaller stake / bigger stake
MIN_SIMILAR_STAKE_RATE = 0.70  # similar-stake rounds / opposite rounds

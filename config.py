import os
import sys

# ======================================================
# APP
# ======================================================
APP_NAME = "PairBettingChecker"
APP_VERSION = "1.0.0"  # BUMP EVERY RELEASE — also used as the exe file/product version

# ======================================================
# RUNTIME LOCATION
# ======================================================
IS_NUITKA = "__compiled__" in globals()
IS_PYINSTALLER = getattr(sys, "frozen", False) and not IS_NUITKA
IS_COMPILED = IS_NUITKA or IS_PYINSTALLER

if IS_NUITKA:
    # sys.argv[0] is the real exe; __file__ and sys.executable point into the unpack folder
    BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
elif IS_PYINSTALLER:
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

# ======================================================
# PATHS (user files and data/ live BESIDE the exe)
# ======================================================
ENV_FILE = os.path.join(BASE_DIR, ".env")
USERNAMES_FILE = os.path.join(BASE_DIR, "usernames.txt")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
LOG_ROOT = os.path.join(DATA_DIR, "logs")
SCREENSHOT_ROOT = os.path.join(DATA_DIR, "screenshots")
LOG_FILENAME = "automation.txt"
SCREENSHOT_PREFIX = "screenshot"
BUNDLED_BROWSERS_DIRNAME = "ms-playwright"

# ======================================================
# LOGGING
# ======================================================
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
SUCCESS_PREFIXES = ("Saved", "Successfully", "Logged in", "Browser closed cleanly")

# ======================================================
# LEO SITE
# ======================================================
LEO_LOGIN_URL = "http://leo-a01.sbobet.com.tw:8088/Default.aspx"
LIVE_CASINO_PRODUCT_NAME = "Live Casino & Casino Games"  # PRODUCT column text on the statement
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

# Deliberate pause between LEO page actions so the site is not hit too fast.
# This is a throttle, not a replacement for element waits. Raise to 5 if errors continue.
STEP_DELAY_SECONDS = 2

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
# Bets settling this close (same account or two accounts, same table) = same round
SETTLE_TOLERANCE_SECONDS = 2

# A pair is "consistent" with at least MIN_OPPOSITE_ROUNDS won-vs-lost rounds AND
# at least MIN_CONSISTENCY_RATE of shared rounds being opposite or tie-together.
# Lower MIN_OPPOSITE_ROUNDS = catches short sessions, but more chance hits.
MIN_OPPOSITE_ROUNDS = 2
MIN_CONSISTENCY_RATE = 0.80

# Supporting signals (2 or more + consistent = HIGH)
STAKE_SIMILARITY_RATIO = 0.80  # smaller round stake / bigger round stake
MIN_SIMILAR_STAKE_RATE = 0.70  # similar-stake rounds / opposite rounds
BET_TIME_WINDOW_SECONDS = 10  # first bets in the round placed this close
MIN_CLOSE_TIMING_RATE = 0.70  # close-timing rounds / shared rounds
MAX_HEDGE_NET_PCT = 5.0  # |combined net| / combined turnover on opposite rounds

# One-way flow (chip dumping): the same account wins this share of opposite rounds.
# With only 2-3 opposite rounds this can happen by chance — check the loser's balance.
MIN_ONE_WAY_RATE = 0.80

# Pair Betting Checker

## What This Does
Logs into LEO, finds the accounts to check with **Advanced Search (MKT)**
(deposited accounts created on the report date and the day after), collects each player's basic
information and their Live Casino bet list for one day, then compares every pair
of accounts round by round to find pair betting (two accounts betting opposite
sides of the same rounds). No account list has to be typed in.

## How Accounts Are Found
Step 3 of every run opens **WMA → Advanced Search (MKT)** in LEO (by clicking,
like a person would), fills the form and clicks **Search**:

| Filter | Value | Setting in `config.py` |
|---|---|---|
| Created date | report date → report date + 1 day (never past today) | `MKT_CREATED_DAYS_AFTER = 1` |
| Currency | asked at the start (Enter = all), or `--currency VND` | `MKT_CURRENCIES`, `MKT_CURRENCY_ALIASES` |
| Initial deposit status | Deposited | `MKT_DEPOSIT_STATUS = "1"` |
| Service provider | any | `MKT_SERVICE_PROVIDER = "-1"` |
| Promotion status | any | `MKT_PROMOTION_STATUS = "-1"` |
| Row limit | Top 10000 | `MKT_ROW_LIMIT = "top_10000"` |

The result table is read straight from the page (no Excel download). Each account's
promotion code and status are shown in its player block, in every flagged pair
(`Promotion A` / `Promotion B`) and in the CSVs; `-` means no promotion. LEO lists an
account once per service provider, so repeated account IDs are checked only once.
Every account found is saved to `accounts_YYYYMMDD.csv` **right after the search**,
before the long scrape starts, so the list is kept even if the run is stopped. If the search returns the
full 10,000 rows, a warning says some accounts may be missing.

Example: report date 11/23 checks the bets on 11/23 of every deposited account
created 11/23 - 11/24. If the report date is today, only accounts created today are searched.

## How Detection Works
1. Each account's bets in the same round are added together
   (2 x 100k in one round = one 200k round).
2. Every round both accounts played on the same table is classified:
   - **OPPOSITE** — one won, the other lost
   - **TIE** — both pushed (a tie with one on Banker, one on Player)
   - **CONFLICT** — both won, both lost, or anything else
3. Supporting signals:
   - **similar stakes** — round stakes within 80% of each other
   - **close timing** — bets placed within seconds of each other
   - **hedged net** — combined net near zero (within 5% of turnover)
   - **one-way flow** — the same account wins 80%+ of opposite rounds
   - **shared IP** — both accounts used the same IP
4. Risk:
   - **HIGH** — 2+ opposite rounds, 80%+ of shared rounds opposite or tie, and 2+ signals
   - **MEDIUM** — consistent as above, with 0–1 signals
   - **LOW** — shared IP, or opposite rounds that are not consistent enough
   - **NONE** — shared rounds but nothing suspicious (CSV only)
5. Pattern (for consistent pairs):
   - **HEDGE** — wins swap between the two accounts; they cover each other's risk
   - **CHIP DUMP** — one account keeps losing to the other; money is being moved,
     often a bonus balance into an account that can withdraw. The report shows
     the direction (`loser -> winner`) and the amount moved.

With only 2–3 opposite rounds, one-way flow can happen by chance. Check the
loser's cash balance: a balance at or near zero supports chip dumping.

All thresholds are in the `PAIR-BETTING DETECTION` section of `config.py`.

**Mixed currencies** (e.g. `VND/THB`, or a currency that could not be read, `-`): rounds are
still matched and classified, but amounts from two currencies can't be added, so
*similar stakes* and *hedged net* are never counted and `opposite_turnover`, `opposite_net`
and `net_pct` show `-`. Such a pair can still reach MEDIUM (or HIGH via close timing,
one-way flow and shared IP).

Rounds are matched to the **closest** settle time on the same table (within
`SETTLE_TOLERANCE_SECONDS`), so two rounds settling close together are never swapped.

## Tests
The detection rules have offline tests with made-up bets (no LEO needed):
```bat
python -m unittest discover tests
```
Run them after changing anything in `analysis.py` or the detection thresholds.

## Requirements
- Python 3.11
- Windows OS

## Setup
1. Create and activate a virtual environment:
```bat
   python -m venv venv
   venv\Scripts\activate
```
2. Install dependencies:
```bat
   pip install -r requirements.txt
   playwright install chromium
```
3. Copy `.env.example` to `.env` and fill in your LEO credentials.

## How to Run
```bat
python main.py
```

Press Enter at the date prompt to use the default date, or type `MM/DD/YYYY`.
The default switches at 12:00 PM Manila time (`REPORT_DATE_SWITCH_HOUR`):

| Run on 11/17 at | Enter = |
|---|---|
| before 12:00 PM (e.g. 8 AM, 11 AM) | 11/16 (yesterday) |
| 12:00 PM or later | 11/17 (today) |

Future dates are rejected.

Next it asks `Currency (e.g. VND, THB) [Enter = all]:` — type one currency to check
only those accounts, or press Enter for all. Codes (`VND`, `THB`, `MYR`, `IDR`, `USD`, ...)
and LEO's labels (`TB`, `RM`, `Pp`, ...) both work, in any case. Or skip the prompt:
```bat
python main.py --currency VND
``` A date more than 30 days back (`MAX_REPORT_DATE_AGE_DAYS`)
asks `Is that the right date? [y/N]` — this catches year typos like `2025` for `2026`.

## Running Automatically (Task Scheduler)
`--auto` runs with no prompts, so Windows Task Scheduler can start it:
```bat
python main.py --auto
```
- Report date = the default date (today from 12:00 PM, yesterday before), no prompt.
- Credentials come ONLY from `.env` (`LEO_USERNAME`, `LEO_PASSWORD`); if either is
  missing the run stops with an error instead of waiting for input.
- Currency: all currencies, unless you add `--currency VND` (an unknown code stops the run).
- The banner shows `Mode : auto (scheduled, no prompts)` and the `Currency`.

Hourly task from 11:00 (one-time setup, PowerShell):
```powershell
schtasks /Create /TN "Pair Betting Checker" /SC HOURLY /ST 11:00 /TR "\"<workspace>\.venv\Scripts\python.exe\" \"<workspace>\pair-betting-checker\main.py\" --auto"
```
Replace `<workspace>` with the full path of the `Python Development` folder.
Check it: `schtasks /Query /TN "Pair Betting Checker" /V /FO LIST`. Remove it:
`schtasks /Delete /TN "Pair Betting Checker" /F`.

### Using the exe instead of Python
Put the exe in its own folder with `.env` beside it, e.g. `C:\PairBettingChecker\`:
```text
C:\PairBettingChecker\
├── pair_betting_checker.exe
├── .env                  # LEO_USERNAME / LEO_PASSWORD
└── data\                 # created by the first run (logs, CSVs, screenshots)
```
Then create the hourly task:
```powershell
schtasks /Create /TN "Pair Betting Checker" /SC HOURLY /ST 11:00 /TR "\"C:\PairBettingChecker\pair_betting_checker.exe\" --auto"
```
Add `--currency VND` after `--auto` to check one currency. The exe always reads `.env` and
writes `data\` beside itself, wherever Task Scheduler starts it. After a rebuild, copy the new
exe over the old one (the task keeps working, no need to recreate it).

Good to know:
- A run with many accounts can take longer than an hour (about 8s per account).
  The task's default *"Do not start a new instance"* skips the next hour instead of
  running two copies at once.
- Every run of the same day overwrites that day's CSVs; the log keeps every run.
  Two tasks for different currencies on the same day would overwrite each other's CSVs.
- The task only runs while the PC is on, awake, and (by default) you are logged in.

## Session Recovery
**LEO outage at the start** (503 Service Unavailable, login page not loading, connection reset):
logging in and the Advanced Search (MKT) are each tried 3 times, 30s apart (`RELOGIN_RETRY_DELAY`),
and every search attempt logs in fresh. A short outage is ridden out instead of failing that hour's
run; the log shows `Attempt 1 of 3 failed: ... — trying again in 30s`. If LEO is still down after
3 tries the run stops with an error (and the next scheduled run tries again).

**During the scrape**, if the network drops or the LEO session expires, every remaining player
would fail. To prevent that:
1. After 2 players fail in a row (`MAX_CONSECUTIVE_FAILURES`), the script logs in to LEO again.
2. If logging in again fails 3 times, 30s apart (`RELOGIN_RETRY_DELAY`), the scrape stops,
   the remaining players are listed as `Not checked`, and the results so far are saved.
   The summary ends with `Run stopped early ... Results are PARTIAL` — re-run that date.
3. Players that failed get one more try at the end of the run (`RETRYING N FAILED PLAYER(S)`).

The RUN SUMMARY shows `Recovered on retry` and `LEO re-logins`.

## Terminal Output
Every line is logged separately with its own timestamp, and sections are
framed with `=` lines.

In a terminal, lines are colored: gray timestamp, blue INFO, green SUCCESS
(INFO lines starting with `Saved`, `Successfully`, `Logged in` or `Browser closed cleanly`),
yellow WARNING, red ERROR. The log file is always plain text.

Colors turn off automatically when output is redirected or run by Task Scheduler.
To turn them off manually:

| Shell | Command |
|---|---|
| cmd | `set NO_COLOR=1` |
| PowerShell | `$env:NO_COLOR = "1"` |

## Data Folder Layout
```text
data/
├── output/
│   └── October/
│       └── 10-14-2026/          ← by REPORT date (the day checked)
│           ├── accounts_20261014.csv
│           ├── player_info_20261014.csv
│           ├── bets_20261014.csv
│           ├── pair_betting_20261014.csv
│           └── pair_rounds_20261014.csv
├── logs/
│   └── October/
│       └── 10-15-2026/          ← by RUN date
│           └── automation.txt
└── screenshots/
    └── October/
        └── 10-15-2026/          ← by RUN date
            ├── screenshot-001.png
            └── screenshot-002.png
```

Example: checking 10/14 on the morning of 10/15 gives
`data/output/October/10-14-2026/` and `data/logs/October/10-15-2026/`.

## Output Files
| File | Contents |
|---|---|
| `accounts_YYYYMMDD.csv` | Accounts found by Advanced Search (MKT): account ID, created date, currency, deposit status, promotion code and status |
| `player_info_YYYYMMDD.csv` | Basic information per player, including promotion code and status from Advanced Search (MKT) |
| `bets_YYYYMMDD.csv` | Every Live Casino bet |
| `pair_betting_YYYYMMDD.csv` | Every pair with shared rounds or a shared IP: risk, pattern (HEDGE / CHIP DUMP), signals, one-way flow direction and amount, each account's promotion (`promotion_a` / `promotion_b`, e.g. `MAX125 (Activated)`) |
| `pair_rounds_YYYYMMDD.csv` | Every shared round per pair: round type, stakes, results, seconds between bets, reference numbers |

## Building the Exe (Nuitka)
1. Bump `APP_VERSION` in `config.py` for every release.
2. Install build tools and the browser:
```bat
   pip install -r requirements-dev.txt
   playwright install chromium
```
3. Exclude this project folder and `%LOCALAPPDATA%\Nuitka` from antivirus scanning.
4. Build:
```bat
   python build_nuitka.py
```
5. The exe is in `dist\pair_betting_checker.exe`.

Chromium is bundled inside the exe. On first launch of each version it unpacks
once to `%LOCALAPPDATA%\PairBettingChecker\<version>\`.

## Deployment Layout
Copy only the exe, then add the user files beside it:

```text
any_folder/
├── pair_betting_checker.exe
├── .env
└── data/          ← created automatically on first run
```

## Proving the Bundled Browser Works
Playwright silently falls back to the dev machine's browsers, so test without them:

1. Rename `%LOCALAPPDATA%\ms-playwright` to `ms-playwright.bak`.
2. Copy the exe and `.env` into an empty folder and run the exe.
3. Success = the log reaches `Logged in to LEO.` with no
   `Bundled browser folder not found` warning.
4. Rename `ms-playwright.bak` back to `ms-playwright`.

## Protection and Antivirus
- Nuitka hides the Python source code, but URLs and strings can still be read from the exe.
  Credentials stay in `.env`, never in code.
- Single-file exes are sometimes flagged by antivirus. Never compress with UPX.
  Code-signing the exe is the real fix.

## Project Structure
```text
pair-betting-checker/
├── main.py               # Orchestrator — numbered steps only
├── config.py             # Settings, paths, version, detection thresholds
├── account_search.py     # Advanced Search (MKT) → accounts to check
├── scraper.py            # Basic info → statement → bet list per account
├── leo_session.py        # Shared LEO login, pause, screenshot, browser close
├── analysis.py           # Round-by-round pair-betting detection
├── file_handler.py       # CSV outputs
├── utils.py              # Generic helpers (retry, frames, dated folders)
├── log_utils.py          # Line-by-line log helpers + terminal colors
├── build_nuitka.py       # Builds the single-file exe
├── tests/                # Offline tests: detection rules, MKT result parsing (unittest)
├── requirements.txt      # Runtime dependencies
├── requirements-dev.txt  # Build-only (Nuitka)
├── pyproject.toml        # Black settings (line length 120)
├── .env.example          # Credential template
└── data/                 # Output, logs, screenshots (not in Git)
```

## Logs
- Logs: `data/logs/<Month>/<MM-DD-YYYY>/automation.txt`
- Error screenshots: `data/screenshots/<Month>/<MM-DD-YYYY>/`
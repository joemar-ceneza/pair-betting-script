# Pair Betting Checker

## What This Does
Logs into LEO, collects each player's basic information and their Live Casino
bet list for one day, then compares every pair of accounts round by round to
find pair betting (two accounts betting opposite sides of the same rounds).

## How Detection Works
1. Each account's bets in the same round are added together
   (2 x 100k in one round = one 200k round).
2. Every round both accounts played on the same table is classified:
   - OPPOSITE — one won, the other lost
   - TIE      — both pushed (a tie with one on Banker, one on Player)
   - CONFLICT — both won, both lost, or anything else
3. Supporting signals: similar stakes, bets placed within seconds,
   combined net near zero (hedged), shared IP.
4. Risk:
   - HIGH   — 2+ opposite rounds, 80%+ of shared rounds opposite or tie, and 2+ signals
   - MEDIUM — consistent as above, with 0-1 signals
   - LOW    — shared IP, or opposite rounds that are not consistent enough
   - NONE   — shared rounds but nothing suspicious (CSV only)

All thresholds are in the PAIR-BETTING DETECTION section of config.py.

## Requirements
- Python 3.11
- Windows OS

## Setup
1. Create virtual environment:
   python -m venv venv
   venv\Scripts\activate
2. Install dependencies:
   pip install -r requirements.txt
   playwright install chromium
3. Copy .env.example to .env and fill in your LEO credentials
4. Put account IDs in usernames.txt (one per line)

## How to Run
   python main.py

Press Enter at the date prompt to check yesterday, or type MM/DD/YYYY.
Run after 12:00 PM Manila time so the full LEO day (GMT-4) has closed.

## Terminal Output
Every line is logged separately with its own timestamp, and sections are
framed with "=" lines.

In a terminal, lines are colored: gray timestamp, blue INFO, green SUCCESS
(INFO lines starting with Saved / Successfully / Logged in / Browser closed cleanly),
yellow WARNING, red ERROR. The log file is always plain text.

Colors turn off automatically when output is redirected or run by Task Scheduler.
To turn them off manually:
- cmd:        set NO_COLOR=1
- PowerShell: $env:NO_COLOR = "1"

## Data Folder Layout
data/
├── output/<Month>/<MM-DD-YYYY>/       CSV reports, by REPORT date (the day checked)
├── logs/<Month>/<MM-DD-YYYY>/         automation.txt, by RUN date
└── screenshots/<Month>/<MM-DD-YYYY>/  screenshot-001.png, ..., by RUN date

Example: checking 10/14 on the morning of 10/15 gives
data/output/October/10-14-2026/ and data/logs/October/10-15-2026/

## Output Files
- player_info_YYYYMMDD.csv  — basic information per player
- bets_YYYYMMDD.csv         — every Live Casino bet
- pair_betting_YYYYMMDD.csv — every pair with shared rounds or a shared IP,
                              ranked HIGH / MEDIUM / LOW / NONE, with signals
- pair_rounds_YYYYMMDD.csv  — every shared round per pair: round type, stakes,
                              results, seconds between bets, reference numbers

## Building the Exe (Nuitka)
1. Bump APP_VERSION in config.py for every release.
2. pip install -r requirements-dev.txt
3. playwright install chromium
4. Exclude this project folder and %LOCALAPPDATA%\Nuitka from antivirus scanning.
5. python build_nuitka.py
6. The exe is in dist\pair_betting_checker.exe

Chromium is bundled inside the exe. On first launch of each version it unpacks
once to %LOCALAPPDATA%\PairBettingChecker\<version>\.

## Deployment Layout
Copy only the exe, then add the user files beside it:

any_folder/
├── pair_betting_checker.exe
├── .env
├── usernames.txt
└── data/          created automatically on first run

## Proving the Bundled Browser Works
Playwright silently falls back to the dev machine's browsers, so test without them:
1. Rename %LOCALAPPDATA%\ms-playwright to ms-playwright.bak
2. Copy the exe, .env and usernames.txt into an empty folder and run the exe
3. Success = the log reaches "Logged in to LEO." with no
   "Bundled browser folder not found" warning
4. Rename ms-playwright.bak back to ms-playwright

## Protection and Antivirus
- Nuitka hides the Python source code, but URLs and strings can still be read from the exe.
  Credentials stay in .env, never in code.
- Single-file exes are sometimes flagged by antivirus. Never compress with UPX.
  Code-signing the exe is the real fix.

## Project Structure
pair_betting_checker/
├── main.py              # Orchestrator — numbered steps only
├── config.py            # Settings, paths, version, detection thresholds
├── scraper.py           # Login → basic info → bet list
├── analysis.py          # Round-by-round pair-betting detection
├── file_handler.py      # CSV outputs
├── utils.py             # Generic helpers (retry, frames, dated folders)
├── log_utils.py         # Line-by-line log helpers + terminal colors
├── build_nuitka.py      # Builds the single-file exe
├── requirements.txt
└── requirements-dev.txt # Build-only (Nuitka)

## Logs
Logs: data/logs/<Month>/<MM-DD-YYYY>/automation.txt
Error screenshots: data/screenshots/<Month>/<MM-DD-YYYY>/
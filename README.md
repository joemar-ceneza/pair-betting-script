# Pair Betting Checker

## What This Does
Logs into LEO, collects each player's basic information and their Live Casino
bet list for one day, then flags account pairs that bet opposite sides of the
same rounds (one WON / one LOST, settled within seconds on the same table).

## Requirements
- Python 3.10+
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

## Output (output/)
- player_info_YYYYMMDD.csv  — basic information per player
- bets_YYYYMMDD.csv         — every Live Casino bet
- pair_betting_YYYYMMDD.csv — flagged pairs, ranked HIGH / MEDIUM / LOW
- pair_rounds_YYYYMMDD.csv  — matched rounds proving each flagged pair

## Tuning
Detection thresholds are in the PAIR-BETTING DETECTION section of config.py.

## Project Structure
pair_betting_checker/
├── main.py           # Orchestrator — numbered steps only
├── config.py         # Settings and detection thresholds
├── scraper.py        # Login → basic info → bet list
├── analysis.py       # Pair-betting detection
├── file_handler.py   # CSV outputs
├── utils.py          # Generic helpers
├── log_utils.py      # Log formatting helpers
└── usernames.txt     # Account IDs to check

## Logs
Logs are saved to logs/automation.log
Screenshots on errors are saved to logs/screenshots/
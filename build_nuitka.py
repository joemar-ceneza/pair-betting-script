"""
Build a single-file Windows exe with Nuitka, with Chromium bundled inside.
Run:  python build_nuitka.py
"""

import os
import sys
import json
import shutil
import logging
import subprocess

import config

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENTRY_POINT = os.path.join(PROJECT_DIR, "main.py")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
STAGE_DIR = os.path.join(BUILD_DIR, "ms-playwright-stage")

EXE_NAME = "pair_betting_checker.exe"
COMPANY_NAME = "Your Company"
PRODUCT_NAME = "Pair Betting Checker"
FILE_DESCRIPTION = "Detects pair betting in LEO Live Casino bet lists"
ICON_PATH = ""  # e.g. os.path.join(PROJECT_DIR, "favicon.ico"); leave "" for no icon

REQUIRED_BROWSERS = ("chromium", "chromium-headless-shell")
OPTIONAL_BROWSERS = ("ffmpeg", "winldd")
DEV_ONLY_PACKAGES = (
    "pytest",
    "_pytest",
    "black",
    "IPython",
    "ipykernel",
    "jupyter_client",
    "notebook",
    "mypy",
    "pylint",
    "tkinter",
)


# ======================================================
# HELPERS
# ======================================================
def _setup_logging() -> None:
    """Console-only logging for the build script."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")


def _fail(message: str) -> None:
    """Log a clear error and stop the build."""
    logging.error(message)
    sys.exit(1)


def _check_icon() -> None:
    """Stop early if an icon is configured but missing."""
    if ICON_PATH and not os.path.isfile(ICON_PATH):
        _fail(f'Icon file not found: {ICON_PATH}\nFix ICON_PATH in build_nuitka.py, or set it to "" for no icon.')


def _check_nuitka() -> None:
    """Stop early if Nuitka isn't installed."""
    try:
        import nuitka  # noqa: F401
    except ImportError:
        _fail("Nuitka is not installed. Run: pip install -r requirements-dev.txt")


def _clean_build_folders() -> None:
    """Remove old build/dist output and any leftover Nuitka *.build / *.dist folders."""
    leftovers = [
        os.path.join(PROJECT_DIR, name)
        for name in os.listdir(PROJECT_DIR)
        if name.endswith((".build", ".dist", ".onefile-build"))
    ]
    for folder in [BUILD_DIR, DIST_DIR, *leftovers]:
        if os.path.isdir(folder):
            shutil.rmtree(folder)
            logging.info("Removed old folder: %s", folder)


# ======================================================
# BROWSER STAGING
# ======================================================
def _find_playwright_package() -> str:
    """Return the installed playwright package folder."""
    try:
        import playwright
    except ImportError:
        _fail("Playwright is not installed. Run: pip install -r requirements.txt")
    return os.path.dirname(os.path.abspath(playwright.__file__))


def _read_browser_revisions(playwright_package: str) -> dict[str, str]:
    """Read browser revisions from Playwright's own driver/package/browsers.json."""
    browsers_json = os.path.join(playwright_package, "driver", "package", "browsers.json")
    if not os.path.isfile(browsers_json):
        _fail(
            f"browsers.json not found: {browsers_json}\nReinstall Playwright: pip install --force-reinstall playwright"
        )
    with open(browsers_json, "r", encoding="utf-8") as f:
        entries = json.load(f)["browsers"]
    return {entry["name"]: entry.get("revisionOverrides", {}).get("win64", entry["revision"]) for entry in entries}


def _find_browsers_root() -> str:
    """Return where Playwright installed its browsers on this machine."""
    custom_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if custom_path and custom_path != "0":
        return custom_path
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")


def _browser_folder_name(name: str, revision: str) -> str:
    """'chromium-headless-shell' + '1187' → 'chromium_headless_shell-1187'."""
    return f"{name.replace('-', '_')}-{revision}"


def _stage_browsers(revisions: dict[str, str]) -> None:
    """Copy ONLY the needed browser folders into STAGE_DIR."""
    browsers_root = _find_browsers_root()
    os.makedirs(STAGE_DIR, exist_ok=True)
    for name in REQUIRED_BROWSERS + OPTIONAL_BROWSERS:
        if name not in revisions:
            if name in REQUIRED_BROWSERS:
                _fail(f"'{name}' is not listed in Playwright's browsers.json — upgrade Playwright.")
            continue
        folder = _browser_folder_name(name, revisions[name])
        source = os.path.join(browsers_root, folder)
        if not os.path.isdir(source):
            if name in REQUIRED_BROWSERS:
                _fail(f"Browser not installed: {source}\nRun: playwright install chromium")
            logging.info("Optional browser not found, skipping: %s", folder)
            continue
        shutil.copytree(source, os.path.join(STAGE_DIR, folder))
        logging.info("Staged: %s", folder)


# ======================================================
# NUITKA
# ======================================================
def _build_nuitka_command(playwright_package: str) -> list[str]:
    """Assemble the full Nuitka command line."""
    driver_dir = os.path.join(playwright_package, "driver")
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--assume-yes-for-downloads",
        f"--output-dir={DIST_DIR}",
        f"--output-filename={EXE_NAME}",
        f"--onefile-tempdir-spec={{CACHE_DIR}}/{config.APP_NAME}/{config.APP_VERSION}",
        "--deployment",
        "--python-flag=no_asserts",
        "--python-flag=no_docstrings",
        "--remove-output",
        "--windows-console-mode=force",
        f"--company-name={COMPANY_NAME}",
        f"--product-name={PRODUCT_NAME}",
        f"--file-description={FILE_DESCRIPTION}",
        f"--product-version={config.APP_VERSION}",
        f"--file-version={config.APP_VERSION}",
        # Raw dirs keep .exe/.dll files (data dirs would drop them)
        f"--include-raw-dir={STAGE_DIR}=ms-playwright",
        f"--include-raw-dir={driver_dir}=playwright/driver",
    ]
    command += [f"--nofollow-import-to={package}" for package in DEV_ONLY_PACKAGES]
    if ICON_PATH:
        command.append(f"--windows-icon-from-ico={ICON_PATH}")
    command.append(ENTRY_POINT)
    return command


def _log_failure_hints() -> None:
    """Explain the most common reasons a Nuitka build fails on Windows."""
    hints = [
        "Nuitka build FAILED. Common causes:",
        "  - Antivirus deleted or locked compiled object files (.o/.obj) mid-build.",
        f"    Exclude {PROJECT_DIR} and %LOCALAPPDATA%\\Nuitka from real-time scanning, then rebuild.",
        "  - No C compiler: install Visual Studio Build Tools ('Desktop development with C++'),",
        "    or let Nuitka download MinGW64 when it asks.",
        "  - Python from the Microsoft Store is not supported: use the python.org installer.",
        "  - Not enough disk space or memory: close other programs and free a few GB.",
        "  - Scroll up for the first real error line printed by Nuitka.",
    ]
    logging.error("\n".join(hints))


def _run_nuitka(command: list[str]) -> None:
    """Run Nuitka and stop with hints if it fails."""
    logging.info("Running Nuitka (this takes several minutes)...")
    result = subprocess.run(command, cwd=PROJECT_DIR)
    if result.returncode != 0:
        _log_failure_hints()
        sys.exit(result.returncode)


# ======================================================
# BUILD
# ======================================================
def main() -> None:
    """Clean → check → stage browsers → compile → report."""
    _setup_logging()
    logging.info("Building %s v%s", EXE_NAME, config.APP_VERSION)
    _check_icon()
    _check_nuitka()
    _clean_build_folders()

    playwright_package = _find_playwright_package()
    revisions = _read_browser_revisions(playwright_package)
    _stage_browsers(revisions)

    _run_nuitka(_build_nuitka_command(playwright_package))

    exe_path = os.path.join(DIST_DIR, EXE_NAME)
    if not os.path.isfile(exe_path):
        _fail(f"Nuitka finished but the exe was not found: {exe_path}")
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    logging.info("Build complete: %s (%.0f MB)", exe_path, size_mb)
    logging.info("Ship only the exe. Put .env and usernames.txt beside it.")


if __name__ == "__main__":
    main()

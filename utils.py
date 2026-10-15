import os
import csv
import time
import logging
from typing import Any, Callable

from playwright.sync_api import Frame, Page


def retry(func: Callable, retries: int = 3, delay: int = 2) -> Any:
    """Run func, retrying on failure. Re-raises with the last error message."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return func()
        except Exception as error:
            last_error = error
            logging.warning("  Attempt %d of %d failed: %s", attempt, retries, error)
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"All {retries} attempts failed: {last_error}") from last_error


def get_frame(page: Page, frame_name: str, timeout_ms: int = 15000) -> Frame:
    """Return a named frame, polling until it exists or the timeout passes."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        frame = page.frame(name=frame_name)
        if frame:
            return frame
        page.wait_for_timeout(250)
    raise TimeoutError(f"Frame '{frame_name}' not found within {timeout_ms} ms")


def parse_amount(text: str) -> float:
    """Convert '1,600,000.00' or '-2,000,000.00' to a float."""
    return float(text.replace(",", "").strip())


def write_csv(rows: list[dict], columns: list[str], path: str) -> None:
    """Write dict rows to a CSV (Excel-friendly UTF-8), creating the folder if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

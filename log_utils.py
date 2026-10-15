import os
import sys
import logging

WIDTH = 70

_RESET = "\033[0m"
_GRAY = "\033[90m"
_BLUE = "\033[94m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"

_STD_ERROR_HANDLE = -12
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


# ======================================================
# TEXT LAYOUT HELPERS
# ======================================================
def rule(char: str = "=") -> str:
    """Return a full-width ASCII separator line."""
    return char * WIDTH


def section(title: str) -> str:
    """Return a major section header framed with '=' rules."""
    return f"{rule('=')}\n{title}\n{rule('=')}"


def subsection(title: str) -> str:
    """Return a sub-step header framed with '-' rules."""
    return f"{rule('-')}\n{title}\n{rule('-')}"


def field(label: str, value: object, width: int = 18) -> str:
    """Return an aligned 'label : value' line."""
    return f"  {label:<{width}}: {value}"


# ======================================================
# TERMINAL COLOR SUPPORT
# ======================================================
def _enable_windows_ansi() -> bool:
    """Turn on ANSI escape support for the stderr console. Returns False if it can't."""
    try:
        # Imported here because these Windows APIs are only needed (and only safe) on Windows
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]

        handle = kernel32.GetStdHandle(_STD_ERROR_HANDLE)
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & _ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False


def supports_color(stream: object) -> bool:
    """True only for a real terminal, without NO_COLOR, where ANSI colors can be enabled."""
    if os.environ.get("NO_COLOR"):
        return False
    is_tty = getattr(stream, "isatty", None)
    if is_tty is None or not is_tty():
        return False
    if sys.platform == "win32":
        return _enable_windows_ansi()
    return True


def _paint(color: str, text: str) -> str:
    """Wrap text in an ANSI color, or return it unchanged when no color is given."""
    return f"{color}{text}{_RESET}" if color else text


class ColorFormatter(logging.Formatter):
    """Same layout as the plain formatter, with colored timestamp, level and message."""

    def __init__(self, fmt: str, success_prefixes: tuple[str, ...]) -> None:
        super().__init__(fmt)
        self._success_prefixes = tuple(success_prefixes)

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """Gray timestamp."""
        return _paint(_GRAY, super().formatTime(record, datefmt))

    def _pick_style(self, record: logging.LogRecord, message: str) -> tuple[str, str, str]:
        """Return (level name, level color, message color) for a record."""
        if record.levelno >= logging.ERROR:
            return record.levelname, _RED, _RED
        if record.levelno >= logging.WARNING:
            return record.levelname, _YELLOW, _YELLOW
        if record.levelno == logging.INFO and message.lstrip().startswith(self._success_prefixes):
            return "SUCCESS", _GREEN, _GREEN
        if record.levelno == logging.INFO:
            return record.levelname, _BLUE, ""
        return record.levelname, _GRAY, ""

    def _format_extras(self, record: logging.LogRecord) -> str:
        """Return traceback and stack text without touching the original record."""
        parts = []
        if record.exc_info:
            parts.append(self.formatException(record.exc_info))
        elif record.exc_text:
            parts.append(record.exc_text)
        if record.stack_info:
            parts.append(self.formatStack(record.stack_info))
        return "\n".join(parts)

    def format(self, record: logging.LogRecord) -> str:
        """Format a colored copy so the file handler still gets the untouched record."""
        message = record.getMessage()
        level_name, level_color, message_color = self._pick_style(record, message)
        extras = self._format_extras(record)
        body = f"{message}\n{extras}" if extras else message

        painted = logging.makeLogRecord(record.__dict__)
        painted.levelname = _paint(level_color, level_name)
        painted.msg = _paint(message_color, body)
        painted.args = None
        painted.exc_info, painted.exc_text, painted.stack_info = None, None, None
        return super().format(painted)


def build_console_formatter(stream: object, fmt: str, success_prefixes: tuple[str, ...]) -> logging.Formatter:
    """Return a ColorFormatter for real terminals, otherwise a plain Formatter."""
    if supports_color(stream):
        return ColorFormatter(fmt, success_prefixes)
    return logging.Formatter(fmt)

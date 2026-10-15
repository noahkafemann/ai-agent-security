"""ANSI style helpers for AGORIS output.

Provides color codes and styling functions that gracefully degrade
when output is not a terminal.
"""

import sys
from typing import Optional


def _supports_color() -> bool:
    """Return True if the terminal supports color."""
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    # Windows console supports color since Windows 10 version 1511.
    # We assume it's supported; if not, colors will just be printed as-is.
    return True


# ANSI escape codes
if _supports_color():
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"
    STRIKETHROUGH = "\033[9m"

    # Foreground colors
    FG_BLACK = "\033[30m"
    FG_RED = "\033[31m"
    FG_GREEN = "\033[32m"
    FG_YELLOW = "\033[33m"
    FG_BLUE = "\033[34m"
    FG_MAGENTA = "\033[35m"
    FG_CYAN = "\033[36m"
    FG_WHITE = "\033[37m"
    FG_DEFAULT = "\033[39m"

    # Bright foreground colors
    FG_BRIGHT_BLACK = "\033[90m"
    FG_BRIGHT_RED = "\033[91m"
    FG_BRIGHT_GREEN = "\033[92m"
    FG_BRIGHT_YELLOW = "\033[93m"
    FG_BRIGHT_BLUE = "\033[94m"
    FG_BRIGHT_MAGENTA = "\033[95m"
    FG_BRIGHT_CYAN = "\033[96m"
    FG_BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"
    BG_DEFAULT = "\033[49m"

    # Bright background colors
    BG_BRIGHT_BLACK = "\033[100m"
    BG_BRIGHT_RED = "\033[101m"
    BG_BRIGHT_GREEN = "\033[102m"
    BG_BRIGHT_YELLOW = "\033[103m"
    BG_BRIGHT_BLUE = "\033[104m"
    BG_BRIGHT_MAGENTA = "\033[105m"
    BG_BRIGHT_CYAN = "\033[106m"
    BG_BRIGHT_WHITE = "\033[107m"
else:
    # No color support - empty strings
    RESET = BOLD = DIM = ITALIC = UNDERLINE = BLINK = REVERSE = STRIKETHROUGH = ""
    FG_BLACK = FG_RED = FG_GREEN = FG_YELLOW = FG_BLUE = FG_MAGENTA = FG_CYAN = FG_WHITE = FG_DEFAULT = ""
    FG_BRIGHT_BLACK = FG_BRIGHT_RED = FG_BRIGHT_GREEN = FG_BRIGHT_YELLOW = FG_BRIGHT_BLUE = FG_BRIGHT_MAGENTA = FG_BRIGHT_CYAN = FG_BRIGHT_WHITE = ""
    BG_BLACK = BG_RED = BG_GREEN = BG_YELLOW = BG_BLUE = BG_MAGENTA = BG_CYAN = BG_WHITE = BG_DEFAULT = ""
    BG_BRIGHT_BLACK = BG_BRIGHT_RED = BG_BRIGHT_GREEN = BG_BRIGHT_YELLOW = BG_BRIGHT_BLUE = BG_BRIGHT_MAGENTA = BG_BRIGHT_CYAN = BG_BRIGHT_WHITE = ""


def colorize(text: str, color: str = "") -> str:
    """Wrap text in ANSI color code if color is supported."""
    if not color:
        return text
    return f"{color}{text}{RESET}"


def bold(text: str) -> str:
    """Return bold text if supported."""
    return colorize(text, BOLD)


def dim(text: str) -> str:
    """Return dim text if supported."""
    return colorize(text, DIM)


def green(text: str) -> str:
    """Return green text if supported."""
    return colorize(text, FG_GREEN)


def red(text: str) -> str:
    """Return red text if supported."""
    return colorize(text, FG_RED)


def yellow(text: str) -> str:
    """Return yellow text if supported."""
    return colorize(text, FG_YELLOW)


def blue(text: str) -> str:
    """Return blue text if supported."""
    return colorize(text, FG_BLUE)


def magenta(text: str) -> str:
    """Return magenta text if supported."""
    return colorize(text, FG_MAGENTA)


def cyan(text: str) -> str:
    """Return cyan text if supported."""
    return colorize(text, FG_CYAN)


def white(text: str) -> str:
    """Return white text if supported."""
    return colorize(text, FG_WHITE)


def bright_green(text: str) -> str:
    """Return bright green text if supported."""
    return colorize(text, FG_BRIGHT_GREEN)


def bright_red(text: str) -> str:
    """Return bright red text if supported."""
    return colorize(text, FG_BRIGHT_RED)


def bright_yellow(text: str) -> str:
    """Return bright yellow text if supported."""
    return colorize(text, FG_BRIGHT_YELLOW)


def bright_blue(text: str) -> str:
    """Return bright blue text if supported."""
    return colorize(text, FG_BRIGHT_BLUE)


def bright_magenta(text: str) -> str:
    """Return bright magenta text if supported."""
    return colorize(text, FG_BRIGHT_MAGENTA)


def bright_cyan(text: str) -> str:
    """Return bright cyan text if supported."""
    return colorize(text, FG_BRIGHT_CYAN)


def bright_white(text: str) -> str:
    """Return bright white text if supported."""
    return colorize(text, FG_BRIGHT_WHITE)


def header(text: str) -> str:
    """Return styled header text."""
    return bold(bright_cyan(text))


def success(text: str) -> str:
    """Return styled success text."""
    return bright_green(text)


def error(text: str) -> str:
    """Return styled error text."""
    return bright_red(text)


def warning(text: str) -> str:
    """Return styled warning text."""
    return bright_yellow(text)


def info(text: str) -> str:
    """Return styled info text."""
    return bright_blue(text)


def dim_text(text: str) -> str:
    """Return dimmed text."""
    return dim(text)


def rule(char: str = "─", length: int = 0) -> str:
    """Return a horizontal rule."""
    if length <= 0:
        # Try to get terminal width
        try:
            import shutil
            length = shutil.get_terminal_size((80, 20)).columns
        except Exception:
            length = 80
    return colorize(char * length, FG_BRIGHT_BLACK)


def box_title(title: str, width: int = 0) -> str:
    """Return a title inside a box."""
    if width <= 0:
        try:
            import shutil
            width = shutil.get_terminal_size((80, 20)).columns
        except Exception:
            width = 80
    if len(title) >= width - 4:
        width = len(title) + 4
    padding = width - len(title) - 2
    left = padding // 2
    right = padding - left
    line = "═" * (width - 2)
    return (
        colorize("╔", FG_BRIGHT_BLACK) + line + colorize("╗", FG_BRIGHT_BLACK) + "\n" +
        colorize("║", FG_BRIGHT_BLACK) + " " * left + bold(title) + " " * right + colorize(" ║", FG_BRIGHT_BLACK) + "\n" +
        colorize("╚", FG_BRIGHT_BLACK) + line + colorize("╝", FG_BRIGHT_BLACK)
    )
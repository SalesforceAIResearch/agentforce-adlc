"""Terminal UI helpers — step narration, spinners, color.

Kept tiny and dependency-free (stdlib + click). Everything can be disabled by
setting NO_COLOR=1 or by passing a TTY check, so JSON output / CI logs stay clean.
"""
from __future__ import annotations

import itertools
import os
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator

import click

# Visual vocabulary -----------------------------------------------------------
# Unicode glyphs. If the terminal can't render these we degrade gracefully;
# they're only decoration and the text after them still reads fine.

ICON_RUN = "▶"
ICON_OK = "✓"
ICON_WARN = "!"
ICON_ERR = "✗"
ICON_HEADER = "◆"
ICON_BULLET = "•"
ICON_ARROW = "→"

# Session-level status icons (printed in the per-session scorecard).
LABEL_ICON = "★"
REASON_ICON = "↳"

SEP = "─" * 72
HEAVY_SEP = "━" * 72


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def header(text: str) -> None:
    """Top-of-run banner."""
    if _color_enabled():
        click.secho(f"\n{ICON_HEADER} {text}", fg="cyan", bold=True)
    else:
        click.echo(f"\n{ICON_HEADER} {text}")


def step(n: int, total: int, text: str) -> None:
    """Announce the start of a numbered top-level step."""
    prefix = f"[{n}/{total}]"
    if _color_enabled():
        click.secho(f"\n{ICON_RUN} ", fg="blue", bold=True, nl=False)
        click.secho(prefix, fg="blue", bold=True, nl=False)
        click.echo(f"  {text}")
    else:
        click.echo(f"\n{ICON_RUN} {prefix}  {text}")


def substep(text: str, *, ok: bool = False, warn: bool = False, err: bool = False) -> None:
    """Single indented status line under a step."""
    icon = ICON_BULLET
    color = None
    if ok:
        icon, color = ICON_OK, "green"
    elif warn:
        icon, color = ICON_WARN, "yellow"
    elif err:
        icon, color = ICON_ERR, "red"
    if color and _color_enabled():
        click.secho(f"   {icon} {text}", fg=color)
    else:
        click.echo(f"   {icon} {text}")


def info(text: str) -> None:
    """Low-signal informational line."""
    if _color_enabled():
        click.secho(f"   {text}", fg="bright_black")
    else:
        click.echo(f"   {text}")


def success_banner(text: str) -> None:
    if _color_enabled():
        click.secho(f"\n{ICON_OK} {text}", fg="green", bold=True)
    else:
        click.echo(f"\n{ICON_OK} {text}")


def error_banner(text: str) -> None:
    if _color_enabled():
        click.secho(f"\n{ICON_ERR} {text}", fg="red", bold=True, err=True)
    else:
        click.echo(f"\n{ICON_ERR} {text}", err=True)


class Spinner:
    """A minimal ASCII-spinner thread, displayed only in a TTY. Safe no-op otherwise."""

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str):
        self.text = text
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = _color_enabled()
        # Output state — track what we've printed so we can erase cleanly.
        self._last_line_len = 0

    def __enter__(self) -> "Spinner":
        if not self._active:
            # Non-TTY: announce work starting with a dim bullet. A substep() line
            # after the block will print the completion result.
            click.echo(f"   {ICON_BULLET} {self.text}")
            return self
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._active:
            return
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        # Erase the spinner line.
        sys.stdout.write("\r" + " " * self._last_line_len + "\r")
        sys.stdout.flush()

    def set_text(self, new_text: str) -> None:
        """Update the spinner's label while it's running (e.g. for sub-progress)."""
        self.text = new_text

    def _spin(self) -> None:
        frames = itertools.cycle(self._FRAMES)
        while not self._stop.is_set():
            frame = next(frames)
            line = f"   {frame} {self.text}"
            self._last_line_len = max(self._last_line_len, len(line))
            sys.stdout.write("\r" + line + " " * max(0, self._last_line_len - len(line)))
            sys.stdout.flush()
            time.sleep(0.08)


@contextmanager
def spinner(text: str) -> Iterator[Spinner]:
    """Context manager that runs a spinner while a block executes.

    Usage:
        with ui.spinner("Fetching…") as s:
            do_work()
            s.set_text("Fetching, 2/3")
        ui.substep("Fetched 3 sessions", ok=True)
    """
    sp = Spinner(text)
    with sp:
        yield sp


def short_id(session_id: str, head: int = 8, tail: int = 4) -> str:
    """Pretty-shorten a UUID for table display. Keeps head + ellipsis + tail."""
    if len(session_id) <= head + tail + 1:
        return session_id
    return f"{session_id[:head]}…{session_id[-tail:]}"


def color_label(label: str) -> str:
    """Color a scorer label by its sentiment. Best-effort heuristic."""
    if not _color_enabled() or not label:
        return label
    lower = label.lower()
    positive = ("excellent", "very_helpful", "helpful", "good", "not_frustrated",
                "resolved", "success")
    negative = ("poor", "not_helpful", "very_frustrated", "frustrated", "bad",
                "failed", "toxic")
    neutral = ("adequate", "somewhat_helpful", "mildly_frustrated", "neutral",
               "inconclusive", "unknown")
    if any(p in lower for p in positive):
        return click.style(label, fg="green", bold=True)
    if any(n in lower for n in negative):
        return click.style(label, fg="red", bold=True)
    if any(n in lower for n in neutral):
        return click.style(label, fg="yellow", bold=True)
    return click.style(label, bold=True)


def wrap_indent(text: str, width: int = 76, indent: str = "       ") -> str:
    """Wrap `text` to `width` characters and indent continuation lines."""
    import textwrap
    if not text:
        return ""
    wrapped = textwrap.fill(
        text.strip(),
        width=width,
        initial_indent="",
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapped

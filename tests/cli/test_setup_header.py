from __future__ import annotations

import io
import re
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.style import Style
from typer.testing import CliRunner

from jarvislabs import config
from jarvislabs.cli import render, setup
from jarvislabs.cli.app import app

runner = CliRunner()

ANSI = re.compile(r"\x1b\[[0-9;]*m")
WORDMARK_TOP_ROW = "   ▗▄▄▄▄▖                     ▄▄        ██▌        ▐█▌"


@pytest.fixture()
def terminal(server, monkeypatch):
    """A first-time setup in an interactive terminal 80 columns wide; the API key typed is "jarvis-key"."""
    # Rich's Style._add caches rendered ANSI codes on Style instances across consoles of different colour systems.
    Style._add.cache_clear()
    monkeypatch.setattr(render, "can_prompt", lambda: True)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setattr(setup.questionary, "password", lambda message, **kwargs: MagicMock(ask=lambda: "jarvis-key"))
    monkeypatch.setattr("rich.console.getpass", lambda prompt, stream=None: "jarvis-key")
    return monkeypatch


def test_first_setup_opens_with_the_wordmark(terminal):
    result = runner.invoke(app, ["setup"], input="n\n")

    assert result.exit_code == 0, result.output
    assert WORDMARK_TOP_ROW in result.output
    assert "CLI Setup" not in result.output


@pytest.mark.parametrize(
    ("saved_key", "columns", "tty", "args"),
    [
        pytest.param(True, "79", True, ["setup"], id="re-run-narrow"),
        pytest.param(False, "79", True, ["setup"], id="narrow"),
        pytest.param(False, "80", False, ["setup"], id="piped"),
        pytest.param(False, "80", True, ["setup", "--yes"], id="yes"),
    ],
)
def test_setup_shows_the_one_line_header_otherwise(terminal, saved_key, columns, tty, args):
    if saved_key:
        config.save_config({"auth": {"token": "jarvis-key"}})
    terminal.setenv("COLUMNS", columns)
    terminal.setattr(render, "can_prompt", lambda: tty)

    result = runner.invoke(app, args, input="n\nn\n")

    assert result.exit_code == 0, result.output
    assert "\nJarvislabs CLI setup\n" in result.output
    assert WORDMARK_TOP_ROW not in result.output


def test_setup_asks_for_the_jarvis_key(terminal):
    terminal.setattr(render, "can_prompt", lambda: False)

    result = runner.invoke(app, ["setup"], input="n\n")

    assert result.exit_code == 0, result.output
    assert "Get your API key at: https://jarvislabs.ai/settings/api-keys" in result.output
    assert "? API key: " in result.output
    assert "JarvisLabs" not in result.output
    assert "API token" not in result.output


def test_a_repeat_setup_in_a_wide_terminal_still_shows_the_wordmark(terminal):
    config.save_config({"auth": {"token": "jarvis-key"}})
    terminal.setenv("COLUMNS", "80")
    terminal.setattr(render, "can_prompt", lambda: True)

    result = runner.invoke(app, ["setup"], input="n\nn\n")

    assert result.exit_code == 0, result.output
    assert WORDMARK_TOP_ROW in result.output


def test_truecolor_setup_opens_with_the_gradient_mark_beside_the_wordmark_within_80_columns(terminal):
    buffer = io.StringIO()
    console = Console(file=buffer, width=80, force_terminal=True, color_system="truecolor", theme=render.theme)
    terminal.setattr(render, "console", console)
    terminal.setattr(render, "MARKS", render.UNICODE_MARKS)

    result = runner.invoke(app, ["setup"], input="n\n")

    assert result.exit_code == 0, result.output
    raw_banner_lines = buffer.getvalue().splitlines()[1:7]
    # First banner line has 24-bit RGB colour (38;2;) for the diamond peak before the wordmark.
    assert any("\x1b[38;2;" in line for line in raw_banner_lines)
    plain_lines = [ANSI.sub("", line) for line in raw_banner_lines]
    # 11-column mark + 2-space gap + 66-column wordmark = 79 columns max, so 80 columns never wraps.
    assert len(plain_lines) == 6
    assert max(len(line) for line in plain_lines) == 79
    assert plain_lines[0].endswith(WORDMARK_TOP_ROW)
    assert "▀" in plain_lines[0] or "▄" in plain_lines[0]


def test_256_colour_setup_opens_with_a_quantised_mark_beside_the_wordmark(terminal):
    buffer = io.StringIO()
    console = Console(file=buffer, width=80, force_terminal=True, color_system="256", theme=render.theme)
    terminal.setattr(render, "console", console)
    terminal.setattr(render, "MARKS", render.UNICODE_MARKS)

    result = runner.invoke(app, ["setup"], input="n\n")

    assert result.exit_code == 0, result.output
    raw_banner_lines = buffer.getvalue().splitlines()[1:7]
    assert any("\x1b[38;5;" in line for line in raw_banner_lines)
    plain_lines = [ANSI.sub("", line) for line in raw_banner_lines]
    assert max(len(line) for line in plain_lines) == 79
    assert plain_lines[0].endswith(WORDMARK_TOP_ROW)


@pytest.mark.parametrize(
    ("color_system", "no_color", "marks"),
    [
        pytest.param("standard", False, render.UNICODE_MARKS, id="16-colour"),
        pytest.param(None, True, render.UNICODE_MARKS, id="no-color"),
        pytest.param("truecolor", False, render.ASCII_MARKS, id="ascii-marks"),
    ],
)
def test_setup_omits_the_gradient_mark_on_unsupported_consoles(terminal, color_system, no_color, marks):
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=80,
        force_terminal=True,
        color_system=color_system,
        no_color=no_color,
        theme=render.theme,
    )
    terminal.setattr(render, "console", console)
    terminal.setattr(render, "MARKS", marks)

    result = runner.invoke(app, ["setup"], input="n\n")

    assert result.exit_code == 0, result.output
    raw_banner_lines = buffer.getvalue().splitlines()[1:7]
    assert not any("\x1b[38;2;" in line or "\x1b[38;5;" in line for line in raw_banner_lines)
    plain_lines = [ANSI.sub("", line) for line in raw_banner_lines]
    # Wordmark alone (max 66 columns), with no 11-column mark prefix.
    assert plain_lines[0] == WORDMARK_TOP_ROW
    assert max(len(line) for line in plain_lines) == 66

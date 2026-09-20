"""External terminal launcher — opens CLI tools in Terminal.app or Warp.

Uses AppleScript via `osascript` to drive the host apps. Both Terminal.app
and Warp support AppleScript automation (Warp's support is informal but
reliable for new tabs + paste).

For Warp we use clipboard paste because Warp doesn't implement `do script`
the way Terminal.app does. The flow is:
  1. Copy the command to the system clipboard.
  2. Bring Warp to front via `tell application "Warp" to activate`.
  3. Wait briefly so Warp's new-tab shortcut can be intercepted.
  4. Send ⌘V then Return via System Events keystroke.

This avoids the brittle parts of our built-in PTY (which can choke on
long-running TUI agents like claude/codex/omp).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QGuiApplication


def _escape_for_applescript(s: str) -> str:
    """Escape a string for safe inclusion in an AppleScript literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _is_warp_installed() -> bool:
    """Quick check for Warp.app."""
    if os.path.exists("/Applications/Warp.app"):
        return True
    # Also check user-wrapped installs
    home = os.path.expanduser("~")
    for path in (f"{home}/Applications/Warp.app", "/Applications/Setapp/Warp.app"):
        if os.path.exists(path):
            return True
    return False


def _is_terminal_installed() -> bool:
    """Terminal.app is always present on macOS."""
    return os.path.exists("/Applications/Utilities/Terminal.app") or os.path.exists(
        "/System/Applications/Utilities/Terminal.app"
    )


def open_in_terminal_app(command: str, cwd: str | None = None) -> tuple[bool, str]:
    """Open `command` in a new Terminal.app window.

    Returns (success, error_message).
    """
    if not _is_terminal_installed():
        return False, "Terminal.app not found"

    esc_cmd = _escape_for_applescript(command)
    cd_part = ""
    if cwd:
        esc_cwd = _escape_for_applescript(cwd)
        cd_part = f'cd "{esc_cwd}" && '

    script = f'''
    tell application "Terminal"
        activate
        do script "{cd_part}{esc_cmd}"
    end tell
    '''
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return False, r.stderr.strip() or f"osascript exit {r.returncode}"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "AppleScript timed out"
    except Exception as e:
        return False, str(e)


def open_in_warp(command: str, cwd: str | None = None) -> tuple[bool, str]:
    """Open `command` in a new Warp tab via clipboard paste.

    Returns (success, error_message). Falls back to Terminal.app if Warp isn't installed.
    """
    if not _is_warp_installed():
        # Fall back gracefully
        return open_in_terminal_app(command, cwd)

    # 1. Copy the full command (with cd if cwd) to clipboard
    full_cmd = command
    if cwd:
        full_cmd = f"cd {shlex.quote(cwd)} && {command}"

    clipboard = QGuiApplication.clipboard()
    clipboard.setText(full_cmd)

    # 2. Bring Warp to front
    activate_script = 'tell application "Warp" to activate'
    try:
        subprocess.run(
            ["osascript", "-e", activate_script],
            capture_output=True, text=True, timeout=5,
        )
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    # 3. Small delay so Warp is ready to receive input
    time.sleep(0.3)

    # 4. Open a new tab (⌘T) and paste
    paste_script = '''
    tell application "System Events"
        tell process "Warp"
            keystroke "t" using {command down}
            delay 0.15
            keystroke "v" using {command down}
            delay 0.05
            key code 36
        end tell
    end tell
    '''
    try:
        r = subprocess.run(
            ["osascript", "-e", paste_script],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            # Common reason: Accessibility / Automation permissions not granted
            return False, (
                "Warp automation blocked. Grant Accessibility in "
                "System Settings → Privacy & Security → Accessibility for Terminal.app / Warp. "
                f"({r.stderr.strip() or 'osascript exit ' + str(r.returncode)})"
            )
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "AppleScript timed out"
    except Exception as e:
        return False, str(e)


# ─── Convenience wrapper with status-bar feedback ──────────────────────

class ExternalLauncher(QObject):
    """Object that emits signals so MainWindow can show status-bar feedback."""

    launched_in_terminal = Signal(str)   # command
    launched_in_warp = Signal(str)       # command
    launch_failed = Signal(str, str)     # command, error message

    def launch(self, target: str, command: str, cwd: str | None = None):
        """target: 'terminal' or 'warp'."""
        if target == "warp":
            ok, err = open_in_warp(command, cwd)
        else:
            ok, err = open_in_terminal_app(command, cwd)

        if ok:
            if target == "warp":
                self.launched_in_warp.emit(command)
            else:
                self.launched_in_terminal.emit(command)
        else:
            self.launch_failed.emit(command, err)
        return ok
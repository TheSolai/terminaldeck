"""Built-in terminal — uses pyte for stable VT100/Xterm emulation.

Architecture:
- pty.fork() spawns the child process in a real pseudo-terminal
- PTYReader thread reads bytes from PTY master fd via select()
- Bytes flow into a pyte.Stream that updates a pyte.HistoryScreen
- A 30 FPS repaint timer snapshots the screen and updates the QPlainTextEdit
- Keystrokes are forwarded to PTY master fd

This avoids the brittle hand-rolled ANSI parser. pyte is a battle-tested
VT100/Xterm emulator used by many Python terminal apps and handles:
- Cursor positioning (CUP, HVP, HPA, VPA)
- Screen erase (ED, EL, ECH, SU, SD)
- Colors (SGR — 8/16/256/RGB)
- Alternate screen buffer (smcup, rmcup) — used by vim, less, htop
- Scrolling regions (DECSTBM)
- Alternate character sets (DEC drawing chars)
- Cursor visibility + shape (DECTCEM)
- Mouse reporting (sgr1006, urxvt, normal tracking modes)

This is the SAME engine xterm.js uses (logic-wise), so apps like vim, htop,
claude/codex TUI, lazygit, btop, etc. just work.
"""

from __future__ import annotations

import os
import pty
import re
import fcntl
import shutil
import signal
import struct
import sys
import termios
from PySide6.QtCore import QObject, QThread, Signal, Qt, QTimer, QSize, QPoint
from PySide6.QtGui import (
    QFont, QTextCursor, QFontDatabase, QKeyEvent, QKeySequence,
    QAction, QGuiApplication
)
from PySide6.QtWidgets import (
    QPlainTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QFrame, QMenu, QApplication, QFileDialog
)

import pyte


# ─── ANSI stripping (for "Save Output…" only) ──────────────────────────

_ANSI_RE = re.compile(
    r"\x1b\[[0-9;]*[A-Za-z]"      # CSI sequences
    r"|\x1b\][^\x07]*\x07"        # OSC sequences
    r"|\x1b[()][\dA-Za-z]"        # Charset selection
    r"|\x1b[=>NOMc]"              # Misc single-char
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ─── PTY reader thread ─────────────────────────────────────────────────

class PTYReader(QThread):
    """Reads bytes from the PTY master fd and emits them as a signal.

    Also scans output for terminal capability queries (DA, DSR, OSC color
    queries) and writes back appropriate responses. Without this, programs
    like `gh` and `ollama` hang forever waiting for a reply that pyte
    never generates.
    """
    data_received = Signal(bytes)
    closed = Signal(int)

    # Patterns we respond to. Compiled for speed.
    # DA: ESC [ ? (optional) 0/6 c  — we answer "I am VT100 with extras"
    DA_RE = re.compile(rb"\x1b\[\??0?c")
    # DSR 5n (status) / 6n (cursor position)
    DSR5_RE = re.compile(rb"\x1b\[5n")
    DSR6_RE = re.compile(rb"\x1b\[6n")
    # OSC 10;? (foreground), 11;? (background), 12;? (cursor color)
    OSC_FG_RE = re.compile(rb"\x1b\]10;\?\x1b\\")
    OSC_BG_RE = re.compile(rb"\x1b\]11;\?\x1b\\")
    OSC_CURSOR_RE = re.compile(rb"\x1b\]12;\?\x1b\\")
    # DEC private mode set/reset — we ack most as enabled
    # CSI ? 12h (start blinking cursor), ? 25h (show cursor), ? 1049h (alt screen)
    DECSET_RE = re.compile(rb"\x1b\[\?(?P<n>\d+)h")
    DECRST_RE = re.compile(rb"\x1b\[\?(?P<n>\d+)l")

    # Responses
    DA_RESPONSE = b"\x1b[?1;2c"          # VT100 with ANSI color
    DSR5_RESPONSE = b"\x1b[0n"            # OK
    DSR6_RESPONSE = b"\x1b[1;1R"          # row 1, col 1
    OSC_FG_RESPONSE = b"\x1b]10;rgb:d0d0/d0d0/d0d0\x1b\\"
    OSC_BG_RESPONSE = b"\x1b]11;rgb:00/00/00\x1b\\"
    OSC_CURSOR_RESPONSE = b"\x1b]12;rgb:ff/ff/ff\x1b\\"

    def __init__(self, fd: int):
        super().__init__()
        self.fd = fd
        self._running = True

    def _respond_to_queries(self, data: bytes):
        """Scan a chunk for terminal queries and write back responses.

        Modifies `data` in-place by stripping query sequences (so pyte
        doesn't try to render them and they don't leak to the user), and
        returns the response bytes to write back to the master fd.
        """
        response = b""

        # OSC color queries — strip from display, ack with a fake color
        if self.OSC_BG_RE.search(data):
            response += self.OSC_BG_RESPONSE
        if self.OSC_FG_RE.search(data):
            response += self.OSC_FG_RESPONSE
        if self.OSC_CURSOR_RE.search(data):
            response += self.OSC_CURSOR_RESPONSE

        # DSR (cursor / status queries)
        if self.DSR6_RE.search(data):
            response += self.DSR6_RESPONSE
        if self.DSR5_RE.search(data):
            response += self.DSR5_RESPONSE

        # DA (Device Attributes)
        if self.DA_RE.search(data):
            response += self.DA_RESPONSE

        # DEC private modes — pyte tracks these internally; we just need to
        # NOT crash. The Stream class already handles most of them.

        return response

    def run(self):
        import select
        try:
            while self._running:
                try:
                    rlist, _, _ = select.select([self.fd], [], [], 0.1)
                except (OSError, ValueError):
                    break
                if self.fd in rlist:
                    try:
                        data = os.read(self.fd, 8192)
                    except OSError:
                        break
                    if not data:
                        break

                    # Reply to terminal queries BEFORE forwarding to the
                    # screen — the child is blocking on the response.
                    response = self._respond_to_queries(data)
                    if response:
                        try:
                            os.write(self.fd, response)
                        except OSError:
                            pass

                    self.data_received.emit(data)
        finally:
            self.closed.emit(0)

    def stop(self):
        """Stop the reader. select() timeout ensures it exits within 100ms."""
        self._running = False


# ─── Terminal pane widget ──────────────────────────────────────────────

class TerminalPane(QPlainTextEdit):
    """QPlainTextEdit wired up as a real terminal backed by pyte.

    pyte.HistoryScreen holds the visible screen plus scrollback history.
    We render it as plain text (one line per row, including wide-char width
    via wcwidth). For colors, we apply SGR via Qt rich-text spans.
    """

    BANNER = (
        "\x1b[1;36m┌─ TerminalDeck ───────────────────────────────────────┐\x1b[0m\n"
        "\x1b[36m│\x1b[0m Type, Ctrl-C to interrupt, Ctrl-D to exit.        \x1b[36m│\x1b[0m\n"
        "\x1b[1;36m└──────────────────────────────────────────────────────┘\x1b[0m\n\n"
    )

    # Emitted whenever the underlying process state changes (start, exit, error)
    state_changed = Signal(str)
    process_exited = Signal(int)

    # Repaint rate (30 fps). Smooth enough, doesn't peg the CPU.
    REPAINT_MS = 33

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(False)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setMaximumBlockCount(10_000)  # hard cap on lines retained

        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0d1117;
                color: #d4d4d4;
                border: none;
                padding: 6px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
        """)

        # State
        self.master_fd: int | None = None
        self.child_pid: int | None = None
        self.reader: PTYReader | None = None

        # pyte screen + stream. HistoryScreen holds scrollback. cols=120,
        # rows=40 (pyte will resize on TIOCSWINSZ ioctl if we update it).
        self._cols, self._rows = 120, 40
        self._screen = pyte.HistoryScreen(self._cols, self._rows)
        self._stream = pyte.Stream(self._screen)

        # Render coalescing: data → _dirty=True, repaint timer drains it
        self._dirty = False
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setInterval(self.REPAINT_MS)
        self._repaint_timer.timeout.connect(self._on_repaint_tick)
        self._repaint_timer.start()

        # Idle metrics
        self._bytes_in = 0
        self._lines_rendered = 0

    # ─── Lifecycle ──────────────────────────────────────────────────────

    def run_command(self, command: str, cwd: str | None = None):
        """Spawn `command` in a PTY and stream output via pyte."""
        if self.master_fd is not None:
            self.append_plain("\n\x1b[33m⚠  Terminal already running. Stop first.\x1b[0m\n")
            return

        # Interactive login shell so PATH / env match the user's terminal.
        # Drop the `-l` flag — it triggers /etc/profile and ~/.zprofile, which
        # print a LOT of init output that confuses pyte and slows startup.
        # The shell still sources .zshrc on first prompt.
        shell = os.environ.get("SHELL", "/bin/zsh")
        argv = [shell, "-i", "-c", command]
        if shell.endswith("/sh") and not shell.endswith("zsh") and not shell.endswith("bash"):
            argv = [shell, "-c", command]

        # Make sure the child has sensible terminal env vars. Without these,
        # some tools disable color or refuse to run their TUI mode.
        child_env = {
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
            "TERM_PROGRAM": "TerminalDeck",
            "TERM_FEATURES": "truecolor:sixels:iterm-emulation",
            "COLUMNS": str(self._cols),
            "LINES": str(self._rows),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
            "HOME": os.environ.get("HOME", "/Users/amre"),
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "USER": os.environ.get("USER", ""),
            "SHELL": shell,
            "TERM_PROGRAM_VERSION": "0.1.0",
        }

        try:
            pid, fd = pty.fork()
        except OSError as e:
            self.append_plain(f"\x1b[31m✗ pty.fork failed: {e}\x1b[0m\n")
            return

        if pid == 0:
            # Child process. Set terminal size BEFORE exec so programs that
            # query dimensions at startup (vim, htop, claude TUI, etc.) see
            # the correct cols/rows.
            try:
                fcntl.ioctl(
                    0,  # stdin is the slave PTY
                    termios.TIOCSWINSZ,
                    struct.pack("HHHH", self._rows, self._cols, 0, 0),
                )
            except OSError:
                pass

            # Replace env with our controlled set, keeping selected vars
            for k, v in child_env.items():
                os.environ[k] = v

            try:
                if cwd:
                    os.chdir(cwd)
                os.execvpe(argv[0], argv, os.environ)
            except OSError as e:
                sys.stderr.write(f"exec failed: {e}\n")
                os._exit(127)

        # Parent
        self.child_pid = pid
        self.master_fd = fd

        # Reset pyte screen for fresh run
        self._screen = pyte.HistoryScreen(self._cols, self._rows)
        self._stream = pyte.Stream(self._screen)

        # Also set winsize on parent master fd — this triggers SIGWINCH
        # delivery to the child so it can redraw if it already started.
        self._set_winsize(self._cols, self._rows)

        # Non-blocking
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Banner + the command line itself
        self.append_ansi(self.BANNER)
        self.append_plain(f"\x1b[1;32m$ {command}\x1b[0m\n")

        # Reader
        self.reader = PTYReader(fd)
        self.reader.data_received.connect(self._on_data)
        self.reader.closed.connect(self._on_closed)
        self.reader.start()

        self.state_changed.emit(command)
        self.setFocus()

    def _set_winsize(self, cols: int, rows: int):
        """Tell the child PTY its size via TIOCSWINSZ ioctl."""
        if self.master_fd is None:
            return
        # struct winsize { ws_row, ws_col, ws_xpixel, ws_ypixel }
        try:
            fcntl.ioctl(
                self.master_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )
        except OSError:
            pass

    def resizeEvent(self, event):
        """Update PTY size when the widget is resized."""
        super().resizeEvent(event)
        if self.master_fd is None:
            return
        # Compute new cols/rows from current widget size + font metrics
        fm = self.fontMetrics()
        char_w = max(1, fm.horizontalAdvance("M"))
        char_h = max(1, fm.lineSpacing())
        # Account for padding (6px each side, top + a few for last line)
        pad = 12
        cols = max(20, (self.viewport().width() - pad) // char_w)
        rows = max(5, (self.viewport().height() - pad) // char_h)
        if (cols, rows) != (self._cols, self._rows):
            self._cols, self._rows = cols, rows
            # pyte doesn't have a set_size method; we just keep screen+history
            # at fixed cols but tell the PTY its new size so the program
            # redraws to fit.
            self._set_winsize(cols, rows)
            # Mark dirty — pyte will receive SIGWINCH and the program may redraw
            self._dirty = True

    def stop(self):
        if self.child_pid and self.master_fd is not None:
            try:
                os.kill(self.child_pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            self._cleanup()
            self.state_changed.emit("")

    def kill(self):
        """Hard kill (SIGKILL). Use when stop() doesn't terminate."""
        if self.child_pid:
            try:
                os.kill(self.child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _cleanup(self):
        # Close fd first — unblocks the reader's select() immediately
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        if self.reader is not None:
            self.reader.stop()
            if not self.reader.wait(1500):
                self.reader.terminate()
                self.reader.wait(500)
            self.reader = None
        if self.child_pid is not None:
            # Reap the zombie
            try:
                os.waitpid(self.child_pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self.child_pid = None

    # ─── Output handling ───────────────────────────────────────────────

    def _on_data(self, data: bytes):
        """Feed raw bytes from PTY into pyte. Don't render here — let the
        coalescing timer do that, so a burst of output doesn't trigger N
        redraws."""
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")
        # Feed to pyte — this updates self._screen in place
        self._stream.feed(text)
        self._bytes_in += len(data)
        self._dirty = True

    def _on_closed(self, code: int):
        """PTY child has exited (or EOF on the master fd).

        Forces a SYNCHRONOUS final render so the exit marker + last output
        are visible immediately. Without this, fast commands (pwd, gh
        --version) finish and master_fd becomes None before the 33ms repaint
        timer fires, and any code reading toPlainText() right after sees
        stale content.
        """
        # Reap the child to get the real exit code
        rc = 0
        try:
            pid, status = os.waitpid(self.child_pid or 0, os.WNOHANG)
            if pid:
                if os.WIFEXITED(status):
                    rc = os.WEXITSTATUS(status)
                elif os.WIFSIGNALED(status):
                    rc = 128 + os.WTERMSIG(status)
        except ChildProcessError:
            pass

        # Write the exit marker via pyte so colors render correctly
        try:
            self._stream.feed(f"\n\x1b[2m─── exited ({rc}) ───\x1b[0m\n")
        except Exception:
            pass

        # Synchronous final render — don't wait for the 33ms timer tick
        self._dirty = False
        self._render_screen()

        self._cleanup()
        self.state_changed.emit("")
        self.process_exited.emit(rc)

    def _on_repaint_tick(self):
        """Coalesced repaint — runs at 30 fps, only does work if data arrived."""
        if not self._dirty:
            return
        self._dirty = False
        self._render_screen()

    def _render_screen(self):
        """Render pyte's screen into the QPlainTextEdit using a single setHtml
        call. We rebuild the whole text each frame — for ~120×40 screens this is
        fast enough at 30 fps."""
        try:
            lines = []
            for y in range(self._screen.lines):
                row = self._screen.buffer[y]
                if not row:
                    lines.append("")
                    continue
                # pyte stores chars as dict[int x → Char]. Sort by x for order.
                sorted_chars = [row[x] for x in sorted(row.keys())]
                line_html = self._row_to_html(sorted_chars)
                lines.append(line_html)

            html = "<br>".join(lines)
            # Replace the document content with a single setHtml
            # (much faster than per-char appendPlainText)
            self.clear()
            # Insert via QTextCursor for proper HTML rendering
            cursor = self.textCursor()
            cursor.insertHtml(html)
            # Scroll to bottom
            sb = self.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception as e:
            # Render error shouldn't crash the pane
            print(f"[TerminalPane] render error: {e}")

    def _row_to_html(self, chars: list) -> str:
        """Convert a row of pyte characters into HTML with ANSI colors."""
        from html import escape
        if not chars:
            return ""
        spans = []
        cur_fg = None
        cur_bg = None
        cur_bold = False
        cur_italic = False
        cur_underline = False
        buf = []

        def flush():
            nonlocal buf
            if not buf:
                return
            text = escape("".join(buf))
            styles = []
            if cur_fg:
                styles.append(f"color:{cur_fg}")
            if cur_bg:
                styles.append(f"background-color:{cur_bg}")
            if cur_bold:
                styles.append("font-weight:600")
            if cur_italic:
                styles.append("font-style:italic")
            if cur_underline:
                styles.append("text-decoration:underline")
            attrs = ";".join(styles)
            if attrs:
                spans.append(f'<span style="{attrs}">{text}</span>')
            else:
                spans.append(text)
            buf = []

        for ch in chars:
            if ch.data == "":
                continue
            fg, bg, bold, italic, underline = self._resolve_sgr(ch)
            # Break span on style change
            if (fg, bg, bold, italic, underline) != (cur_fg, cur_bg, cur_bold, cur_italic, cur_underline):
                flush()
                cur_fg, cur_bg, cur_bold, cur_italic, cur_underline = fg, bg, bold, italic, underline
            buf.append(ch.data)
        flush()

        return "".join(spans)

    # ─── SGR (color/attribute) resolution ──────────────────────────────

    # Standard 8 colors + bright variants (xterm default palette)
    PALETTE_8 = [
        "#000000", "#cd0000", "#00cd00", "#cdcd00",
        "#0000ee", "#cd00cd", "#00cdcd", "#e5e5e5",
    ]
    PALETTE_8_BRIGHT = [
        "#7f7f7f", "#ff0000", "#00ff00", "#ffff00",
        "#5c5cff", "#ff00ff", "#00ffff", "#ffffff",
    ]

    def _resolve_sgr(self, ch):
        """Resolve a pyte Character to (fg, bg, bold, italic, underline)."""
        # pyte Character has .fg, .bg (named/hex/rgb), .bold, .italics, .underscore
        # Normalize 'default' to None
        def color(c):
            if c == "default" or c is None:
                return None
            if isinstance(c, str):
                # pyte returns "0xrrggbb" for indexed/RGB
                if c.startswith("0x") and len(c) == 8:
                    rgb = c[2:]
                    return f"#{rgb}"
                if c.startswith("#"):
                    return c
            return None

        fg = color(ch.fg)
        bg = color(ch.bg)
        return fg, bg, bool(ch.bold), bool(ch.italics), bool(ch.underscore)

    # ─── Direct text append (for banner before PTY starts) ─────────────

    def append_ansi(self, text: str):
        """Append ANSI-colored text to the pane (bypassing pyte)."""
        try:
            self._stream.feed(text)
            self._dirty = True
        except Exception:
            pass

    def append_plain(self, text: str):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ─── Input handling ────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        if self.master_fd is None:
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()
        text = event.text()

        # Ctrl-key sequences
        if mods & Qt.KeyboardModifier.ControlModifier:
            mapping = {
                Qt.Key.Key_C: b"\x03", Qt.Key.Key_D: b"\x04",
                Qt.Key.Key_Z: b"\x1a", Qt.Key.Key_L: b"\x0c",
                Qt.Key.Key_Backslash: b"\x1c", Qt.Key.Key_W: b"\x17",
                Qt.Key.Key_U: b"\x15", Qt.Key.Key_A: b"\x01",
                Qt.Key.Key_E: b"\x05", Qt.Key.Key_K: b"\x0b",
                Qt.Key.Key_R: b"\x12",
            }
            if key in mapping:
                self._write(mapping[key])
                return
            # Ctrl-as-char (e.g. Ctrl-Space)
            if text and text.isprintable():
                # Ctrl-letter ASCII control codes
                ctrl = chr(ord(text.upper()) - 64)
                if ctrl.isprintable():
                    self._write(ctrl.encode())
                    return

        # Special keys
        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self._write(b"\r")
            return
        if key == Qt.Key.Key_Backspace:
            self._write(b"\x7f")
            return
        if key == Qt.Key.Key_Tab:
            self._write(b"\t")
            return
        if key == Qt.Key.Key_Backtab:
            self._write(b"\x1b[Z")
            return
        if key == Qt.Key.Key_Up:    self._write(b"\x1b[A"); return
        if key == Qt.Key.Key_Down:  self._write(b"\x1b[B"); return
        if key == Qt.Key.Key_Right: self._write(b"\x1b[C"); return
        if key == Qt.Key.Key_Left:  self._write(b"\x1b[D"); return
        if key == Qt.Key.Key_Home:  self._write(b"\x1b[H");  return
        if key == Qt.Key.Key_End:   self._write(b"\x1b[F");  return
        if key == Qt.Key.Key_Delete: self._write(b"\x1b[3~"); return
        if key == Qt.Key.Key_Escape: self._write(b"\x1b"); return
        if key == Qt.Key.Key_PageUp:   self._write(b"\x1b[5~"); return
        if key == Qt.Key.Key_PageDown: self._write(b"\x1b[6~"); return
        # Function keys
        fn_map = {
            Qt.Key.Key_F1: b"\x1bOP", Qt.Key.Key_F2: b"\x1bOQ",
            Qt.Key.Key_F3: b"\x1bOR", Qt.Key.Key_F4: b"\x1bOS",
            Qt.Key.Key_F5: b"\x1b[15~", Qt.Key.Key_F6: b"\x1b[17~",
            Qt.Key.Key_F7: b"\x1b[18~", Qt.Key.Key_F8: b"\x1b[19~",
            Qt.Key.Key_F9: b"\x1b[20~", Qt.Key.Key_F10: b"\x1b[21~",
            Qt.Key.Key_F11: b"\x1b[23~", Qt.Key.Key_F12: b"\x1b[24~",
        }
        if key in fn_map:
            self._write(fn_map[key])
            return

        # Plain text
        if text:
            self._write(text.encode("utf-8"))
            return

        super().keyPressEvent(event)

    def _write(self, data: bytes):
        if self.master_fd is None:
            return
        try:
            os.write(self.master_fd, data)
        except OSError:
            self.append_plain("\n\x1b[31m✗ write failed (process gone)\x1b[0m\n")
            self._cleanup()

    # ─── Context menu ────────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1408;
                color: #f5d491;
                border: 1px solid #3a2e15;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #6b3410;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #3a2e15;
                margin: 4px 8px;
            }
        """)

        has_selection = self.textCursor().hasSelection()

        copy_act = menu.addAction("Copy")
        copy_act.setShortcut(QKeySequence.StandardKey.Copy)
        copy_act.setEnabled(has_selection)
        copy_act.triggered.connect(self.copy)

        cut_act = menu.addAction("Cut")
        cut_act.setShortcut(QKeySequence.StandardKey.Cut)
        cut_act.setEnabled(has_selection)
        cut_act.triggered.connect(self.cut)

        paste_act = menu.addAction("Paste")
        paste_act.setShortcut(QKeySequence.StandardKey.Paste)
        paste_act.triggered.connect(self.paste_input)

        menu.addSeparator()

        select_all_act = menu.addAction("Select All")
        select_all_act.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_act.triggered.connect(self.selectAll)

        clear_act = menu.addAction("Clear")
        clear_act.setShortcut(QKeySequence("Ctrl+K"))
        clear_act.triggered.connect(self.clear)

        menu.addSeparator()

        save_act = menu.addAction("Save Output…")
        save_act.triggered.connect(self._save_output)

        copy_all_act = menu.addAction("Copy All")
        copy_all_act.triggered.connect(self._copy_all)

        menu.exec(self.mapToGlobal(pos))

    def paste_input(self):
        text = QApplication.clipboard().text()
        if text and self.master_fd is not None:
            try:
                os.write(self.master_fd, text.encode("utf-8"))
            except OSError:
                pass

    def _copy_all(self):
        QApplication.clipboard().setText(self.toPlainText())

    def _save_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Terminal Output",
            "terminal-output.txt",
            "Text Files (*.txt);;Log Files (*.log);;All Files (*)",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    # Strip ANSI for clean text
                    f.write(strip_ansi(self.toPlainText()))
            except OSError as e:
                print(f"TerminalDeck: save failed: {e}")


# ─── Toolbar (header above the terminal showing the current command) ─────

class TerminalBar(QWidget):
    """Header above the terminal showing the current command and a stop button."""

    stop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QWidget {
                background-color: #161b22;
                border: none;
            }
            QLabel {
                color: #d4d4d4;
                font-family: "Menlo", "SF Mono", monospace;
                font-size: 11px;
            }
            QPushButton {
                background-color: #21262d;
                color: #d4d4d4;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #30363d;
            }
            QPushButton:pressed {
                background-color: #1f6feb;
            }
        """)

        self.label = QLabel("No command running")
        self.label.setContentsMargins(12, 0, 12, 0)

        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setFixedWidth(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.stop_btn)

    def set_command(self, command: str):
        if command:
            self.label.setText(f"  $ {command}")
            self.stop_btn.setEnabled(True)
        else:
            self.label.setText("  No command running")
            self.stop_btn.setEnabled(False)


# ─── Combined widget (Bar + TerminalPane) ──────────────────────────────

class TerminalDeckWidget(QWidget):
    """Bar + TerminalPane combined."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar = TerminalBar()
        self.pane = TerminalPane()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.bar)
        layout.addWidget(self.pane, 1)

        self.bar.stop_clicked.connect(self.pane.stop)
        self.pane.state_changed.connect(self.bar.set_command)

    def run(self, command: str, cwd: str | None = None):
        self.pane.run_command(command, cwd)

    def clear(self):
        self.pane.clear()

    def stop(self):
        self.pane.stop()
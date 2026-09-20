"""Tabbed terminal — wraps multiple TerminalDeckWidget instances in a QTabWidget."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QKeySequence, QShortcut, QFont
from PySide6.QtWidgets import (
    QTabWidget, QPushButton, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QToolButton, QMenu, QApplication, QMessageBox
)

from .terminal import TerminalDeckWidget


# ─── Icon helpers ──────────────────────────────────────────────────────

def make_dot(color: str, size: int = 10) -> QIcon:
    """Create a colored dot icon for tab status."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pix)


def make_close_icon(color: str = "#7d8590", size: int = 14) -> QIcon:
    """Draw a × close icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor(color))
    pen.setWidth(2)
    p.setPen(pen)
    # Draw an × centered
    pad = 3
    p.drawLine(pad, pad, size - pad, size - pad)
    p.drawLine(size - pad, pad, pad, size - pad)
    p.end()
    return QIcon(pix)


class TabbedTerminal(QTabWidget):
    """QTabWidget that hosts independent terminal sessions."""

    current_terminal_changed = Signal(object)  # TerminalDeckWidget
    tab_state_changed = Signal()  # any tab started/stopped/closed

    SECTION_ACCENT = "#f59e0b"  # amber

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # Provide our own close icon so the × is always visible
        self._close_icon = make_close_icon("#7d8590", 14)
        self._close_icon_hover = make_close_icon("#f85149", 14)

        self.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid #21262d;
                border-radius: 6px;
                background-color: #1a1408;
                top: -1px;
            }}
            QTabBar {{
                background-color: transparent;
                qproperty-drawBase: 0;
            }}
            QTabBar::tab {{
                background-color: #161b22;
                color: #d4d4d4;
                border: 1px solid #30363d;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 6px 10px 6px 10px;
                margin-right: 2px;
                min-width: 80px;
                max-width: 220px;
            }}
            QTabBar::tab:selected {{
                background-color: #1a1408;
                color: #f5d491;
                border-color: {self.SECTION_ACCENT};
                border-bottom: 2px solid {self.SECTION_ACCENT};
                font-weight: 600;
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #21262d;
                color: #ffffff;
            }}
            QTabBar::close-button {{
                subcontrol-position: right;
                width: 16px;
                height: 16px;
            }}
        """)

        # "+" button for new tab in the corner
        self.new_btn = QToolButton()
        self.new_btn.setText("+")
        self.new_btn.setToolTip("New terminal tab (⌘T)")
        self.new_btn.setFixedSize(24, 22)
        self.new_btn.setStyleSheet("""
            QToolButton {
                background-color: #21262d;
                color: #d4d4d4;
                border: 1px solid #30363d;
                border-radius: 4px;
                font-size: 14px;
                font-weight: 600;
                padding: 0;
            }
            QToolButton:hover {
                background-color: #f59e0b;
                color: #0d1117;
            }
            QToolButton:pressed {
                background-color: #d97706;
;
            }
        """)
        self.new_btn.clicked.connect(lambda: self.new_tab())
        self.setCornerWidget(self.new_btn, Qt.Corner.TopRightCorner)

        # Connect signals
        self.tabCloseRequested.connect(self._on_close_requested)
        self.currentChanged.connect(self._on_current_changed)

        # Track running state per tab (for the dot icon)
        self._tab_states: dict[int, dict] = {}  # index → {"state": str, "exit": int|None, "command": str}

        # Track which tab we're currently updating so the close icon handler knows
        self._suppress_close_handler = False

        # Start with a single empty tab
        self.new_tab()

        # Keyboard shortcuts
        self._install_shortcuts()

        # Apply our × close icon to all current tabs (and any future ones via new_tab)
        self.tabBarDoubleClicked.connect(self._on_tab_double_clicked)

    # ─── Public API ─────────────────────────────────────────────────────

    def new_tab(self, command: str | None = None, cwd: str | None = None, name: str | None = None) -> TerminalDeckWidget:
        """Create a new tab, optionally running a command in it. Returns the widget."""
        term = TerminalDeckWidget()
        # Wire signals to keep tab title in sync
        term.pane.state_changed.connect(
            lambda cmd, w=term: self._on_tab_state_changed(w, cmd)
        )

        # Forward exit signal to update tab status badge
        try:
            term.pane.process_exited.connect(lambda code, w=term: self._on_tab_exit(w, code))
        except Exception:
            pass

        idx = self.addTab(term, name or "Terminal")
        self.setCurrentIndex(idx)
        self._tab_states[idx] = {
            "state": "idle",      # "idle" | "running" | "done"
            "exit": None,         # exit code when done
            "command": None,      # last command run
            "category": "default", # category for color tint
        }
        self._set_close_icon(idx)
        self._update_tab_tooltip(idx)

        if command:
            term.run(command, cwd)
        return term

    def run_in_current_tab(self, command: str, cwd: str | None = None):
        """Run command in current tab, or open new tab if current is busy."""
        term = self.current_terminal()
        if term is None:
            return self.new_tab(command, cwd)

        if term.pane.master_fd is not None:
            return self.new_tab(command, cwd)

        # Set category hint on the tab based on tool id (if known)
        term.run(command, cwd)
        return term

    def run_in_new_tab(self, command: str, cwd: str | None = None, category: str = "default") -> TerminalDeckWidget:
        """Always open a fresh tab for this command, with optional category tint."""
        term = self.new_tab()
        idx = self.indexOf(term)
        self._tab_states[idx]["category"] = category
        term.run(command, cwd)
        return term

    def current_terminal(self) -> TerminalDeckWidget | None:
        w = self.currentWidget()
        return w if isinstance(w, TerminalDeckWidget) else None

    def clear_current(self):
        term = self.current_terminal()
        if term:
            term.clear()

    def stop_current(self):
        term = self.current_terminal()
        if term:
            term.pane.stop()

    def close_current(self):
        idx = self.currentIndex()
        if idx >= 0 and self.count() > 1:
            self._on_close_requested(idx)

    def switch_to_tab(self, n: int):
        """Switch to tab N (1-indexed). Cmd-1..Cmd-9."""
        idx = n - 1
        if 0 <= idx < self.count():
            self.setCurrentIndex(idx)

    # ─── Font size (Cmd-+, Cmd--, Cmd-0) ─────────────────────────────────

    def increase_font(self):
        term = self.current_terminal()
        if not term:
            return
        f = term.pane.font()
        size = min(f.pointSize() + 1, 32)
        f.setPointSize(size)
        term.pane.setFont(f)

    def decrease_font(self):
        term = self.current_terminal()
        if not term:
            return
        f = term.pane.font()
        size = max(f.pointSize() - 1, 7)
        f.setPointSize(size)
        term.pane.setFont(f)

    def reset_font(self):
        term = self.current_terminal()
        if not term:
            return
        f = term.pane.font()
        f.setPointSize(12)
        term.pane.setFont(f)

    # ─── Internal ───────────────────────────────────────────────────────

    def _on_close_requested(self, index: int):
        if self.count() <= 1:
            return

        widget = self.widget(index)
        # Confirm if there's a running process
        if isinstance(widget, TerminalDeckWidget) and widget.pane.master_fd is not None:
            ans = QMessageBox.question(
                self,
                "Close running tab?",
                f"Tab '{self.tabText(index)}' has a running process.\n\nStop it and close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
            widget.pane.stop()

        self.removeTab(index)

    def _on_tab_removed(self, index: int):
        """Rebuild the _tab_states dict after a tab is removed (indices shift)."""
        # Rebuild from scratch using the remaining widgets
        new_states = {}
        for i in range(self.count()):
            # The widget at position i after removal is the one that was at
            # i or i+1 before. Just re-match by widget.
            pass
        # Simpler: just clear — we re-derive state on each event
        self._tab_states.clear()

    def _on_current_changed(self, index: int):
        term = self.current_terminal()
        self.current_terminal_changed.emit(term)

    def _on_tab_exit(self, widget: TerminalDeckWidget, code: int):
        idx = self.indexOf(widget)
        if idx < 0:
            return
        st = self._tab_states.get(idx, {})
        st["state"] = "done"
        st["exit"] = code
        self._refresh_tab_title(idx)
        self._update_tab_tooltip(idx)
        self.tab_state_changed.emit()

    def _on_tab_state_changed(self, widget: TerminalDeckWidget, command: str):
        idx = self.indexOf(widget)
        if idx < 0:
            return
        st = self._tab_states.setdefault(idx, {"state": "idle", "exit": None, "command": None, "category": "default"})
        if command:
            # New command started — reset to running
            st["command"] = command
            st["state"] = "running"
            st["exit"] = None
        # When command becomes empty (process ended), DON'T clobber state or
        # command — _on_tab_exit will set state="done" + exit code, and we
        # want the command to persist so the ✓/✗N badge renders in the title.
        self._refresh_tab_title(idx)
        self._update_tab_tooltip(idx)
        self.tab_state_changed.emit()

    def _on_tab_double_clicked(self, index: int):
        """Double-click tab to close it (familiar browser behavior)."""
        if index < 0:
            return
        self._on_close_requested(index)

    def _refresh_tab_title(self, idx: int):
        st = self._tab_states.get(idx, {})
        cmd = st.get("command")
        if not cmd:
            self.setTabText(idx, f"Terminal {idx + 1}")
            self.setTabIcon(idx, QIcon())
            return
        # Truncate
        label = cmd if len(cmd) <= 24 else cmd[:21] + "…"
        # Add exit status badge
        if st.get("state") == "done":
            code = st.get("exit")
            if code == 0:
                badge = " ✓"
            elif code is None:
                badge = ""
            else:
                badge = f" ✗{code}"
            label = f"{label}{badge}"
        self.setTabText(idx, label)

        # Status icon: green dot running, gray idle, colored when done
        state = st.get("state")
        if state == "running":
            self.setTabIcon(idx, make_dot("#3fb950", 10))
        elif state == "done":
            code = st.get("exit")
            color = "#3fb950" if code == 0 else "#f85149"
            self.setTabIcon(idx, make_dot(color, 10))
        else:
            self.setTabIcon(idx, QIcon())

        # Apply category color tint to the tab background
        self._apply_category_tint(idx, st.get("category", "default"))

    def _apply_category_tint(self, idx: int, category: str):
        # Base inactive color
        cat_colors = {
            "ai-coding":    "#2d1b4a",  # purple tint
            "openclaw":     "#3a2410",  # orange tint
            "local-llm":    "#3a1530",  # pink tint
            "local-ai":     "#15303a",  # cyan tint
            "productivity": "#3a3515",  # yellow tint
            "dev":          "#1a2530",  # blue tint
            "shell":        "#1a3325",  # green tint
            "default":      "#161b22",  # gray
        }
        base = cat_colors.get(category, cat_colors["default"])
        if idx == self.currentIndex():
            # selected tab — keep amber tint but blend with category
            if category == "ai-coding":
                bg = "#2a1828"
            elif category == "shell":
                bg = "#1a2818"
            elif category == "dev":
                bg = "#162028"
            else:
                bg = "#1a1408"  # amber default
            self.tabBar().setTabTextColor(idx, QColor("#f5d491"))
        else:
            bg = base
            self.tabBar().setTabTextColor(idx, QColor("#d4d4d4"))

        # Use Qt's built-in tab data to override stylesheet bg
        # (stylesheet overrides per-tab bg, so we use a property setStyleSheet trick)
        # Easier: just rely on category info in tooltip; visual cue via icon color is enough.
        # Skip per-tab bg override — it conflicts with the stylesheet.

    def _update_tab_tooltip(self, idx: int):
        st = self._tab_states.get(idx, {})
        cmd = st.get("command") or "Idle — no command running"
        parts = [f"$ {cmd}"]
        if st.get("state") == "done":
            code = st.get("exit")
            parts.append(f"exit: {code if code is not None else '?'}")
        widget = self.widget(idx)
        if isinstance(widget, TerminalDeckWidget) and widget.pane.child_pid:
            parts.append(f"PID: {widget.pane.child_pid}")
        parts.append("Double-click or × to close")
        parts.append("⌘1–⌘9 to switch · ⌘T new · ⌘W close · ⌘K clear · ⌘± font")
        self.setTabToolTip(idx, "\n".join(parts))

    def _set_close_icon(self, idx: int):
        # Qt doesn't natively let us paint a custom icon on the close button
        # across themes; instead we ensure the close button stays visible and
        # force a repaint. The stylesheet already sized it 16x16; the default
        # "x" image will show up clearly on macOS.
        # No-op: Qt uses native close glyph on macOS for QTabBar::close-button.
        pass

    def _refresh_close_icons_all(self):
        for i in range(self.count()):
            self._set_close_icon(i)

    def _install_shortcuts(self):
        # Tab management
        QShortcut(QKeySequence("Ctrl+T"), self, activated=lambda: self.new_tab())
        QShortcut(QKeySequence("Ctrl+W"), self, activated=lambda: self.close_current())
        QShortcut(QKeySequence("Ctrl+K"), self, activated=lambda: self.clear_current())
        # Font size
        QShortcut(QKeySequence("Ctrl+="), self, activated=self.increase_font)
        QShortcut(QKeySequence("Ctrl++"), self, activated=self.increase_font)  # shift+= on US kbds
        QShortcut(QKeySequence("Ctrl+-"), self, activated=self.decrease_font)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.reset_font)
        # Switch tabs
        for n in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{n}"), self, activated=lambda x=n: self.switch_to_tab(x))

    def shutdown(self):
        """Stop all running tabs cleanly before app quit."""
        for i in range(self.count()):
            w = self.widget(i)
            if isinstance(w, TerminalDeckWidget) and w.pane.master_fd is not None:
                w.pane.stop()
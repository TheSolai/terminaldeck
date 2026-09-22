"""Main window — sidebar + tool list + built-in terminal pane."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QThreadPool, QRunnable, Slot, Signal, QObject, QTimer, QSize, QPoint
from PySide6.QtGui import (
    QAction, QFont, QFontDatabase, QIcon, QKeySequence, QShortcut,
    QTextCursor, QColor
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLineEdit, QLabel, QPushButton,
    QSplitter, QFrame, QStatusBar, QToolBar, QCheckBox, QSizePolicy, QMenu
)

from . import tools as T
from .terminal import TerminalDeckWidget
from .tabbed import TabbedTerminal
from .launcher import ExternalLauncher


# ─── Background detection worker ───────────────────────────────────────

class DetectionSignals(QObject):
    done = Signal(dict)  # {tool_id: status_dict}


class DetectionWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = DetectionSignals()

    @Slot()
    def run(self):
        # Detect both installed and discover tools in one pass
        all_tools = T.all_tools()
        results = T.detect_all(all_tools)
        self.signals.done.emit(results)


# ─── Tool list widget ──────────────────────────────────────────────────

class ToolList(QListWidget):
    """Filtered, categorized list of tools."""

    tool_activated = Signal(object)  # CLITool
    launch_requested = Signal(object)  # CLITool
    launch_external_requested = Signal(object, str)  # CLITool, terminal ("terminal"|"warp")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._tools: list[T.CLITool] = []
        self._statuses: dict[str, dict] = {}

        self._mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._mono.setPointSize(11)

        self.setStyleSheet("""
            QListWidget {
                background-color: #16102a;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 0;
                border-bottom: 1px solid #22153d;
            }
            QListWidget::item:selected {
                background-color: #3a2263;
                border-left: 3px solid #a371f7;
            }
            QListWidget::item:hover {
                background-color: #22153d;
            }
        """)

        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_item_dbl)

    def set_tools(self, tools: list[T.CLITool]):
        self._tools = tools
        self._rebuild()

    def set_statuses(self, statuses: dict[str, dict]):
        self._statuses = statuses
        self._rebuild()

    def set_filter(self, needle: str, available_only: bool = False, statuses: dict | None = None):
        self._rebuild(needle=needle, available_only=available_only, statuses=statuses)

    def _rebuild(self, needle: str = "", available_only: bool = False, statuses: dict | None = None):
        if statuses is None:
            statuses = self._statuses
        needle = needle.lower().strip()
        self.clear()
        for tool in self._tools:
            # Apply availability filter
            if available_only and not statuses.get(tool.id, {}).get("available"):
                continue
            # Apply needle filter
            if needle:
                haystack = (tool.name + " " + tool.command + " " + tool.description + " " + (tool.model or "")).lower()
                if needle not in haystack:
                    continue
            self._add_item(tool)

    def _add_item(self, tool: T.CLITool):
        item = QListWidgetItem(self)
        item.setData(Qt.ItemDataRole.UserRole, tool)
        # Width fills the available width; height per row
        w = self.viewport().width() or self.width() or 400
        item.setSizeHint(QSize(w, 48))

        widget = ToolRow(tool, self._statuses.get(tool.id))
        # Connect row click to launch
        widget.mouseReleaseEvent = self._make_row_click_handler(tool, widget)
        self.addItem(item)
        self.setItemWidget(item, widget)

    def _make_row_click_handler(self, tool: T.CLITool, widget: ToolRow):
        original = widget.mouseReleaseEvent
        def handler(event):
            original(event)
            if event.button() == Qt.MouseButton.LeftButton:
                self.launch_requested.emit(tool)
                self.tool_activated.emit(tool)
        return handler

    def _on_item_clicked(self, item: QListWidgetItem):
        tool = item.data(Qt.ItemDataRole.UserRole)
        if tool:
            self.tool_activated.emit(tool)

    def _on_item_dbl(self, item: QListWidgetItem):
        tool = item.data(Qt.ItemDataRole.UserRole)
        if tool:
            self.launch_requested.emit(tool)

    def _show_context_menu(self, pos: QPoint):
        """Right-click on a tool row → menu with launch-in-external-terminal options."""
        item = self.itemAt(pos)
        if not item:
            return
        tool: T.CLITool = item.data(Qt.ItemDataRole.UserRole)
        if not tool:
            return

        available = bool(self._statuses.get(tool.id, {}).get("available"))
        cmd = tool.command
        cwd = None
        if tool.id == "learnage":
            cwd = "/Users/amre/Projects/Learnage"

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #16102a;
                color: #d4d4d4;
                border: 1px solid #3a2263;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #3a2263;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #3a2263;
                margin: 4px 8px;
            }
            QMenu::item:disabled {
                color: #4b525b;
            }
        """)

        title = menu.addAction(f"{tool.name}  ·  {cmd}")
        title.setEnabled(False)

        menu.addSeparator()

        open_built = menu.addAction("Launch in built-in terminal")
        open_built.setEnabled(available)
        open_built.triggered.connect(lambda: self.launch_requested.emit(tool))

        open_term = menu.addAction("Open in Terminal.app")
        open_term.triggered.connect(
            lambda: self.launch_external_requested.emit(tool, "terminal")
        )

        open_warp = menu.addAction("Open in Warp")
        open_warp.setEnabled(_launcher_warp_available())
        open_warp.triggered.connect(
            lambda: self.launch_external_requested.emit(tool, "warp")
        )

        menu.addSeparator()

        copy_act = menu.addAction("Copy command")
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText(cmd))

        copy_full = menu.addAction(f"Copy full launch line")
        copy_full.triggered.connect(lambda: QApplication.clipboard().setText(
            f"cd {cwd}" if cwd else cmd
        ))

        menu.exec(self.mapToGlobal(pos))


def _launcher_warp_available() -> bool:
    """Helper — check if Warp is installed (called from context menu)."""
    from terminaldeck.launcher import _is_warp_installed
    return _is_warp_installed()


# ─── Row widget (one tool) ─────────────────────────────────────────────

class ToolRow(QWidget):
    """Compact row showing tool status, name, command, version.
    The whole row is clickable; click triggers launch via parent ToolList."""

    def __init__(self, tool: T.CLITool, status: dict | None, parent=None):
        super().__init__(parent)
        self.tool = tool
        self.status = status or {"available": False, "version": None, "path": None}

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QWidget {
                background: transparent;
            }
            QWidget:hover {
                background-color: #22153d;
            }
            QLabel { color: #d4d4d4; }
            QLabel#name {
                font-size: 12px;
                color: #f0f6fc;
                font-weight: 600;
            }
            QLabel#cmd {
                font-size: 10px;
                font-family: 'Menlo', monospace;
                color: #c4b5fd;
            }
            QLabel#model {
                background-color: #22153d;
                color: #c4b5fd;
                border: 1px solid #3a2263;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
            }
            QLabel#version {
                background-color: #22153d;
                color: #7ee787;
                border: 1px solid #3a2263;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                font-family: 'Menlo', monospace;
                min-width: 80px;
                max-width: 110px;
            }
            QLabel#version_missing {
                background-color: #21262d;
                color: #f85149;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 10px;
                font-family: 'Menlo', monospace;
                min-width: 80px;
                max-width: 110px;
            }
        """)

        # Status dot
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self._update_dot()

        # Name + command (two lines)
        name_lbl = QLabel(tool.name)
        name_lbl.setObjectName("name")
        cmd_lbl = QLabel(tool.command)
        cmd_lbl.setObjectName("cmd")

        name_box = QVBoxLayout()
        name_box.setContentsMargins(0, 0, 0, 0)
        name_box.setSpacing(2)
        name_box.addWidget(name_lbl)
        name_box.addWidget(cmd_lbl)

        # Model chip (only if meaningful)
        self.model_lbl = QLabel()
        self.model_lbl.setObjectName("model")
        if tool.model and tool.model not in ("—", "Various"):
            self.model_lbl.setText(tool.model)
            self.model_lbl.setVisible(True)
        else:
            self.model_lbl.setVisible(False)

        # Version chip
        self.version_lbl = QLabel()
        self.version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_version()

        # Compose
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)
        layout.addWidget(self.dot)
        layout.addLayout(name_box, 1)
        layout.addWidget(self.model_lbl)
        layout.addWidget(self.version_lbl)

        self.setFixedHeight(48)

        # Rich tooltip on the whole row
        self._build_tooltip()

    def _build_tooltip(self):
        """Compose a multi-line tooltip with everything we know about this tool."""
        t = self.tool
        lines = [f"<b style='color:#58a6ff'>{t.name}</b>", t.description]
        lines.append(f"<span style='color:#7d8590'>Command:</span> "
                     f"<tt style='color:#c4b5fd'>{t.command}</tt>")
        if t.model and t.model not in ("—", "Various"):
            lines.append(f"<span style='color:#7d8590'>Model:</span> {t.model}")
        s = self.status
        if s.get("available"):
            v = s.get("version") or "—"
            p = s.get("path") or "?"
            lines.append(f"<span style='color:#7ee787'>● Available</span> · v{v}")
            lines.append(f"<span style='color:#7d8590'>Path:</span> "
                         f"<tt style='color:#c4b5fd'>{p}</tt>")
            lines.append("<span style='color:#7d8590'>Tip:</span> click to launch · right-click for more")
        else:
            lines.append(f"<span style='color:#f85149'>● Not installed</span>")
            if t.install:
                lines.append(f"<span style='color:#7d8590'>Install:</span> "
                             f"<tt style='color:#c4b5fd'>{t.install}</tt>")
            lines.append("<span style='color:#7d8590'>Tip:</span> click to install · right-click for more")
        if t.notes:
            lines.append(f"<i style='color:#7d8590'>{t.notes}</i>")
        self.setToolTip("<div style='line-height:1.4'>" + "<br>".join(lines) + "</div>")

    def _update_dot(self):
        if self.status["available"]:
            color = "#3fb950"  # green
            tip = f"Available at {self.status.get('path', '')}"
        else:
            color = "#f85149"  # red
            tip = "Not installed or broken"
        self.dot.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 5px;
            }}
        """)
        self.dot.setToolTip(tip)

    def _update_version(self):
        v = self.status.get("version")
        if self.status["available"] and v and v != "—":
            self.version_lbl.setObjectName("version")
            self.version_lbl.setText(v[:18])
            self.version_lbl.setStyleSheet("""
                QLabel {
                    background-color: #161b22;
                    color: #7ee787;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    padding: 2px 8px;
                    font-size: 10px;
                    font-family: 'Menlo', monospace;
                }
            """)
            self.version_lbl.setToolTip(self.status.get("path", ""))
        else:
            self.version_lbl.setObjectName("version_missing")
            if self.tool.install:
                self.version_lbl.setText("↓ install")
                self.version_lbl.setStyleSheet("""
                    QLabel {
                        background-color: #1f3a5f;
                        color: #79c0ff;
                        border: 1px solid #1f6feb;
                        border-radius: 8px;
                        padding: 2px 8px;
                        font-size: 10px;
                        font-family: 'Menlo', monospace;
                        font-weight: 600;
                    }
                """)
                self.version_lbl.setToolTip(
                    f"Click to install via:\n  {self.tool.install}"
                )
            else:
                self.version_lbl.setText("missing")
                self.version_lbl.setStyleSheet("""
                    QLabel {
                        background-color: #21262d;
                        color: #f85149;
                        border: 1px solid #30363d;
                        border-radius: 8px;
                        padding: 2px 8px;
                        font-size: 10px;
                        font-family: 'Menlo', monospace;
                    }
                """)
                self.version_lbl.setToolTip("Not installed; no auto-install configured")


# ─── Sidebar (categories) ──────────────────────────────────────────────

class Sidebar(QWidget):
    """Sidebar with two sections: installed tools, and Discover (installable)."""
    category_selected = Signal(object)  # tuple: (section, key) where section in {"installed", "discover"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet("""
            QWidget {
                background-color: #0d1929;
                border: none;
            }
            QListWidget {
                background-color: #0d1929;
                border: none;
                outline: none;
                color: #d4d4d4;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px 12px;
                border-radius: 4px;
                margin: 2px 6px;
            }
            QListWidget::item:selected {
                background-color: #1f6feb;
                color: #ffffff;
            }
            QListWidget::item:hover:!selected {
                background-color: #16243a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)

        title = QLabel("TERMINALDECK")
        title.setStyleSheet("""
            QLabel {
                color: #58a6ff;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.5px;
                padding: 8px 12px;
            }
        """)
        layout.addWidget(title)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        # Items
        self._items: list[tuple[str, str | None, QListWidgetItem]] = []
        # section="installed"
        for cat_key, cat_title in T.CATEGORIES:
            count = sum(1 for t in T.TOOLS if t.category == cat_key)
            label = f"{cat_title}  ({count})" if cat_key is None else f"{cat_title}  ({count})"
            item = QListWidgetItem(label)
            self.list.addItem(item)
            self._items.append(("installed", cat_key, item))

        # Discover section separator (purple accent to differentiate from installed)
        sep = QListWidgetItem("── Discover ──")
        sep.setFlags(Qt.ItemFlag.NoItemFlags)  # not selectable
        sep.setForeground(QColor("#a371f7"))
        bold_font = QFont()
        bold_font.setBold(True)
        sep.setFont(bold_font)
        self.list.addItem(sep)

        # section="discover"
        for cat_key, cat_title in T.DISCOVER_CATEGORIES:
            count = sum(1 for t in T.DISCOVER_TOOLS if t.category == cat_key)
            item = QListWidgetItem(f"{cat_title}  ({count})")
            self.list.addItem(item)
            self._items.append(("discover", cat_key, item))

        self.list.setCurrentRow(0)
        self.list.currentItemChanged.connect(self._on_changed)

        # Footer
        self.status_lbl = QLabel("Detecting tools…")
        self.status_lbl.setStyleSheet("""
            QLabel {
                color: #58a6ff;
                font-size: 10px;
                padding: 8px 12px;
                border-top: 1px solid #1f3a5f;
            }
        """)
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

    def set_status_text(self, text: str):
        self.status_lbl.setText(text)

    def update_counts(self, statuses: dict[str, dict]):
        """Refresh counts in sidebar based on detection results."""
        for i, (section, cat_key, item) in enumerate(self._items):
            if section == "installed":
                count = sum(1 for t in T.TOOLS if t.category == cat_key)
                cat_title = next((t for k, t in T.CATEGORIES if k == cat_key), "All Tools")
            else:
                count = sum(1 for t in T.DISCOVER_TOOLS if t.category == cat_key)
                cat_title = next((t for k, t in T.DISCOVER_CATEGORIES if k == cat_key), "?")
            item.setText(f"{cat_title}  ({count})")

    def _on_changed(self, current, _prev):
        if current is None:
            return
        for section, cat_key, item in self._items:
            if item is current:
                self.category_selected.emit((section, cat_key))
                return


# ─── Main window ───────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TerminalDeck")
        self.resize(1200, 760)
        self.setMinimumSize(900, 540)
        # Mac-native: app stays running when window closed
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setUnifiedTitleAndToolBarOnMac(True)
        self.setStyleSheet("""
            QMainWindow { background-color: #0d1117; }
            QStatusBar { background-color: #0d1929; color: #58a6ff; font-size: 11px; border-top: 1px solid #1f3a5f; }
            QToolBar { background-color: #16102a; border: none; spacing: 4px; padding: 4px; }
            QToolBar QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QToolBar QToolButton:hover {
                background-color: #21262d;
                border: 1px solid #30363d;
            }
        """)

        # ─── Layout: [Sidebar | ToolList | TerminalPane] ──────────────────
        self.sidebar = Sidebar()
        self.tool_list = ToolList()
        self.terminal = TabbedTerminal()

        # Filter bar above tool list
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter tools…")
        self.filter.setStyleSheet("""
            QLineEdit {
                background-color: #0d1117;
                color: #d4d4d4;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #1f6feb; }
        """)
        self.filter.textChanged.connect(self.tool_list.set_filter)

        # Available-only toggle
        self.available_only = QCheckBox("Available only")
        self.available_only.setStyleSheet("""
            QCheckBox { color: #7d8590; font-size: 11px; padding: 4px 8px; }
            QCheckBox::indicator { width: 12px; height: 12px; }
        """)
        self.available_only.stateChanged.connect(self._apply_filters)

        # Tool list container
        tool_container = QWidget()
        tool_layout = QVBoxLayout(tool_container)
        tool_layout.setContentsMargins(0, 0, 0, 0)
        tool_layout.setSpacing(0)

        # Search bar at top of tool list
        search_bar = QWidget()
        search_bar.setStyleSheet("background-color: #22153d; border-bottom: 1px solid #3a2263;")
        sb_layout = QHBoxLayout(search_bar)
        sb_layout.setContentsMargins(8, 6, 8, 6)
        sb_layout.addWidget(self.filter, 1)
        sb_layout.addWidget(self.available_only)
        tool_layout.addWidget(search_bar)

        # Header showing count
        self.list_header = QLabel("")
        self.list_header.setStyleSheet("""
            QLabel {
                background-color: #16102a;
                color: #c4b5fd;
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1px;
                padding: 8px 12px;
                border-bottom: 1px solid #3a2263;
            }
        """)
        tool_layout.addWidget(self.list_header)
        tool_layout.addWidget(self.tool_list, 1)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(tool_container)
        self.splitter.addWidget(self.terminal)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 2)
        self.splitter.setSizes([180, 380, 640])
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #0d1117;
                width: 2px;
            }
            QSplitter::handle:horizontal:hover {
                background-color: #58a6ff;
            }
        """)
        self.setCentralWidget(self.splitter)

        # Status bar
        self.setStatusBar(QStatusBar())

        # Toolbar
        tb = QToolBar()
        tb.setObjectName("MainToolBar")  # required for saveState() / restoreState()
        tb.setMovable(False)
        self.addToolBar(tb)

        refresh_action = QAction("↻ Refresh", self)
        refresh_action.setShortcut(QKeySequence("Ctrl+R"))  # stays Ctrl — Mac convention varies
        refresh_action.setToolTip("Re-detect all tools (Ctrl+R)")
        refresh_action.triggered.connect(self.refresh)
        tb.addAction(refresh_action)

        clear_action = QAction("Clear terminal", self)
        clear_action.setShortcut(QKeySequence("Meta+K"))  # Cmd+K on Mac
        clear_action.setToolTip("Clear current terminal (⌘K)")
        clear_action.triggered.connect(self.terminal.clear_current)
        tb.addAction(clear_action)

        stop_action = QAction("■ Stop", self)
        stop_action.setShortcut(QKeySequence("Meta+C"))  # Cmd+. would be more native but conflicts with copy
        stop_action.setToolTip("Stop current terminal (⌘C)")
        stop_action.triggered.connect(self.terminal.stop_current)
        tb.addAction(stop_action)

        new_tab_action = QAction("New tab", self)
        new_tab_action.setShortcut(QKeySequence("Meta+T"))  # Cmd+T
        new_tab_action.setToolTip("Open new terminal tab (⌘T)")
        new_tab_action.triggered.connect(lambda: self.terminal.new_tab())
        tb.addAction(new_tab_action)

        tb.addSeparator()

        font_up = QAction("Font +", self)
        font_up.setShortcut(QKeySequence("Meta+="))
        font_up.setToolTip("Increase font size (⌘=)")
        font_up.triggered.connect(self.terminal.increase_font)
        tb.addAction(font_up)

        font_down = QAction("Font -", self)
        font_down.setShortcut(QKeySequence("Meta+-"))
        font_down.setToolTip("Decrease font size (⌘-)")
        font_down.triggered.connect(self.terminal.decrease_font)
        tb.addAction(font_down)

        font_reset = QAction("Font 0", self)
        font_reset.setShortcut(QKeySequence("Meta+0"))
        font_reset.setToolTip("Reset font size (⌘0)")
        font_reset.triggered.connect(self.terminal.reset_font)
        tb.addAction(font_reset)

        tb.addSeparator()

        self.model_info = QLabel("")
        self.model_info.setStyleSheet("color: #7d8590; font-size: 11px; padding: 0 8px;")
        tb.addWidget(self.model_info)

        # ─── Native Mac menu bar ──────────────────────────────────────
        self._build_menu_bar()

        # ─── Mac-native shortcut: ⌘F focuses filter, ⌘W closes tab ──
        focus_filter = QAction("Focus filter", self)
        focus_filter.setShortcut(QKeySequence("Meta+F"))
        focus_filter.triggered.connect(lambda: (self.filter.setFocus(), self.filter.selectAll()))
        self.addAction(focus_filter)

        clear_filter = QAction("Clear filter", self)
        clear_filter.setShortcut(QKeySequence("Escape"))
        clear_filter.triggered.connect(lambda: (
            self.filter.clear(),
            self.available_only.setChecked(False),
            self.tool_list.setFocus(),
        ))
        self.addAction(clear_filter)

        launch_sel = QAction("Launch selected", self)
        launch_sel.setShortcut(QKeySequence("Meta+Return"))
        launch_sel.triggered.connect(self._launch_selected)
        self.addAction(launch_sel)

        launch_sel_shift = QAction("Launch selected in new tab", self)
        launch_sel_shift.setShortcut(QKeySequence("Meta+Shift+Return"))
        launch_sel_shift.triggered.connect(self._launch_selected_new_tab)
        self.addAction(launch_sel_shift)

        # Tab switching: ⌘1..⌘9
        for i in range(1, 10):
            act = QAction(f"Tab {i}", self)
            act.setShortcut(QKeySequence(f"Meta+{i}"))
            act.triggered.connect(lambda _, n=i: self.terminal.switch_to_tab(n))
            self.addAction(act)

        # Wiring
        self.tool_list.tool_activated.connect(self._on_tool_selected)
        self.tool_list.launch_requested.connect(self._launch)
        self.tool_list.launch_external_requested.connect(self._launch_external)
        self.sidebar.category_selected.connect(self._on_category_changed)
        self.tool_list.itemClicked.connect(lambda _: self._update_header())

        # Persist filter/category changes
        self.filter.textChanged.connect(lambda *_: self._save_session())
        self.available_only.stateChanged.connect(lambda *_: self._save_session())
        self.sidebar.category_selected.connect(lambda *_: self._save_session())

        # Title bar updates when any tab's state changes
        self.terminal.tab_state_changed.connect(self._update_title_bar)
        self._update_title_bar()

        # External terminal launcher (Terminal.app / Warp)
        self._external_launcher = ExternalLauncher()
        self._external_launcher.launched_in_terminal.connect(
            lambda cmd: self.statusBar().showMessage(f"Opened {cmd} in Terminal.app", 4000)
        )
        self._external_launcher.launched_in_warp.connect(
            lambda cmd: self.statusBar().showMessage(f"Opened {cmd} in Warp", 4000)
        )
        self._external_launcher.launch_failed.connect(
            lambda cmd, err: self.statusBar().showMessage(f"Failed: {err}", 6000)
        )

        # State
        self._selected_tool: T.CLITool | None = None
        self._selected_category: tuple[str, str | None] = ("installed", None)
        self._statuses: dict[str, dict] = {}
        self._discover_statuses: dict[str, dict] = {}

        # Restore last session from QSettings (selected category, filter)
        self._restore_session()

        # Apply initial filter
        self._apply_filters()

        # Detect tools in background
        self._run_detection()

    # ─── Detection ─────────────────────────────────────────────────────

    def _run_detection(self):
        self.sidebar.set_status_text("Detecting tools…")
        worker = DetectionWorker()
        worker.signals.done.connect(self._on_detection_done)
        QThreadPool.globalInstance().start(worker)

    def _on_detection_done(self, statuses: dict):
        # Split: installed tools go in _statuses, discover tools go in _discover_statuses
        self._statuses = {tid: s for tid, s in statuses.items() if tid in {t.id for t in T.TOOLS}}
        self._discover_statuses = {tid: s for tid, s in statuses.items() if tid in {t.id for t in T.DISCOVER_TOOLS}}
        available = sum(1 for s in self._statuses.values() if s["available"])
        discover_available = sum(1 for s in self._discover_statuses.values() if s["available"])
        self.sidebar.set_status_text(
            f"{available}/{len(self._statuses)} installed · {discover_available} of {len(self._discover_statuses)} discover"
        )
        self.sidebar.update_counts(statuses)
        self.statusBar().showMessage(
            f"Detection complete — {available}/{len(self._statuses)} installed, "
            f"{discover_available}/{len(self._discover_statuses)} discoverable",
            5000,
        )
        self._apply_filters()

    # ─── Filtering ─────────────────────────────────────────────────────

    def _on_category_changed(self, payload):
        # payload = (section, category_key)
        self._selected_category = payload
        self._apply_filters()

    def _apply_filters(self):
        needle = self.filter.text().strip().lower()
        available_only = self.available_only.isChecked()
        section, cat_key = self._selected_category

        if section == "installed":
            pool = T.TOOLS
            statuses = self._statuses
        else:
            pool = T.DISCOVER_TOOLS
            statuses = self._discover_statuses

        # Compute the FULL pool for this category — we hand the complete
        # unfiltered list to the tool list, then layer the needle filter on top
        # via set_filter(). This way clearing the search text always restores the
        # full category list even if _apply_filters was called while a needle
        # was active.
        full_pool = [tool for tool in pool if not cat_key or tool.category == cat_key]

        # Apply availability + needle filters only for display
        if available_only:
            visible = [t for t in full_pool if statuses.get(t.id, {}).get("available")]
            visible = [t for t in visible if self._matches(t, needle)]
        else:
            visible = [t for t in full_pool if self._matches(t, needle)]

        # Hand the full pool to the tool list so it has something to filter,
        # then call set_filter() to actually apply the search + availability.
        self.tool_list.set_tools(full_pool)
        self.tool_list.set_statuses(statuses)
        self.tool_list.set_filter(needle, available_only=available_only, statuses=statuses)
        self._update_header()
        # Visible count = what's currently shown in the list (post-filter)
        self._visible_count = self.tool_list.count()

    @staticmethod
    def _matches(tool: T.CLITool, needle: str) -> bool:
        if not needle:
            return True
        haystack = (tool.name + " " + tool.command + " " + tool.description + " " + (tool.model or "")).lower()
        return needle in haystack

    def _update_header(self):
        n = self.tool_list.count()
        visible = getattr(self, "_visible_count", n)
        section, cat_key = self._selected_category
        # Show visible count when filtered, full count otherwise
        display_n = visible if visible != n else n
        suffix = f"  ·  {display_n}/{n}" if visible != n else f"  ·  {n}"
        if section == "discover":
            cat_title = next((t for k, t in T.DISCOVER_CATEGORIES if k == cat_key), "Discover")
            self.list_header.setText(f"DISCOVER · {cat_title.upper()}{suffix} TOOLS")
            self.list_header.setStyleSheet("""
                QLabel {
                    background-color: #1f2d3d;
                    color: #79c0ff;
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 1px;
                    padding: 8px 12px;
                    border-bottom: 1px solid #161b22;
                }
            """)
        else:
            if cat_key:
                cat_title = next((t for k, t in T.CATEGORIES if k == cat_key), "Unknown")
                self.list_header.setText(f"{cat_title.upper()}{suffix} TOOLS")
            else:
                self.list_header.setText(f"ALL TOOLS{suffix} TOOLS")
            self.list_header.setStyleSheet("""
                QLabel {
                    background-color: #0d1117;
                    color: #7d8590;
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 1px;
                    padding: 8px 12px;
                    border-bottom: 1px solid #161b22;
                }
            """)

        # Empty-state hint when filter has zero matches
        if visible == 0 and n > 0:
            needle = self.filter.text().strip()
            if needle:
                self.statusBar().showMessage(
                    f"No tools match \"{needle}\". Press Esc to clear the filter.", 6000
                )
            elif self.available_only.isChecked():
                self.statusBar().showMessage(
                    "No installed tools in this category. Toggle 'Available only' off to see all.", 6000
                )

    # ─── Launch ─────────────────────────────────────────────────────────

    def _on_tool_selected(self, tool: T.CLITool):
        self._selected_tool = tool
        # Update the model info bar
        model_text = f"  {tool.name}  ·  {tool.command}"
        if tool.model and tool.model != "—":
            model_text += f"  ·  {tool.model}"
        if tool.notes:
            model_text += f"  ·  ⚠ {tool.notes}"
        self.model_info.setText(model_text)

    def launch(self, tool: T.CLITool):
        self._launch(tool)

    def _launch(self, tool: T.CLITool):
        self._selected_tool = tool
        status = self._statuses.get(tool.id, {})
        available = status.get("available", False)

        if not available:
            # Tool is missing — try to install if we know how
            if tool.install:
                self._install(tool)
                return
            else:
                self.statusBar().showMessage(
                    f"{tool.command} is not installed and no auto-install is configured",
                    4000,
                )
                return

        # Special handling for known multi-action tools
        cmd = tool.command
        category = tool.category

        # Always open a fresh tab so each tool has its own session + category color
        if tool.id == "learnage":
            cwd = "/Users/amre/Projects/Learnage"
            self.terminal.run_in_new_tab(
                f"cd {cwd} && source .venv/bin/activate && learnage", cwd, category
            )
        elif tool.id == "opencode":
            self.terminal.run_in_new_tab("opencode", None, category)
        elif tool.id == "kilocode":
            self.terminal.run_in_new_tab("kilocode", None, category)
        elif tool.id == "mission-control":
            self.terminal.run_in_new_tab("mission-control", None, category)
        elif tool.id == "ocm":
            self.terminal.run_in_new_tab("ocm", None, category)
        else:
            self.terminal.run_in_new_tab(cmd, None, category)

        self.statusBar().showMessage(f"Launched {tool.command} in new tab", 3000)

    def _launch_external(self, tool: T.CLITool, target: str):
        """Launch tool in external Terminal.app or Warp via AppleScript.

        target is 'terminal' or 'warp'.
        """
        self._selected_tool = tool

        # Build the launch command — same customizations as built-in tab
        cmd = tool.command
        cwd = None
        if tool.id == "learnage":
            cwd = "/Users/amre/Projects/Learnage"
            cmd = f"cd {cwd} && source .venv/bin/activate && learnage"
        elif tool.id == "opencode":
            pass
        elif tool.id == "kilocode":
            pass
        elif tool.id == "mission-control":
            pass
        elif tool.id == "ocm":
            pass

        # If tool isn't installed and has an install cmd, we still let the
        # user open it in an external terminal — they'll see "command not found"
        # in the terminal and can run the install manually. Don't gate on availability.

        self._external_launcher.launch(target, cmd, cwd)

    def _install(self, tool: T.CLITool):
        """Run the install command in a fresh tab (shell category), then refresh."""
        # Pick a category that suggests this is a setup/install task
        install_cat = tool.category if tool.category in ("dev", "shell", "ai-coding") else "shell"
        term = self.terminal.new_tab(name=f"Install {tool.command}", cwd=None)
        idx = self.terminal.indexOf(term)
        self.terminal._tab_states[idx]["category"] = install_cat
        term.pane.append_ansi(
            f"\n\x1b[1;33m⚡ Installing {tool.name} ({tool.command})…\x1b[0m\n"
            f"\x1b[2m$ {tool.install}\x1b[0m\n\n"
        )
        term.run(tool.install)
        self.statusBar().showMessage(
            f"Installing {tool.command}… (auto-refresh in 30s)",
            5000,
        )
        # Schedule a refresh after the install (best-effort: 30s)
        QTimer.singleShot(30_000, self.refresh)

    def refresh(self):
        self._statuses = {}
        self._discover_statuses = {}
        self._run_detection()

    # ─── Menu bar (native Mac) ────────────────────────────────────────
    def _build_menu_bar(self):
        """Build a native macOS menu bar. Qt automatically gets us Cmd+Q,
        Cmd+H, Cmd+W from the system — we just provide app-specific items."""
        menubar = self.menuBar()
        menubar.setNativeMenuBar(True)

        # ─── App menu (gets renamed to the app name automatically) ─
        app_menu = menubar.addMenu("TerminalDeck")
        about_act = QAction("About TerminalDeck", self)
        about_act.triggered.connect(self._show_about)
        app_menu.addAction(about_act)
        app_menu.addSeparator()
        prefs_act = QAction("Preferences…", self)
        prefs_act.setShortcut(QKeySequence("Meta+,"))
        prefs_act.triggered.connect(self._show_preferences)
        app_menu.addAction(prefs_act)
        app_menu.addSeparator()
        quit_act = QAction("Quit TerminalDeck", self)
        quit_act.setShortcut(QKeySequence("Meta+Q"))
        quit_act.setMenuRole(QAction.MenuRole.QuitRole)
        quit_act.triggered.connect(self.close)
        app_menu.addAction(quit_act)

        # ─── File menu ──────────────────────────────────────────────
        file_menu = menubar.addMenu("File")
        new_tab = QAction("New Tab", self)
        new_tab.setShortcut(QKeySequence("Meta+T"))
        new_tab.triggered.connect(lambda: self.terminal.new_tab())
        file_menu.addAction(new_tab)
        close_tab = QAction("Close Tab", self)
        close_tab.setShortcut(QKeySequence("Meta+W"))
        close_tab.triggered.connect(self.terminal.close_current)
        file_menu.addAction(close_tab)
        duplicate_tab = QAction("Duplicate Tab", self)
        duplicate_tab.setShortcut(QKeySequence("Meta+D"))
        duplicate_tab.triggered.connect(self.terminal.duplicate_current)
        file_menu.addAction(duplicate_tab)
        restart_tab = QAction("Restart Current Tab", self)
        restart_tab.setShortcut(QKeySequence("Meta+Shift+R"))
        restart_tab.triggered.connect(self.terminal.restart_current)
        file_menu.addAction(restart_tab)
        file_menu.addSeparator()
        refresh = QAction("Re-detect Tools", self)
        refresh.setShortcut(QKeySequence("Ctrl+R"))
        refresh.triggered.connect(self.refresh)
        file_menu.addAction(refresh)

        # ─── Edit menu (so standard Cmd+C/V/X work + clear terminal) ──
        edit_menu = menubar.addMenu("Edit")
        clear = QAction("Clear Terminal", self)
        clear.setShortcut(QKeySequence("Meta+K"))
        clear.triggered.connect(self.terminal.clear_current)
        edit_menu.addAction(clear)
        stop = QAction("Stop Process", self)
        stop.setShortcut(QKeySequence("Meta+C"))
        stop.triggered.connect(self.terminal.stop_current)
        edit_menu.addAction(stop)
        edit_menu.addSeparator()
        find = QAction("Find / Filter", self)
        find.setShortcut(QKeySequence("Meta+F"))
        find.triggered.connect(lambda: (self.filter.setFocus(), self.filter.selectAll()))
        edit_menu.addAction(find)

        # ─── View menu ──────────────────────────────────────────────
        view_menu = menubar.addMenu("View")
        f_up = QAction("Increase Font Size", self)
        f_up.setShortcut(QKeySequence("Meta+="))
        f_up.triggered.connect(self.terminal.increase_font)
        view_menu.addAction(f_up)
        f_down = QAction("Decrease Font Size", self)
        f_down.setShortcut(QKeySequence("Meta+-"))
        f_down.triggered.connect(self.terminal.decrease_font)
        view_menu.addAction(f_down)
        f_reset = QAction("Reset Font Size", self)
        f_reset.setShortcut(QKeySequence("Meta+0"))
        f_reset.triggered.connect(self.terminal.reset_font)
        view_menu.addAction(f_reset)

        # ─── Window menu ────────────────────────────────────────────
        win_menu = menubar.addMenu("Window")
        # Qt's Mac standard "Minimize / Zoom" appear automatically

        # ─── Help menu ──────────────────────────────────────────────
        help_menu = menubar.addMenu("Help")
        shortcuts_act = QAction("Keyboard Shortcuts", self)
        shortcuts_act.setShortcut(QKeySequence("Meta+/"))
        shortcuts_act.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_act)

    def _show_about(self):
        """Show a native About dialog."""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "About TerminalDeck",
            "<h3>TerminalDeck</h3>"
            "<p>A native macOS dashboard for every CLI on your machine.</p>"
            "<p>157 tools tracked · 78 installed · 83 discoverable</p>"
            "<p style='color:#888'>v0.1 · built with PySide6 + pyte</p>",
        )

    def _show_preferences(self):
        """Show preferences dialog. Currently a placeholder for future settings."""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Preferences",
            "<h3>Preferences</h3>"
            "<p>TerminalDeck remembers your last selected category "
            "and filter between launches.</p>"
            "<p style='color:#888'>More settings coming soon.</p>",
        )

    def _show_shortcuts(self):
        """Native dialog showing every keyboard shortcut."""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            """<h3>Keyboard Shortcuts</h3>
<table cellpadding='6' style='margin-top:8px'>
<tr><td><b>⌘F</b></td><td>Focus filter</td></tr>
<tr><td><b>Esc</b></td><td>Clear filter & unfocus</td></tr>
<tr><td><b>⌘T</b></td><td>New tab</td></tr>
<tr><td><b>⌘W</b></td><td>Close current tab</td></tr>
<tr><td><b>⌘D</b></td><td>Duplicate current tab</td></tr>
<tr><td><b>⌘⇧R</b></td><td>Restart current tab's command</td></tr>
<tr><td><b>⌘Return</b></td><td>Launch selected tool</td></tr>
<tr><td><b>⌘⇧Return</b></td><td>Launch selected tool in new tab</td></tr>
<tr><td><b>⌘1 … ⌘9</b></td><td>Switch to tab N</td></tr>
<tr><td><b>⌘K</b></td><td>Clear terminal</td></tr>
<tr><td><b>⌘C</b></td><td>Stop current process</td></tr>
<tr><td><b>⌘=</b> / <b>⌘-</b> / <b>⌘0</b></td><td>Font +/−/reset</td></tr>
<tr><td><b>Ctrl+R</b></td><td>Re-detect tools</td></tr>
<tr><td><b>⌘,</b></td><td>Preferences</td></tr>
<tr><td><b>⌘Q</b></td><td>Quit TerminalDeck</td></tr>
</table>
<p style='color:#888;margin-top:12px'>
Right-click a tool row for Terminal.app / Warp launch.<br>
Click a tool row to launch in the current tab.
</p>""",
        )

    def _launch_selected(self):
        """Launch the currently highlighted tool (⌘Return)."""
        item = self.tool_list.currentItem()
        if item is None:
            return
        widget = self.tool_list.itemWidget(item)
        if widget and widget.tool:
            self._launch(widget.tool)

    def _launch_selected_new_tab(self):
        """Launch the currently highlighted tool in a new tab (⌘⇧Return)."""
        item = self.tool_list.currentItem()
        if item is None:
            return
        widget = self.tool_list.itemWidget(item)
        if widget and widget.tool:
            self.terminal.run_in_new_tab(widget.tool.command, category=widget.tool.category)

    def _update_title_bar(self):
        """Show running tab count in title bar."""
        running = 0
        for state in self.terminal._tab_states.values():
            if state.get("state") == "running":
                running += 1
        if running > 0:
            self.setWindowTitle(f"TerminalDeck — {running} running")
        else:
            self.setWindowTitle("TerminalDeck")

    # ─── QSettings persistence ────────────────────────────────────────
    def _restore_session(self):
        """Restore last selected category + filter + window geometry from QSettings."""
        from PySide6.QtCore import QSettings
        s = QSettings("TheSolAI", "TerminalDeck")
        cat_section = s.value("selected_section", "installed")
        cat_key = s.value("selected_key", None)
        if cat_key is not None:
            cat_key = str(cat_key)
        self._selected_category = (cat_section, cat_key)
        # Restore filter text
        saved_filter = s.value("filter_text", "", str)
        if saved_filter:
            self.filter.setText(saved_filter)
        # Restore available_only toggle
        avail = s.value("available_only", False, bool)
        self.available_only.setChecked(avail)
        # Restore window geometry (size + position)
        geom = s.value("window_geometry")
        if geom is not None:
            try:
                self.restoreGeometry(geom)
            except Exception:
                pass
        state = s.value("window_state")
        if state is not None:
            try:
                self.restoreState(state)
            except Exception:
                pass
        # Restore splitter sizes
        sp = s.value("splitter_sizes")
        if sp is not None:
            try:
                # PySide6 returns a QByteArray; convert to int list
                if hasattr(sp, "toList"):
                    sp = sp.toList()
                sizes = [int(x) for x in sp]
                if len(sizes) == 3 and sum(sizes) > 0:
                    self.splitter.setSizes(sizes)
            except Exception:
                pass
        # Highlight matching sidebar row
        for i, (sec, key, item) in enumerate(self.sidebar._items):
            if sec == cat_section and key == cat_key:
                self.sidebar.list.setCurrentRow(i)
                break

    def _save_session(self):
        """Persist last selected category + filter + geometry to QSettings."""
        from PySide6.QtCore import QSettings
        s = QSettings("TheSolAI", "TerminalDeck")
        section, key = self._selected_category
        s.setValue("selected_section", section)
        s.setValue("selected_key", key)
        s.setValue("filter_text", self.filter.text())
        s.setValue("available_only", self.available_only.isChecked())
        # Save window geometry
        try:
            s.setValue("window_geometry", self.saveGeometry())
            s.setValue("window_state", self.saveState())
            s.setValue("splitter_sizes", self.splitter.sizes())
        except Exception:
            pass

    def closeEvent(self, event):
        """Make sure all PTYReader threads are fully stopped before exit."""
        # Always use the tabbed terminal's shutdown — it walks every tab
        # and waits for each PTYReader thread to exit cleanly.
        self.terminal.shutdown()
        super().closeEvent(event)


# ─── Entry ─────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TerminalDeck")
    app.setOrganizationName("TheSolAI")
    app.setStyle("Fusion")  # Consistent dark style across macOS versions

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
"""Color palette — each main section has its own accent for visual differentiation.

Layout:
    ┌──────────┬──────────────────────────┬──────────────────────────┐
    │ SIDEBAR  │ TOOL LIST                │ TERMINAL                 │
    │ (blue)   │ (purple)                 │ (amber)                  │
    └──────────┴──────────────────────────┴──────────────────────────┘

Sections:
- Sidebar (left, category list): blue accent
- Tool list (middle, clickable rows): purple accent
- Terminal (right, PTY panes): amber accent
- Each tab in the terminal: green dot when running

Backgrounds are tinted by hue so it's obvious which section you're in even
without looking at the borders or accent stripes.
"""

# ─── Base palette (shared dark) ────────────────────────────────────────
BG_BASE       = "#0d1117"  # main window bg
BG_RAISED     = "#161b22"  # headers, toolbars
BG_BORDER     = "#21262d"  # dividers
FG_TEXT       = "#d4d4d4"
FG_DIM        = "#7d8590"
FG_FAINT      = "#4b525b"

# ─── Sidebar: blue ─────────────────────────────────────────────────────
SIDEBAR_BG        = "#0d1929"  # blue-tinted dark
SIDEBAR_HOVER     = "#16243a"
SIDEBAR_SELECTED  = "#1f6feb"
SIDEBAR_BORDER    = "#1f3a5f"
SIDEBAR_ACCENT    = "#58a6ff"

# ─── Tool list: purple ─────────────────────────────────────────────────
TOOL_BG           = "#16102a"  # purple-tinted dark
TOOL_ROW_HOVER    = "#22153d"
TOOL_ROW_SELECTED = "#3a2263"
TOOL_BORDER       = "#3a2263"
TOOL_ACCENT       = "#a371f7"  # GitHub purple

# ─── Terminal: amber ───────────────────────────────────────────────────
TERM_BG           = "#1a1408"  # amber-tinted dark
TERM_HEADER_BG    = "#211a0c"
TERM_BORDER       = "#3a2e15"
TERM_ACCENT       = "#f59e0b"  # amber
TERM_RUNNING_DOT  = "#3fb950"  # green dot when a command is running

# ─── Status ────────────────────────────────────────────────────────────
STATUS_BG         = "#0d1929"  # blue, matches sidebar accent
STATUS_FG         = "#58a6ff"
STATUS_OK         = "#3fb950"
STATUS_WARN       = "#f59e0b"
STATUS_ERR        = "#f85149"
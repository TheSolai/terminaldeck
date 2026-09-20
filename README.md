# TerminalDeck

Native macOS dashboard for launching CLI tools with a **built-in terminal** —
no Xcode required.

```
┌────────────────┬─────────────────────────┬─────────────────────────┐
│ TERMINALDECK   │ 🔎 Filter…  [Available] │ ▶ claude                │
│                ├─────────────────────────┤ $ claude                 │
│ INSTALLED (73) │ ● Claude Code    v2.1.278 │ ✓ Memory hooks loaded... │
│ All Tools      │ ● codex         v0.154.0 │ Type, Ctrl-C interrupt,  │
│ AI Coding  16  │ ● openclaw      2026.6.35│ Ctrl-D exit.             │
│ OpenClaw    5  │ ● ollama        v0.34.2  │                         │
│ Local LLMs  6  │ ● ...                    │                         │
│ Your AI     8  │                         │                         │
│ Productivity 16│                         │                         │
│ Dev / Build  22│                         │                         │
│ ── Discover ── │                         │                         │
│ Shell        19│                         │                         │
│ Editors       5│                         │                         │
│ ... (83 tools) │                         │                         │
└────────────────┴─────────────────────────┴─────────────────────────┘
```

## Run it

```bash
~/Projects/TerminalDeck/run.sh
```

Or directly:

```bash
cd ~/Projects/TerminalDeck
.venv/bin/python run.py
```

## Features

- **Two-pane sidebar**: installed tools + a Discover section with 10 installable-tool categories
- **156 tools total**: 73 installed (auto-detected) + 83 popular CLIs (click to install)
- **Search bar** with instant filter
- **"Available only"** toggle to hide missing/broken tools
- **Click a tool**:
  - If installed → spawns it in the **built-in PTY terminal**
  - If missing + has install cmd → **runs `brew install …` live** in the terminal
  - If missing + no install cmd → shows status-bar hint
- **ANSI colors** rendered in the terminal pane
- **Real PTY** — Ctrl-C interrupts, Ctrl-D exits, arrows/line-editing work
- **Cmd-R** re-detects versions
- **Cmd-K** clears the terminal
- **Detection**: 156 tools in ~7s, parallel, with hard timeouts (no UI freeze)

## Layout

```
terminaldeck/
├── __init__.py        # version
├── tools.py           # registry (156 tools) + version detection
├── terminal.py        # PTYReader + TerminalPane (ANSI + Qt widget)
└── main.py            # MainWindow, Sidebar (installed + discover), ToolList

run.py                 # entry point
run.sh                 # launcher
setup.py               # py2app config (broken on Py3.13, see below)
.venv/                 # Python 3.13 + PySide6 6.11.2 + ptyprocess
```

## Architecture

- **`tools.py`** —
  - `TOOLS`: 73 tools mirroring `~/Desktop/CLI.md` (installed + detected)
  - `DISCOVER_TOOLS`: 83 popular CLIs that the user might want (`brew install X` etc.)
  - `CATEGORIES` / `DISCOVER_CATEGORIES`: section labels
  - Detection runs each `<tool> --version` (or `-v` / `-V`) in a subprocess with 1.5s timeout; bails early if a flag hangs (TUIs)
  - `extract_version()` strips ANSI noise and recovers from "unknown option" / "no such" errors
- **`terminal.py`** — `pty.fork()` to spawn the tool with a pseudo-terminal. A `QThread` reads the PTY master fd via `select()` and emits `data_received`. ANSI codes are parsed into HTML spans. Clean shutdown via `closeEvent`.
- **`main.py`** — Qt window with QSplitter (sidebar | tool list | terminal). Dark theme via stylesheets. Background detection via `QRunnable` + `QThreadPool`.

## How the built-in terminal works

1. User clicks a tool row → `MainWindow._launch(tool)` →
   - If available: `TerminalPane.run_command(command)` → PTY spawn
   - If missing + `tool.install` set: `TerminalPane.run_command(tool.install)` → brew install runs live
   - If missing + no install: status-bar message
2. `pty.fork()` creates a child process with a new pseudo-terminal
3. Child `execvp($SHELL, "-il", "-c", command)` — login shell so PATH/env match
4. Parent reads from PTY master fd in `PTYReader(QThread)`
5. Output decoded UTF-8, rendered with ANSI color spans in QPlainTextEdit
6. Keystrokes forwarded to PTY master fd; arrow keys, Ctrl-C, Ctrl-D, Backspace all work

## Adding a tool

Edit `terminaldeck/tools.py` and append to `TOOLS` (for already-installed) or `DISCOVER_TOOLS` (for "click to install"):

```python
# Already installed
CLITool("my-tool", "My Tool", "my-tool",
        "Short description.",
        "ai-coding", model="Anthropic Claude")

# Discover (with install command)
CLITool("cool-cli", "Cool CLI", "cool",
        "Does cool things.",
        "shell", "—", install="brew install cool-cli")
```

Restart the app — detection picks it up automatically.

## Known limitations

- **`py2app` packaging is broken on Python 3.13** (the `zlib.__file__` issue). Run via `run.sh` until upstream fixes it. Will try **Nuitka** next.
- **Tmux-style line buffering** — basic PTY only, no scrollback/search.
- **Discover counts don't auto-update** when tools are installed (Cmd-R refreshes).

## Tested on

- macOS 27.0 (your machine)
- Python 3.13.10
- PySide6 6.11.2
- ptyprocess 0.7.0
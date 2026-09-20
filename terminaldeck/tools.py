"""Tool registry — single source of truth (mirrors ~/Desktop/CLI.md)."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import os
import re
import shutil
import subprocess
from pathlib import Path


# User-installed venv / tool paths that aren't auto-added to subprocess PATH.
# Subprocesses inherit a stripped PATH; ~/.zshrc additions don't apply.
_EXTRA_BIN_PATHS = [
    str(Path.home() / "Projects" / "Learnage" / ".venv" / "bin"),
    str(Path.home() / ".local" / "share" / "uv" / "tools" / "mini-agent" / "bin"),
    str(Path.home() / ".mavis" / "bin"),  # legacy mavis location
    str(Path.home() / "Projects" / "dross" / ".venv" / "bin"),
]


def _expand_env() -> dict[str, str]:
    """Return env dict with _EXTRA_BIN_PATHS prepended to PATH."""
    env = os.environ.copy()
    extra = os.pathsep.join(p for p in _EXTRA_BIN_PATHS if Path(p).exists())
    if extra:
        env["PATH"] = extra + os.pathsep + env.get("PATH", "")
    return env


@dataclass(frozen=True)
class CLITool:
    id: str
    name: str
    command: str
    description: str
    category: str
    model: Optional[str] = None
    notes: Optional[str] = None
    version_flags: tuple = ("--version", "-v", "-V", "--help")
    install: Optional[str] = None  # Command to run when tool is missing (run in terminal)


CATEGORIES = [
    ("ai-coding",    "AI Coding Agents"),
    ("openclaw",     "OpenClaw Ecosystem"),
    ("local-llm",    "Local LLMs & ML"),
    ("local-ai",     "Your Local AI Projects"),
    ("productivity", "Productivity & System"),
    ("dev",          "Dev / Build / Infra"),
]


TOOLS: list[CLITool] = [
    # ─── AI Coding Agents ───────────────────────────────────────────────
    CLITool("mavis", "MiniMax Code CLI", "mavis",
            "MiniMax Code orchestrator CLI. Symlink target (daemon/cli.js) was removed in a recent update.",
            "ai-coding", "MiniMax",
            notes="Currently broken — symlink points to daemon/cli.js which no longer exists in MiniMax Code.app bundle. File an issue with MiniMax Code team.",
            install=None),  # No auto-fix — needs upstream repair
    CLITool("mcode-tools", "mcode-tools", "mcode-tools",
            "MiniMax Code OAuth + connected Connector tools dispatcher.",
            "ai-coding", "MiniMax"),
    CLITool("claude", "Claude Code", "claude",
            "Claude Code by Anthropic — interactive coding agent.",
            "ai-coding", "Anthropic Claude"),
    CLITool("codex", "OpenAI Codex CLI", "codex",
            "OpenAI Codex CLI — coding agent.",
            "ai-coding", "OpenAI Codex"),
    CLITool("cline", "Cline", "cline",
            "VS Code-style autonomous agent in the terminal.",
            "ai-coding", "Various"),
    CLITool("kilocode", "Kilo Code", "kilocode",
            "Open-source AI coding agent (Cline fork).",
            "ai-coding", "Various"),
    CLITool("codebuff", "Codebuff", "codebuff",
            "AI coding agent.", "ai-coding", "Various"),
    CLITool("opencode", "OpenCode", "opencode",
            "Terminal AI coding tool.", "ai-coding", "Various"),
    CLITool("pi", "Pi", "pi",
            "Coding agent (earendil-works/pi-coding-agent).",
            "ai-coding", "Various"),
    CLITool("omp", "oh-my-pi", "omp",
            "Fork/wrapper of Pi installed via Bun. Needs Bun ≥1.3.14.",
            "ai-coding", "Various"),
    CLITool("oracle", "Oracle", "oracle",
            "Research/reasoning CLI. Drives a visible Chrome window.",
            "ai-coding", "OpenAI ChatGPT web"),
    CLITool("mmx", "MiniMax Platform CLI", "mmx",
            "Text/image/video/speech/music generation.",
            "ai-coding", "MiniMax Platform"),
    CLITool("llm-checker", "LLM Checker", "llm-checker",
            "Inspect/configure local LLM providers.",
            "ai-coding", "—"),
    CLITool("agent-browser", "Agent Browser", "agent-browser",
            "Browser-automation CLI for AI agents.",
            "ai-coding", "—"),
    CLITool("shieldcortex", "ShieldCortex", "shieldcortex",
            "AI Agent Memory Security.", "ai-coding", "—"),
    CLITool("clawhub", "ClawHub", "clawhub",
            "OpenClaw skill/package hub.", "ai-coding", "—"),

    # ─── OpenClaw Ecosystem ─────────────────────────────────────────────
    CLITool("openclaw", "OpenClaw", "openclaw",
            "Agent runtime that powers TheSolAI / AmreClaw.",
            "openclaw", "—"),
    CLITool("finn", "Finn", "finn",
            "Your personal Claw CLI (brew copy at /opt/homebrew/bin/finn).",
            "openclaw", "—"),
    CLITool("mission-control", "Mission Control", "mission-control",
            "OpenClaw dashboard / task runner.",
            "openclaw", "—"),
    CLITool("ocm", "OpenClaw Manager", "ocm",
            "Manage your Claw installation.", "openclaw", "—"),
    CLITool("mflux", "mflux", "mflux-generate",
            "Apple Silicon FLUX image-gen CLI.",
            "openclaw", "FLUX"),

    # ─── Local LLMs & ML ────────────────────────────────────────────────
    CLITool("ollama", "Ollama", "ollama",
            "Local LLM server. `ollama run llama3`.",
            "local-llm", "Local models",
            install="brew install ollama"),
    CLITool("llama.cpp", "llama.cpp", "llama",
            "CPU/GPU LLM inference engine. The Homebrew formula installs the binary as `llama` (not `llama.cpp`).",
            "local-llm", "Local GGUF",
            install="brew install llama.cpp"),
    CLITool("mlx", "MLX", "mlx",
            "Apple Silicon ML framework. Homebrew formula only ships config helpers (mlx.distributed_config, mlx.launch) — no `mlx` CLI. For an MLX chat CLI use mlx-lm.",
            "local-llm", "MLX",
            notes=(
                "Homebrew `mlx` is a library, not a CLI. "
                "For an actual chat/LM CLI: `pip install mlx-lm` → `mlx_lm.chat`."
            ),
            install="brew install mlx"),
    CLITool("mlx-lm", "MLX LM", "mlx-lm",
            "Run LLMs locally with mlx. Install via `pip install mlx-lm`.",
            "local-llm", "MLX",
            notes="Install: pip install mlx-lm",
            install="pip install mlx-lm"),
    CLITool("mlx-serve", "MLX Server", "mlx-serve",
            "Serve MLX models over HTTP.", "local-llm", "MLX",
            notes="Comes with the mlx-lm pip package as `mlx_lm.server`.",
            install="pip install mlx-lm"),
    CLITool("whisper", "Whisper", "whisper",
            "OpenAI Whisper speech-to-text.",
            "local-llm", "Whisper"),
    CLITool("tesseract", "Tesseract OCR", "tesseract",
            "OCR engine.", "local-llm", "—"),

    # ─── Local AI Projects ──────────────────────────────────────────────
    CLITool("nightdreamer", "NightDreamer", "nightdreamer",
            "Overnight multi-agent coding swarm.",
            "local-ai", "Various"),
    CLITool("elia", "Elia", "elia",
            "Terminal chat client for LLMs (pipx-installed, TUI — no version output).",
            "local-ai", "Various"),
    CLITool("parllama", "ParLlama", "parllama",
            "Ollama-focused chat/model manager TUI.",
            "local-ai", "Ollama"),
    CLITool("learnage", "Learnage", "learnage",
            "Local RAG book reader (SmolQuill fork). Lives in its own venv at /Users/amre/Projects/Learnage/.venv/bin/learnage — add that to PATH or use `~/.local/share/uv/python/cpython-3.13.10-macos-aarch64-none/bin/python -m learnage`.",
            "local-ai", "Local RAG",
            notes=(
                "PATH fix: export PATH=\"/Users/amre/Projects/Learnage/.venv/bin:$PATH\""
            ),
            install=None),
    CLITool("quill", "Quill", "quill",
            "Your personal writing helper.",
            "local-ai", "Various"),
    CLITool("agent", "agent", "agent",
            "Generic agent CLI from uv.", "local-ai", "Various"),
    CLITool("mini-agent", "mini-agent", "mini-agent",
            "Small agent + ACP protocol CLI. Requires mcp<2.",
            "local-ai", "Various",
            notes=(
                "Fixed: pinned mcp 1.9.0 in uv tool venv. "
                "If regresses: /Users/amre/.local/share/uv/tools/mini-agent/bin/pip install --force-reinstall 'mcp==1.9.0'"
            )),
    CLITool("nano-pdf", "nano-pdf", "nano-pdf",
            "Minimal PDF tool (uv tool install — actually works, just no version flag).",
            "local-ai", "—"),

    # ─── Productivity & System ──────────────────────────────────────────
    CLITool("himalaya", "Himalaya", "himalaya",
            "Email CLI (IMAP/SMTP).", "productivity", "—"),
    CLITool("imsg", "imsg", "imsg",
            "Read/send iMessage/SMS from terminal.",
            "productivity", "—"),
    CLITool("ordercli", "ordercli", "ordercli",
            "Apple Reminders CLI.", "productivity", "—"),
    CLITool("remindctl", "remindctl", "remindctl",
            "Reminders control.", "productivity", "—"),
    CLITool("peekaboo", "Peekaboo", "peekaboo",
            "Capture macOS screenshots/window state.",
            "productivity", "—"),
    CLITool("imagesnap", "imagesnap", "imagesnap",
            "Webcam capture.", "productivity", "—"),
    CLITool("cliclick", "cliclick", "cliclick",
            "Mouse/keyboard automation.",
            "productivity", "—"),
    CLITool("summarize", "summarize", "summarize",
            "Text/file summarization.",
            "productivity", "—"),
    CLITool("memo", "memo", "memo",
            "Terminal notes/memos.", "productivity", "—",
            "Broken — Python interpreter missing"),
    CLITool("sag", "sag", "sag",
            "macOS sysadmin utility.", "productivity", "—"),
    CLITool("gumroad", "Gumroad", "gumroad",
            "Gumroad seller CLI.", "productivity", "—"),
    CLITool("gogcli", "Google Workspace (gogcli)", "gogcli",
            "Google Workspace CLI. Homebrew formula installs as `gog`; symlinked to `gogcli` for convenience.",
            "productivity", "Google Workspace"),
    CLITool("wacli", "wacli", "wacli",
            "WhatsApp CLI.", "productivity", "—"),
    CLITool("openhue", "openhue", "openhue",
            "Philips Hue lights.", "productivity", "—"),
    CLITool("duti", "duti", "duti",
            "Set default apps for file types.",
            "productivity", "—"),
    CLITool("cloudflared", "cloudflared", "cloudflared",
            "Cloudflare Tunnel.", "productivity", "—"),

    # ─── Dev / Build / Infra ────────────────────────────────────────────
    CLITool("brew", "Homebrew", "brew",
            "macOS package manager.", "dev", "—",
            install='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'),
    CLITool("gh", "GitHub CLI", "gh",
            "gh pr, gh issue, gh repo clone.", "dev", "—",
            install="brew install gh"),
    CLITool("tmux", "tmux", "tmux",
            "Terminal multiplexer.", "dev", "—",
            install="brew install tmux"),
    CLITool("sqlite", "SQLite", "sqlite3",
            "CLI for SQLite.", "dev", "—",
            install="brew install sqlite"),
    CLITool("redis", "Redis CLI", "redis-cli",
            "Redis client.", "dev", "—",
            install="brew install redis"),
    CLITool("postgresql", "PostgreSQL", "psql",
            "Postgres client (16 & 17 installed).",
            "dev", "—",
            install="brew install postgresql@17"),
    CLITool("docker", "Docker", "docker",
            "Container runtime.", "dev", "—",
            install="brew install --cask docker"),
    CLITool("kubectl", "kubectl", "kubectl",
            "Kubernetes CLI.", "dev", "—",
            install="brew install kubectl"),
    CLITool("rustup", "Rust toolchain", "rustc",
            "Rust compiler + cargo + rustup.", "dev", "—"),
    CLITool("go", "Go", "go",
            "Go language toolchain.", "dev", "—"),
    CLITool("node", "Node.js", "node",
            "Node.js runtime (v25 active).", "dev", "—"),
    CLITool("npm", "npm", "npm",
            "Node package manager.", "dev", "—"),
    CLITool("pnpm", "pnpm", "pnpm",
            "Fast npm alternative.", "dev", "—"),
    CLITool("bun", "Bun", "bun",
            "JS/TS runtime + package manager.", "dev", "—"),
    CLITool("uv", "uv", "uv",
            "Fast Python package manager (Astral).", "dev", "—"),
    CLITool("gradle", "Gradle", "gradle",
            "Java build tool.", "dev", "—"),
    CLITool("cmake", "CMake", "cmake",
            "C/C++ build.", "dev", "—"),
    CLITool("pandoc", "pandoc", "pandoc",
            "Universal document converter.", "dev", "—"),
    CLITool("yt-dlp", "yt-dlp", "yt-dlp",
            "Download video/audio.", "dev", "—"),
    CLITool("ffmpeg", "ffmpeg", "ffmpeg",
            "Audio/video processing.", "dev", "—"),
    CLITool("imagemagick", "ImageMagick", "magick",
            "Image conversion/manipulation.", "dev", "—"),
    CLITool("xcodegen", "xcodegen", "xcodegen",
            "Generate Xcode projects from YAML.", "dev", "—"),
]

# ─── Discover (popular CLIs not yet installed) ───────────────────────
# These don't appear in the sidebar by default — accessed via the
# "Discover" sidebar tab.

DISCOVER_TOOLS: list[CLITool] = [
    # Shell & productivity — modern replacements
    CLITool("fzf", "fzf", "fzf",
            "Fuzzy finder for files, history, anything.",
            "shell", "—", install="brew install fzf"),
    CLITool("fd", "fd", "fd",
            "Simple alternative to find.",
            "shell", "—", install="brew install fd"),
    CLITool("bat", "bat", "bat",
            "Better cat with syntax highlighting + line numbers.",
            "shell", "—", install="brew install bat"),
    CLITool("ripgrep", "ripgrep", "rg",
            "Fast recursive grep, respects gitignore.",
            "shell", "—", install="brew install ripgrep"),
    CLITool("jq", "jq", "jq",
            "JSON processor — slice, filter, map, transform.",
            "shell", "—", install="brew install jq"),
    CLITool("yq", "yq", "yq",
            "YAML/XML/TOML processor like jq.",
            "shell", "—", install="brew install yq"),
    CLITool("tree", "tree", "tree",
            "Recursive directory listing.",
            "shell", "—", install="brew install tree"),
    CLITool("lsd", "lsd", "lsd",
            "ls with icons, colors, tree view.",
            "shell", "—", install="brew install lsd"),
    CLITool("exa", "exa", "exa",
            "Modern ls replacement.",
            "shell", "—", install="brew install exa"),
    CLITool("duf", "duf", "duf",
            "Better df — disk usage with pretty colors.",
            "shell", "—", install="brew install duf"),
    CLITool("dust", "dust", "dust",
            "Intuitive du — disk usage by tree.",
            "shell", "—", install="brew install dust"),
    CLITool("zoxide", "zoxide", "zoxide",
            "Smarter cd that learns your most-used dirs.",
            "shell", "—", install="brew install zoxide"),
    CLITool("mcfly", "mcfly", "mcfly",
            "Smart shell history search (replaces Ctrl-R).",
            "shell", "—", install="brew install mcfly"),
    CLITool("atuin", "atuin", "atuin",
            "Encrypted, synced shell history with fuzzy search.",
            "shell", "—", install="brew install atuin"),
    CLITool("tldr", "tldr", "tldr",
            "Simplified man pages with examples.",
            "shell", "—", install="brew install tldr"),
    CLITool("btop", "btop", "btop",
            "Beautiful resource monitor (htop++).",
            "shell", "—", install="brew install btop"),
    CLITool("htop", "htop", "htop",
            "Interactive process viewer.",
            "shell", "—", install="brew install htop"),
    CLITool("glances", "Glances", "glances",
            "System monitor in your terminal.",
            "shell", "—", install="brew install glances"),
    CLITool("delta", "delta", "delta",
            "Beautiful git diff viewer.",
            "shell", "—", install="brew install git-delta"),

    # Editors
    CLITool("neovim", "Neovim", "nvim",
            "Hyperextensible Vim-based text editor.",
            "editor", "—", install="brew install neovim"),
    CLITool("helix", "Helix", "hx",
            "Post-modern text editor (vim + kakoune + tree-sitter).",
            "editor", "—", install="brew install helix"),
    CLITool("micro", "Micro", "micro",
            "Modern intuitive terminal editor.",
            "editor", "—", install="brew install micro"),
    CLITool("kakoune", "Kakoune", "kak",
            "Vim-inspired selection-oriented editor.",
            "editor", "—", install="brew install kakoune"),
    CLITool("emacs", "Emacs", "emacs",
            "Extensible, customizable, self-documenting editor.",
            "editor", "—", install="brew install emacs"),

    # Git
    CLITool("lazygit", "Lazygit", "lazygit",
            "Terminal UI for git — stage, commit, push visually.",
            "git", "—", install="brew install lazygit"),
    CLITool("tig", "tig", "tig",
            "Text interface for git repos.",
            "git", "—", install="brew install tig"),
    CLITool("gitui", "gitui", "gitui",
            "Blazing fast terminal UI for git.",
            "git", "—", install="brew install gitui"),
    CLITool("gitleaks", "gitleaks", "gitleaks",
            "Audit git repos for secrets.",
            "git", "—", install="brew install gitleaks"),

    # Network & HTTP
    CLITool("httpie", "HTTPie", "http",
            "User-friendly cURL replacement (JSON, colors, sessions).",
            "net", "—", install="brew install httpie"),
    CLITool("curlie", "curlie", "curlie",
            "curl with httpie-style UI.",
            "net", "—", install="brew install curlie"),
    CLITool("xh", "xh", "xh",
            "Fast HTTP CLI (Rust rewrite of httpie).",
            "net", "—", install="brew install xh"),
    CLITool("trippy", "Trippy", "trippy",
            "Network diagnostic tool (traceroute++).",
            "net", "—", install="brew install trippy"),
    CLITool("gping", "gping", "gping",
            "Ping with a graph.",
            "net", "—", install="brew install gping"),
    CLITool("iperf3", "iperf3", "iperf3",
            "TCP/UDP bandwidth measurement.",
            "net", "—", install="brew install iperf3"),
    CLITool("bandwhich", "bandwhich", "bandwhich",
            "Terminal bandwidth utilization tool.",
            "net", "—", install="brew install bandwhich"),
    CLITool("nmap", "nmap", "nmap",
            "Network discovery and security auditing.",
            "net", "—", install="brew install nmap"),
    CLITool("rsync", "rsync", "rsync",
            "Fast incremental file transfer.",
            "net", "—", install="brew install rsync"),

    # Containers & K8s
    CLITool("helm", "Helm", "helm",
            "Kubernetes package manager.",
            "k8s", "—", install="brew install helm"),
    CLITool("k9s", "K9s", "k9s",
            "Kubernetes TUI dashboard.",
            "k8s", "—", install="brew install k9s"),
    CLITool("kubectx", "kubectx", "kubectx",
            "Switch between kubectl contexts + namespaces fast.",
            "k8s", "—", install="brew install kubectx"),
    CLITool("stern", "Stern", "stern",
            "Multi-pod log tailing for k8s.",
            "k8s", "—", install="brew install stern"),
    CLITool("podman", "Podman", "podman",
            "Daemon-less container engine.",
            "k8s", "—", install="brew install podman"),
    CLITool("dive", "dive", "dive",
            "Explore Docker image layers.",
            "k8s", "—", install="brew install dive"),
    CLITool("ctop", "ctop", "ctop",
            "Container metrics TUI.",
            "k8s", "—", install="brew install ctop"),

    # Cloud CLIs
    CLITool("aws", "AWS CLI", "aws",
            "Amazon Web Services CLI.",
            "cloud", "AWS", install="brew install awscli"),
    CLITool("gcloud", "Google Cloud", "gcloud",
            "Google Cloud SDK CLI.",
            "cloud", "GCP", install="brew install --cask google-cloud-sdk"),
    CLITool("az", "Azure CLI", "az",
            "Microsoft Azure CLI.",
            "cloud", "Azure", install="brew install azure-cli"),
    CLITool("doctl", "DigitalOcean", "doctl",
            "DigitalOcean CLI.",
            "cloud", "DigitalOcean", install="brew install doctl"),
    CLITool("flyctl", "Fly.io", "flyctl",
            "Fly.io CLI.",
            "cloud", "Fly.io", install="brew install flyctl"),
    CLITool("vercel", "Vercel", "vercel",
            "Vercel deploy CLI.",
            "cloud", "Vercel", install="npm i -g vercel"),
    CLITool("netlify", "Netlify", "netlify",
            "Netlify deploy CLI.",
            "cloud", "Netlify", install="npm i -g netlify-cli"),
    CLITool("supabase", "Supabase", "supabase",
            "Supabase local dev + deploy CLI.",
            "cloud", "Supabase", install="brew install supabase/tap/supabase"),
    CLITool("wrangler", "Wrangler", "wrangler",
            "Cloudflare Workers CLI.",
            "cloud", "Cloudflare", install="npm i -g wrangler"),
    CLITool("railway", "Railway", "railway",
            "Railway deploy CLI.",
            "cloud", "Railway", install="npm i -g @railway/cli"),

    # Databases
    CLITool("mongosh", "MongoDB Shell", "mongosh",
            "MongoDB interactive shell.",
            "db", "MongoDB", install="brew install mongosh"),
    CLITool("mysql", "MySQL", "mysql",
            "MySQL CLI client.",
            "db", "MySQL", install="brew install mysql-client"),
    CLITool("litecli", "litecli", "litecli",
            "SQLite CLI with autocompletion + syntax highlighting.",
            "db", "SQLite", install="brew install litecli"),
    CLITool("iredis", "iredis", "iredis",
            "Redis CLI with autocompletion + syntax highlighting.",
            "db", "Redis", install="brew install iredis"),
    CLITool("duckdb", "DuckDB", "duckdb",
            "In-process analytical DB, OLAP SQL.",
            "db", "DuckDB", install="brew install duckdb"),

    # Build & Task runners
    CLITool("just", "just", "just",
            "Just a command runner (better make).",
            "build", "—", install="brew install just"),
    CLITool("watchexec", "watchexec", "watchexec",
            "Re-run commands on file change.",
            "build", "—", install="brew install watchexec"),
    CLITool("ninja", "Ninja", "ninja",
            "Small build system focused on speed.",
            "build", "—", install="brew install ninja"),
    CLITool("bazelisk", "Bazelisk", "bazelisk",
            "User-friendly bazel launcher.",
            "build", "—", install="brew install bazelisk"),

    # AI / ML CLIs
    CLITool("huggingface-cli", "HuggingFace", "huggingface-cli",
            "HuggingFace Hub CLI — download/upload models.",
            "ai", "HuggingFace", install="uv tool install huggingface_hub[cli]"),
    CLITool("openai", "OpenAI CLI", "openai",
            "OpenAI API CLI (text/vision/audio).",
            "ai", "OpenAI", install="brew install openai"),
    CLITool("aichat", "aichat", "aichat",
            "All-in-one chat CLI for many LLM providers.",
            "ai", "Various", install="brew install aichat"),
    CLITool("sg", "ast-grep", "sg",
            "AST-based code search (grep for source code).",
            "ai", "—", install="brew install ast-grep"),

    # Misc fun & useful
    CLITool("fastfetch", "fastfetch", "fastfetch",
            "Faster neofetch replacement.",
            "misc", "—", install="brew install fastfetch"),
    CLITool("neofetch", "neofetch", "neofetch",
            "System info + ASCII art.",
            "misc", "—", install="brew install neofetch"),
    CLITool("figlet", "figlet", "figlet",
            "ASCII art from text.",
            "misc", "—", install="brew install figlet"),
    CLITool("cowsay", "cowsay", "cowsay",
            "ASCII cow says things.",
            "misc", "—", install="brew install cowsay"),
    CLITool("lolcat", "lolcat", "lolcat",
            "Rainbow colorizer for terminal output.",
            "misc", "—", install="brew install lolcat"),
    CLITool("sl", "sl", "sl",
            "Steam locomotive across your terminal.",
            "misc", "—", install="brew install sl"),
    CLITool("cmatrix", "cmatrix", "cmatrix",
            "Matrix-style scrolling text.",
            "misc", "—", install="brew install cmatrix"),
    CLITool("cbonsai", "cbonsai", "cbonsai",
            "Grow a bonsai tree in your terminal.",
            "misc", "—", install="brew install cbonsai"),
    CLITool("asciiquarium", "asciiquarium", "asciiquarium",
            "Animated aquarium in terminal.",
            "misc", "—", install="brew install asciiquarium"),
    CLITool("pipes", "pipes.sh", "pipes.sh",
            "Animated pipes on terminal.",
            "misc", "—", install="brew install pipes-sh"),
    CLITool("navi", "navi", "navi",
            "Interactive cheatsheets in your terminal.",
            "misc", "—", install="brew install navi"),
    CLITool("choose", "choose", "choose",
            "Human-friendly alternative to cut + awk.",
            "misc", "—", install="brew install choose-rust"),
    CLITool("sd", "sd", "sd",
            "Intuitive find-and-replace (sed alternative).",
            "misc", "—", install="brew install sd"),
    CLITool("choose-gui", "choose-gui", "choose-gui",
            "GUI for the choose cut-tool.",
            "misc", "—", install="brew install choose-gui"),
    CLITool("hyperfine", "hyperfine", "hyperfine",
            "Benchmark CLI with statistical rigor.",
            "misc", "—", install="brew install hyperfine"),
    CLITool("procs", "procs", "procs",
            "Modern ps with colors and trees.",
            "misc", "—", install="brew install procs"),
]

# Categories used by the Discover tab (extra categories beyond CATEGORIES).
DISCOVER_CATEGORIES = [
    ("shell",   "Shell & Productivity"),
    ("editor",  "Editors"),
    ("git",     "Git"),
    ("net",     "Network & HTTP"),
    ("k8s",     "Containers & K8s"),
    ("cloud",   "Cloud CLIs"),
    ("db",      "Databases"),
    ("build",   "Build & Task"),
    ("ai",      "AI / ML CLIs"),
    ("misc",    "Misc & Fun"),
]


# ─── Detection ────────────────────────────────────────────────────────

_VERSION_RE = re.compile(
    r"(v?\d+\.\d+(?:\.\d+)?(?:[-+][\w.-]+)?|\d+\.\d+\.\d+[-+]?[0-9]{4,}|2\d{3}\.\d{1,2}\.\d{1,2})"
)

# Lines like "tmux: unknown option -- -" or "open terminal failed: ..." should
# not be treated as a version string.
_ERROR_HINT_RE = re.compile(
    r"(^[\w./-]+:\s*(error|unknown|illegal|invalid|usage))|"
    r"(^\s*(error|exception|traceback))|"
    r"(not a terminal)|"
    r"(failed:)|"
    r"(no such)",
    re.IGNORECASE,
)


def extract_version(line: str) -> str:
    line = line.strip()
    if not line:
        return "—"
    if _ERROR_HINT_RE.search(line):
        return "—"
    m = _VERSION_RE.search(line)
    if m:
        return m.group(0)
    if any(kw in line.lower() for kw in ("error", "unknown option", "illegal", "no such", "failed:")):
        return "—"
    if len(line) > 60:
        return line[:60] + "…"
    return line


def detect(tool: CLITool, timeout: float = 1.5) -> dict:
    """Return {available, version, path} for a tool. Fast.

    Strategy: try --version, -v, -V, --help (in order). Stop as soon as any
    flag returns useful output. On the first timeout, give up on remaining
    flags and return the path with version='—' (TUIs and interactive REPLs).
    """
    # Search both system PATH and our extended venv paths so tools like
    # `learnage` (in ~/Projects/Learnage/.venv/bin) are picked up.
    env = _expand_env()
    path = shutil.which(tool.command, path=env.get("PATH"))
    if not path:
        return {"available": False, "version": None, "path": None}

    flags = list(tool.version_flags)
    # Drop --help by default — too many TUIs hang on it.
    flags = [f for f in flags if f != "--help"] or ["--version"]

    for flag in flags:
        try:
            result = subprocess.run(
                [path, flag],
                capture_output=True, text=True, timeout=timeout, env=env
            )
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            if output:
                first_line = output.split("\n")[0]
                version = extract_version(first_line)
                if version and version != "—":
                    return {
                        "available": True,
                        "version": version,
                        "path": path,
                    }
                # Got output but it was an error message — try next flag
                continue
        except subprocess.TimeoutExpired:
            # Tool hangs on this flag → it's an interactive TUI, don't keep waiting
            return {"available": True, "version": "—", "path": path}
        except Exception:
            continue

    # All flags tried, none gave useful output
    return {"available": True, "version": "—", "path": path}


def detect_all(tools: list[CLITool]) -> dict[str, dict]:
    """Detect all tools in parallel using a thread pool."""
    from concurrent.futures import ThreadPoolExecutor
    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        for tool, status in zip(tools, ex.map(lambda t: detect(t), tools)):
            out[tool.id] = status
    return out


# ─── Helpers ──────────────────────────────────────────────────────────

def tools_by_category() -> dict[str, list[CLITool]]:
    out: dict[str, list[CLITool]] = {k: [] for k, _ in CATEGORIES}
    for tool in TOOLS:
        out[tool.category].append(tool)
    return out


def all_tools() -> list[CLITool]:
    """Return combined list of installed + discoverable tools."""
    return list(TOOLS) + list(DISCOVER_TOOLS)


def discover_by_category() -> dict[str, list[CLITool]]:
    out: dict[str, list[CLITool]] = {k: [] for k, _ in DISCOVER_CATEGORIES}
    for tool in DISCOVER_TOOLS:
        out[tool.category].append(tool)
    return out
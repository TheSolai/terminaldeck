"""py2app setup for TerminalDeck."""
from setuptools import setup

APP = ["run.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "packages": ["terminaldeck"],
    "includes": ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "ptyprocess"],
    "plist": {
        "CFBundleName": "TerminalDeck",
        "CFBundleDisplayName": "TerminalDeck",
        "CFBundleIdentifier": "com.thesolai.TerminalDeck",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "NSHumanReadableCopyright": "© 2026 Anne Marie Lee",
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "CFBundleIconFile": "",  # Will use default
    },
    "iconfile": None,
}

setup(
    app=APP,
    name="TerminalDeck",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
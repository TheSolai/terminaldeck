# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['pyte', 'wcwidth', 'PySide6.QtCore', 'PySide6.QtWidgets', 'PySide6.QtGui', 'ptyprocess']
hiddenimports += collect_submodules('terminaldeck')
hiddenimports += collect_submodules('pyte')


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('/Users/amre/Projects/TerminalDeck/terminaldeck/colors.py', 'terminaldeck'), ('/Users/amre/Projects/TerminalDeck/terminaldeck/tools.py', 'terminaldeck'), ('/Users/amre/Projects/TerminalDeck/terminaldeck/terminal.py', 'terminaldeck'), ('/Users/amre/Projects/TerminalDeck/terminaldeck/tabbed.py', 'terminaldeck'), ('/Users/amre/Projects/TerminalDeck/terminaldeck/launcher.py', 'terminaldeck'), ('/Users/amre/Projects/TerminalDeck/terminaldeck/main.py', 'terminaldeck'), ('/Users/amre/Projects/TerminalDeck/terminaldeck/__init__.py', 'terminaldeck')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TerminalDeck',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TerminalDeck',
)
app = BUNDLE(
    coll,
    name='TerminalDeck.app',
    icon=None,
    bundle_identifier='com.thesolai.TerminalDeck',
)

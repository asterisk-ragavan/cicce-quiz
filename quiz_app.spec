# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Quiz Application - SINGLE FILE BUILD
Everything bundled inside one exe, only questions folder is external

WINDOWS 10+ OPTIMIZED:
- Requires Python 3.10+ (3.13+ recommended for best performance)
- Download from: https://www.python.org/downloads/
- Install requirements: pip install -r requirements.txt
- Build with: pyinstaller --clean quiz_app.spec

DATABASE ARCHITECTURE:
- All data stored in SQLite database (data/quiz_app.db)
- Database auto-created on first run with default admin/password
- JSON quiz files auto-imported from questions/ folder
"""

import os
import sys

# Get the current directory
CURRENT_DIR = os.path.dirname(os.path.abspath(SPEC))

block_cipher = None

a = Analysis(
    ['run_app.py', 'app.py', 'database.py'],
    pathex=[CURRENT_DIR],
    binaries=[],
    datas=[
        # Bundle templates inside exe (HTML files)
        ('templates', 'templates'),
        # Bundle static files inside exe (CSS, JS, fonts for offline use)
        ('static', 'static'),
        # Bundle questions as defaults (copied to external folder on first run)
        ('questions', 'questions'),
    ],
    hiddenimports=[
        'flask',
        'flask_session',
        'flask_wtf',
        'flask_wtf.csrf',
        'flask_limiter',
        'flask_limiter.util',
        'wtforms',
        'limits',
        'jinja2',
        'werkzeug',
        'werkzeug.security',
        'cachelib',
        'cachelib.file',
        'cachelib.simple',
        'sqlite3',
        'database',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# SINGLE FILE EXECUTABLE - everything bundled into one exe
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='QuizApp',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if needed: icon='icon.ico'
)

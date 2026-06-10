# -*- mode: python ; coding: utf-8 -*-
#
# PriceScout.spec — Configuration PyInstaller
# Build : pyinstaller PriceScout.spec
#

import os
block_cipher = None

DESKTOP = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(DESKTOP, 'main.py')],
    pathex=[DESKTOP],
    binaries=[],
    datas=[
        (os.path.join(DESKTOP, 'templates', 'index.html'), 'templates'),
        (os.path.join(DESKTOP, 'version.txt'), '.'),
    ],
    hiddenimports=[
        # Scrapers & modules internes
        'activation',
        'activation_window',
        'paths',
        'vinted_pricer',
        'leboncoin_scraper',
        # Flask & dépendances
        'flask',
        'flask.templating',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.debug',
        # Réseau
        'requests',
        'curl_cffi',
        'curl_cffi.requests',
        # OAuth (Cardmarket)
        'requests_oauthlib',
        'oauthlib',
        'oauthlib.oauth1',
        # Tkinter (fenêtre activation)
        'tkinter',
        'tkinter.font',
        # Stdlib
        'hmac',
        'hashlib',
        'statistics',
        'unicodedata',
        'threading',
        'webbrowser',
        'subprocess',
        'socket',
        'json',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'PyQt5', 'PyQt6', 'wx',
        'pytest', 'IPython', 'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PriceScout',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Pas de fenêtre noire
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(DESKTOP, 'icon.ico'),
)

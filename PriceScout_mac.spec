# -*- mode: python ; coding: utf-8 -*-
# PriceScout.spec — Version Mac

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
        'activation',
        'activation_window',
        'paths',
        'vinted_pricer',
        'leboncoin_scraper',
        'flask',
        'flask.templating',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.debug',
        'requests',
        'curl_cffi',
        'curl_cffi.requests',
        'tkinter',
        'tkinter.font',
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
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'PyQt5', 'PyQt6'],
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
    strip=False,
    upx=True,
    console=False,
    target_arch=None,
)

app = BUNDLE(
    exe,
    name='PriceScout.app',
    icon=None,
    bundle_identifier='fr.pricescout.app',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '2.1',
    },
)

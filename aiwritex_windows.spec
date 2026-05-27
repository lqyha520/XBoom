# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

root = Path.cwd()

block_cipher = None

hiddenimports = collect_submodules('aiforge') + collect_submodules('tiktoken_ext') + [
    'webview',
    'uvicorn',
    'fastapi',
    'jinja2',
    'sqlmodel',
    'playwright',
    'pystray',
    'PIL',
]

datas = [
    *collect_data_files('crewai'),
    *collect_data_files('tiktoken'),
    *collect_data_files('litellm'),
    (str(root / 'src' / 'ai_write_x' / 'assets' / 'branding'), 'src/ai_write_x/assets/branding'),
    (str(root / 'src' / 'ai_write_x' / 'web' / 'templates'), 'src/ai_write_x/web/templates'),
    (str(root / 'src' / 'ai_write_x' / 'web' / 'static'), 'src/ai_write_x/web/static'),
    (str(root / 'src' / 'ai_write_x' / 'config'), 'src/ai_write_x/config'),
    (str(root / 'src' / 'ai_write_x' / 'scrapers'), 'src/ai_write_x/scrapers'),
    (str(root / 'knowledge' / 'templates'), 'templates'),
    (str(root / 'config'), 'config'),
    (str(root / 'secrets' / 'api_keys.example.yaml'), 'secrets'),
    (str(root / 'z-image专用nf4快速备份.json'), '.'),
]

a = Analysis(
    ['main.py'],
    pathex=[str(root), str(root / 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'notebook', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='XBoom',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / 'src' / 'ai_write_x' / 'assets' / 'branding' / 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='XBoom',
)

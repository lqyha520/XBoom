# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

root = Path.cwd()
factory_config_dir = root / 'build' / 'factory_config'

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
    'lxml',
    'lxml.etree',
    'lxml._elementpath',
    'chardet',
    'aiohttp',
    'feedparser',
    'asyncpg',
]

# 仅打包出厂资源：勿包含本机 config.yaml / install_id / 个人备份等
_factory_datas = []
if (factory_config_dir / 'config.yaml').is_file():
    _factory_datas.extend([
        (str(factory_config_dir / 'config.yaml'), 'config'),
        (str(factory_config_dir / 'aiforge.toml'), 'config'),
        (str(factory_config_dir / 'mcp_services.json'), 'config'),
    ])
    _secrets_template = factory_config_dir / 'secrets' / 'api_keys.yaml'
    if _secrets_template.is_file():
        _factory_datas.append((str(_secrets_template), 'secrets'))
else:
    raise SystemExit(
        '缺少 build/factory_config/config.yaml，请先运行: '
        'python scripts/export_factory_config_for_build.py'
    )

_prompts_dir = root / 'config' / 'prompts'
if _prompts_dir.is_dir():
    _factory_datas.append((str(_prompts_dir), 'config/prompts'))

# ComfyUI 默认工作流（安装版需随包提供，否则只能降级 Picsum 占位图）
_comfy_workflow = root / 'z-image专用nf4快速备份.json'
if _comfy_workflow.is_file():
    _factory_datas.append((str(_comfy_workflow), '.'))
else:
    raise SystemExit(
        '缺少 z-image专用nf4快速备份.json（ComfyUI 工作流），请放在项目根目录后再打包。'
    )

datas = [
    *collect_data_files('crewai'),
    *collect_data_files('tiktoken'),
    *collect_data_files('litellm'),
    (str(root / 'src' / 'ai_write_x' / 'assets' / 'branding'), 'src/ai_write_x/assets/branding'),
    (str(root / 'src' / 'ai_write_x' / 'web' / 'templates'), 'src/ai_write_x/web/templates'),
    (str(root / 'src' / 'ai_write_x' / 'web' / 'static'), 'src/ai_write_x/web/static'),
    (str(root / 'src' / 'ai_write_x' / 'scrapers'), 'src/ai_write_x/scrapers'),
    (str(root / 'knowledge' / 'templates'), 'templates'),
    (str(root / 'secrets' / 'api_keys.example.yaml'), 'secrets/api_keys.example.yaml'),
    *_factory_datas,
]

excludes = [
    'output',
    'data',
    '*.db',
    'pywebview',
    'logs',
    '__pycache__',
    'torch',
    'torchvision',
    'torchaudio',
    'timm',
    'llvmlite',
    'numba',
    'cv2',
    'opencv',
    'sklearn',
    'scikit-learn',
    'transformers',
    'jedi',
    'Pythonwin',
    'win32ui',
    'gevent',
    'tkinter',
    '_tkinter',
    'tcl',
    'tk',
    'hf_xet',
    'Cython',
    'sympy',
    'matplotlib',
    'pytest',
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
    excludes=excludes,
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
    name='小爆来咯',
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
    name='小爆来咯',
)

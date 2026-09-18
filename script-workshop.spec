# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Script Workshop desktop app.

import os
from pathlib import Path

block_cipher = None
ROOT = Path(os.path.dirname(os.path.abspath(SPECPATH)))

a = Analysis(
    [str(ROOT / 'app' / 'desktop.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # 前端构建产物
        (str(ROOT / 'frontend' / 'dist'), 'frontend/dist'),
        # 内置插件（loader 按路径扫描 app/plugins/builtin，漏打包则插件系统为空）
        (str(ROOT / 'app' / 'plugins'), 'app/plugins'),
    ],
    hiddenimports=[
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'langchain',
        'langchain_core',
        'langchain_openai',
        'langchain_community',
        'langchain_text_splitters',
        'langgraph',
        'langgraph.graph',
        'langgraph.graph.message',
        'langgraph.prebuilt',
        'langgraph.checkpoint',
        'langgraph.checkpoint.memory',
        'langgraph.types',
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'pydantic',
        'pydantic_settings',
        'fastapi',
        'starlette',
        'multipart',
        'webview',
    ],
    excludes=[
        'pymilvus',           # 桌面模式用内存向量，不需要 Milvus
        'psycopg',            # 桌面模式用 SQLite，不需要 Postgres 驱动
        'psycopg_pool',
        'langgraph.checkpoint.postgres',
        'matplotlib',
        'PIL',
        'tkinter',            # pywebview 不需要 tkinter
        'test',
        'tests',
        'pytest',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name='ScriptWorkshop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # 可以后续添加 .ico 图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ScriptWorkshop',
)

# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['restyle_app.py'],
    pathex=[],
    binaries=[],
    datas=[('../../references/styles', 'styles'), ('../../scripts/core/docx_support', 'docx_support')],
    hiddenimports=['anthropic', 'pydantic', 'lxml', 'docx', 'docx.oxml', 'docx.oxml.ns'],
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
    a.binaries,
    a.datas,
    [],
    name='Citation Restyle Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

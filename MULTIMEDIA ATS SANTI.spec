# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['installer_app.py'],
    pathex=[],
    binaries=[],
    datas=[('dxgi.dll', '.'), ('WebView2Loader.dll', '.'), ('MENU_EXTRAIDO', 'MENU_EXTRAIDO'), ('installer_assets', 'installer_assets'), ('dist/mmats_audio_inmersivo.exe', '.')],
    hiddenimports=[],
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
    name='MULTIMEDIA ATS SANTI',
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
    icon=['installer_assets\\installer_icon.ico'],
)

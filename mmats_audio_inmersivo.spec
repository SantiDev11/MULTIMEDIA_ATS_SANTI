# -*- mode: python ; coding: utf-8 -*-
"""
Empaqueta el servicio de Audio Inmersivo 3D por camara como un .exe autonomo.

console=False: es un servicio de fondo, no debe abrir ninguna ventana negra
mientras el usuario juega. Para depurar, ejecutar el .py directamente con
    python mmats_audio_inmersivo.py --consola
o revisar %APPDATA%\\MULTIMEDIA ATS SANTI\\audio_inmersivo.log
"""

a = Analysis(
    ['mmats_audio_inmersivo.py'],
    pathex=[],
    binaries=[],
    datas=[],
    # comtypes genera interfaces COM en tiempo de ejecucion; PyInstaller no las
    # detecta por analisis estatico, hay que declararlas a mano.
    hiddenimports=[
        'comtypes',
        'comtypes.stream',
        'comtypes.automation',
        'comtypes.persist',
        'pycaw',
        'pycaw.pycaw',
        'psutil',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PIL', 'pygame', 'numpy', 'pefile', 'capstone'],
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
    name='mmats_audio_inmersivo',
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

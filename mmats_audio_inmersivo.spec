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
        # Control por voz: SAPI 5 se maneja por el typelib SpeechLib, que
        # comtypes ya tiene generado. Sin declararlo, el .exe congelado no lo
        # encuentra y el reconocedor no arranca.
        'comtypes.gen',
        'comtypes.gen.SpeechLib',
        'comtypes.gen._C866CA3A_32F7_11D2_9602_00C04F8EE628_0_5_4',
        'comtypes.client._events',
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

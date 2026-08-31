# -*- mode: python ; coding: utf-8 -*-
"""
Empaqueta el servicio de Audio Inmersivo 3D por camara como un .exe autonomo.

console=False: es un servicio de fondo, no debe abrir ninguna ventana negra
mientras el usuario juega. Para depurar, ejecutar el .py directamente con
    python mmats_audio_inmersivo.py --consola
o revisar %APPDATA%\\MULTIMEDIA ATS SANTI\\audio_inmersivo.log

POR QUE EL CONTROL POR VOZ NO ARRANCABA EN EL .EXE
--------------------------------------------------------------------------------
comtypes no trae las interfaces COM escritas: las GENERA en tiempo de ejecucion
leyendo el typelib y las deja como modulos .py dentro de comtypes/gen, en
site-packages. Dentro de un .exe congelado ese directorio es de solo lectura, asi
que si los modulos no viajan YA generados, el
`from comtypes.gen.SpeechLib import ...` del reconocedor falla y la voz se cae
con "ModuleNotFoundError" sin mas explicacion.

Listarlos a mano no basta y por eso seguia roto: SpeechLib importa un wrapper con
nombre de GUID, y ESE a su vez importa el typelib de stdole, con otro GUID. Faltar
uno solo tumba la cadena entera. Aqui se recogen todos los modulos de
comtypes.gen de golpe, que ademas aguanta que comtypes cambie los nombres.

OJO: solo se empaqueta lo que exista en site-packages EN EL MOMENTO DEL BUILD. Si
comtypes/gen esta vacio, hay que generar el typelib una vez antes de compilar:
    python -c "import comtypes.client as c; c.GetModule('sapi.dll')"
"""

from PyInstaller.utils.hooks import collect_submodules

_gen = collect_submodules('comtypes.gen')
if 'comtypes.gen.SpeechLib' not in _gen:
    raise SystemExit(
        'ABORTADO: comtypes.gen.SpeechLib no esta generado, el .exe saldria sin voz.\n'
        '          Ejecuta antes:  python -c "import comtypes.client as c; '
        'c.GetModule(\'sapi.dll\')"')
print(f' [SPEC] comtypes.gen empaquetado: {len(_gen)} modulos '
      f'(SpeechLib incluido) -> el control por voz viaja completo')

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
        # Control por voz (ver la explicacion larga de arriba).
        'comtypes.client._events',
    ] + _gen,
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

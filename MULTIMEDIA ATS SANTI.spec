# -*- mode: python ; coding: utf-8 -*-
#
# Empaquetado del instalador.
#
# Dos cosas que hay que respetar aqui:
#
# 1) El servicio de audio se coge de la RAIZ del repo, no de dist/. La carpeta
#    dist/ es un artefacto de PyInstaller que ya no se guarda (esta en
#    .gitignore), asi que la ruta 'dist/mmats_audio_inmersivo.exe' que habia
#    antes hacia que este spec fallara en cuanto se limpiaba el arbol.
#
# 2) De MENU_EXTRAIDO solo viajan los archivos que el instalador despliega de
#    verdad. La subcarpeta BACKUP y las notas .txt las descarta igualmente
#    installer_app.py al instalar (MENU_DIRS_EXCLUIDOS / MENU_ARCHIVOS_EXCLUIDOS),
#    asi que meterlas en el .exe era peso muerto.

import os

_EXCLUIR_DIRS = {'BACKUP'}
_EXCLUIR_ARCHIVOS = {
    'ANALISIS.TXT',
    'CAMBIOS_MULTIMEDIAATS.TXT',
    'CAMBIOS_MULTIMEDIA_ATS_SANTI.TXT',
    'DLL_UPDATE_REPORT.TXT',
}

_menu = []
for _raiz, _dirs, _archivos in os.walk('MENU_EXTRAIDO'):
    _dirs[:] = [d for d in _dirs if d.upper() not in _EXCLUIR_DIRS]
    _rel = os.path.relpath(_raiz, 'MENU_EXTRAIDO')
    _destino = 'MENU_EXTRAIDO' if _rel == '.' else os.path.join('MENU_EXTRAIDO', _rel)
    for _f in _archivos:
        if _f.upper() in _EXCLUIR_ARCHIVOS:
            continue
        _menu.append((os.path.join(_raiz, _f), _destino))


a = Analysis(
    ['installer_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('dxgi.dll', '.'),
        ('WebView2Loader.dll', '.'),
        ('installer_assets', 'installer_assets'),
        ('mmats_audio_inmersivo.exe', '.'),
    ] + _menu,
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

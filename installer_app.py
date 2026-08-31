# -*- coding: utf-8 -*-
"""
================================================================================
MULTIMEDIA ATS SANTI - Instalador y Gestor Oficial v2.0
================================================================================
Compatible con Windows 10/11 x64 y American Truck Simulator
"""

import ctypes
import os
import sys
import shutil
import hashlib
import datetime
import time
import winreg
import json
import threading
import subprocess
import urllib.error
import urllib.request
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "MULTIMEDIA ATS SANTI"
APP_VERSION = "2.0.0.0"
APP_TITLE = f"{APP_NAME} - Instalador y Gestor Oficial"
LOG_FILENAME = "MULTIMEDIA_ATS_SANTI_INSTALL.log"
MANIFEST_FILENAME = "MULTIMEDIA_ATS_SANTI_MANIFEST.json"
UNIVERSAL_LICENSE = "MMATS-SANTI-2026-UNIVERSAL"

# Servicio de Audio Inmersivo 3D por cámara (proceso independiente del mod).
AUDIO_HELPER_EXE = "mmats_audio_inmersivo.exe"
AUDIO_HELPER_RUN_KEY = "MULTIMEDIA ATS SANTI - Audio Inmersivo"
AUDIO_HELPER_PORT = 48221
GAME_EXE = "amtrucks.exe"

# Copias de seguridad que se conservan en la carpeta del juego. Cada instalación
# creaba una carpeta nueva de ~3 MB y ninguna se borraba nunca: en este equipo
# se habían acumulado 52 carpetas (168 MB) dentro de bin\win_x64.
BACKUPS_A_CONSERVAR = 3

# Lo que NO se copia a la carpeta del juego desde MENU_EXTRAIDO. Son copias de
# seguridad del propio desarrollo y notas en texto plano: el WebView no las abre
# nunca y solo ensucian bin\win_x64.
MENU_DIRS_EXCLUIDOS = {"BACKUP"}
MENU_ARCHIVOS_EXCLUIDOS = {
    "ANALISIS.TXT",
    "CAMBIOS_MULTIMEDIAATS.TXT",
    "CAMBIOS_MULTIMEDIA_ATS_SANTI.TXT",
    "DLL_UPDATE_REPORT.TXT",
}

def get_bundle_dir():
    """Retorna el directorio donde residen los recursos empaquetados por PyInstaller o en modo desarrollo."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_source_files():
    """Retorna las rutas de los archivos fuente empaquetados dentro del instalador."""
    base_dir = get_bundle_dir()
    
    # Verificar dxgi.dll
    dxgi_path = os.path.join(base_dir, "dxgi.dll")
    if not os.path.isfile(dxgi_path):
        dxgi_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dxgi.dll")
        
    # Verificar WebView2Loader.dll
    webview_path = os.path.join(base_dir, "WebView2Loader.dll")
    if not os.path.isfile(webview_path):
        webview_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WebView2Loader.dll")
        
    # Verificar MENU_EXTRAIDO
    menu_dir = os.path.join(base_dir, "MENU_EXTRAIDO")
    if not os.path.isdir(menu_dir):
        menu_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "MENU_EXTRAIDO")
        
    # Servicio de Audio Inmersivo 3D por cámara. Es opcional: si no está
    # empaquetado, la instalación continúa sin él (el mod funciona igual, solo
    # que el overlay mostrará "Servicio no iniciado").
    audio_path = os.path.join(base_dir, AUDIO_HELPER_EXE)
    if not os.path.isfile(audio_path):
        audio_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), AUDIO_HELPER_EXE)

    return {
        "dxgi": dxgi_path,
        "webview": webview_path,
        "menu_dir": menu_dir,
        "audio_helper": audio_path
    }


# ==============================================================================
# SERVICIO DE AUDIO INMERSIVO 3D POR CÁMARA
# ==============================================================================

def stop_audio_helper(log=None):
    """
    Detiene el servicio de audio y NO vuelve hasta que el proceso ha desaparecido
    de verdad.

    ORIGEN DEL WinError 32
    --------------------------------------------------------------------------
    Antes esto era un simple `taskkill /F /IM ...` seguido inmediatamente de
    shutil.copy2(). Dos problemas encadenados:

      1. taskkill /F devuelve en cuanto Windows ACEPTA la petición de matar el
         proceso, no cuando el proceso ha muerto. Windows mantiene la imagen del
         .exe mapeada (el "section object") hasta que se libera el último hilo,
         y mientras tanto el archivo sigue bloqueado.
      2. Nadie comprobaba el resultado: si taskkill fallaba (el servicio arrancó
         en otra sesión, o estaba a medias de arrancar), la instalación seguía
         adelante igualmente y reventaba en el copy2.

    Resultado: "[WinError 32] El proceso no tiene acceso al archivo porque está
    siendo utilizado por otro proceso" al copiar mmats_audio_inmersivo.exe.

    Ahora se hace en tres pasos, del más limpio al más bruto, y siempre
    esperando confirmación:
      1. /apagar por HTTP: el servicio restaura el volumen, retira el hook de
         teclado, suelta COM, cierra el socket y sale solo. Es la única vía que
         además deja limpio el directorio temporal de PyInstaller.
      2. TerminateProcess sobre los PID que realmente son el servicio.
      3. Espera activa hasta que el PID desaparece.
    """
    decir = log or (lambda m, l='INFO': None)
    pids = pids_de_imagen(AUDIO_HELPER_EXE)
    if not pids:
        return True, "no estaba en ejecución"

    # 1. Apagado ordenado.
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{puerto_servicio_audio()}/apagar",
                                     method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=3) as r:
            r.read()
        if esperar_a_que_mueran(pids, 8.0):
            decir("  [OK] Servicio de audio detenido de forma ordenada.")
            return True, "apagado ordenado"
    except (urllib.error.URLError, OSError, ValueError):
        pass    # versión antigua sin /apagar, o ya no responde: seguimos

    # 2. Terminación forzada, solo de nuestros PID.
    restantes = [p for p in pids if proceso_vivo(p)]
    for pid in restantes:
        terminar_proceso(pid)

    # 3. Confirmar.
    if esperar_a_que_mueran(restantes, 10.0):
        decir("  [OK] Servicio de audio detenido (cierre forzado).")
        return True, "terminado a la fuerza"

    vivos = [p for p in restantes if proceso_vivo(p)]
    decir(f"  [WARN] El servicio de audio sigue vivo (PID {vivos}).", "WARN")
    return False, f"no se pudo detener: PID {vivos}"


def puerto_servicio_audio():
    """
    Puerto en el que escucha el servicio. El usuario puede haberlo cambiado en
    %APPDATA%\\MULTIMEDIA ATS SANTI\\audio_inmersivo.json; si damos por hecho el
    puerto por defecto, el apagado ordenado falla en silencio y acabamos
    matando el proceso a la fuerza sin necesidad.
    """
    try:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        ruta = os.path.join(base, APP_NAME, "audio_inmersivo.json")
        with open(ruta, "r", encoding="utf-8") as f:
            valor = int(json.load(f).get("port", AUDIO_HELPER_PORT))
        return valor if 1024 <= valor <= 65535 else AUDIO_HELPER_PORT
    except (OSError, ValueError, TypeError):
        return AUDIO_HELPER_PORT


# ==============================================================================
# PROCESOS Y ARCHIVOS BLOQUEADOS (API de Windows, sin lanzar cmd.exe)
# ==============================================================================

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
WAIT_TIMEOUT = 0x102
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
_ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", _ULONG_PTR),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.TerminateProcess.restype = wintypes.BOOL
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.HANDLE]
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
_kernel32.MoveFileExW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


def pids_de_imagen(nombre_exe):
    """PIDs cuyo ejecutable se llama así. Solo lee la lista, no toca nada."""
    nombre = nombre_exe.lower()
    salida = []
    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return salida
    try:
        e = _PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == nombre:
                salida.append(e.th32ProcessID)
            ok = _kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        _kernel32.CloseHandle(snap)
    return salida


def proceso_vivo(pid):
    h = _kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        return False
    try:
        return _kernel32.WaitForSingleObject(h, 0) == WAIT_TIMEOUT
    finally:
        _kernel32.CloseHandle(h)


def terminar_proceso(pid):
    h = _kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h:
        return False
    try:
        return bool(_kernel32.TerminateProcess(h, 0))
    finally:
        _kernel32.CloseHandle(h)


def esperar_a_que_mueran(pids, segundos):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if not any(proceso_vivo(p) for p in pids):
            return True
        time.sleep(0.15)
    return not any(proceso_vivo(p) for p in pids)


def archivo_libre(ruta):
    """
    True si NADIE tiene el archivo abierto. Se abre con dwShareMode=0: si otro
    proceso lo tiene mapeado (un .exe en marcha, una DLL cargada por el juego),
    CreateFileW falla y lo sabemos ANTES de intentar la copia.
    """
    if not os.path.exists(ruta):
        return True
    h = _kernel32.CreateFileW(ruta, GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE:
        return False
    _kernel32.CloseHandle(h)
    return True


def esperar_archivo_libre(ruta, segundos=10.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if archivo_libre(ruta):
            return True
        time.sleep(0.2)
    return archivo_libre(ruta)


def copiar_reemplazando(origen, destino, log=None):
    """
    Copia sobrescribiendo, aunque el destino esté bloqueado por un proceso que
    no ha terminado de morir.

    Truco clave de NTFS: un ejecutable o una DLL en uso NO se puede borrar ni
    sobrescribir, pero SÍ se puede renombrar. Así que si la copia directa choca
    con un WinError 32, se aparta el archivo bloqueado con otro nombre, se
    escribe el nuevo en su sitio y se intenta limpiar el apartado. Si tampoco se
    deja borrar, se marca para que Windows lo elimine en el próximo arranque y
    la instalación termina bien igualmente.
    """
    decir = log or (lambda m, l='INFO': None)
    if os.path.exists(destino):
        esperar_archivo_libre(destino, 8.0)
    try:
        shutil.copy2(origen, destino)
        return True, None
    except OSError as e:
        if getattr(e, "winerror", None) not in (5, 32) or not os.path.exists(destino):
            raise

    apartado = f"{destino}.bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.rename(destino, apartado)
    decir(f"  [INFO] {os.path.basename(destino)} estaba en uso: se aparta como "
          f"{os.path.basename(apartado)} y se instala el nuevo.")
    try:
        shutil.copy2(origen, destino)
    except OSError:
        os.rename(apartado, destino)    # deshacer: mejor dejarlo como estaba
        raise

    if not borrar_o_programar_borrado(apartado):
        decir(f"  [WARN] {os.path.basename(apartado)} sigue en uso; se borrará "
              f"al reiniciar Windows o en la próxima instalación.", "WARN")
    return True, apartado


def borrar_o_programar_borrado(ruta):
    try:
        os.remove(ruta)
        return True
    except OSError:
        pass
    try:
        # Última red: Windows lo borra en el próximo arranque (necesita permisos
        # de administrador; si no los hay, lo recogerá limpiar_restos()).
        return bool(_kernel32.MoveFileExW(ruta, None, MOVEFILE_DELAY_UNTIL_REBOOT))
    except Exception:
        return False


def limpiar_restos(directorio, log=None):
    """Borra los .bak_* que quedaron de instalaciones anteriores y ya están libres."""
    decir = log or (lambda m, l='INFO': None)
    borrados = 0
    try:
        nombres = os.listdir(directorio)
    except OSError:
        return 0
    for nombre in nombres:
        if ".bak_" not in nombre:
            continue
        base = nombre.split(".bak_")[0]
        if base not in ("dxgi.dll", "WebView2Loader.dll", AUDIO_HELPER_EXE):
            continue        # no es nuestro, no se toca
        ruta = os.path.join(directorio, nombre)
        if os.path.isfile(ruta) and archivo_libre(ruta):
            try:
                os.remove(ruta)
                borrados += 1
            except OSError:
                pass
    if borrados:
        decir(f"  [OK] {borrados} archivo(s) apartados de instalaciones previas eliminados.")
    return borrados


def limpiar_menu_obsoleto(target_menu_dir, log=None):
    """
    Quita de MENU_EXTRAIDO, ya instalado, lo que este instalador ya no despliega.

    Solo se borran nombres concretos y conocidos (la subcarpeta BACKUP y las
    notas .txt del desarrollo). Nunca se hace una limpieza "por diferencia":
    si el usuario ha dejado un archivo suyo ahí, se respeta.
    """
    decir = log or (lambda m, l='INFO': None)
    quitados = 0
    for d in MENU_DIRS_EXCLUIDOS:
        ruta = os.path.join(target_menu_dir, d)
        if os.path.isdir(ruta):
            try:
                shutil.rmtree(ruta)
                quitados += 1
            except OSError:
                pass
    for nombre in MENU_ARCHIVOS_EXCLUIDOS:
        for candidato in (nombre, nombre.lower()):
            ruta = os.path.join(target_menu_dir, candidato)
            if os.path.isfile(ruta):
                try:
                    os.remove(ruta)
                    quitados += 1
                except OSError:
                    pass
                break
    if quitados:
        decir(f"  [OK] {quitados} resto(s) obsoleto(s) de versiones anteriores eliminados de MENU_EXTRAIDO.")
    return quitados


def podar_backups(directorio, conservar=BACKUPS_A_CONSERVAR, proteger=None, log=None):
    """
    Deja solo las N copias de seguridad más recientes. Cada instalación creaba
    una carpeta nueva y ninguna se borraba: en la carpeta del juego se acumulan
    decenas de copias idénticas de dxgi.dll (2 MB cada una).
    """
    decir = log or (lambda m, l='INFO': None)
    try:
        carpetas = sorted(
            d for d in os.listdir(directorio)
            if d.startswith("BACKUP_MULTIMEDIAATS_")
            and os.path.isdir(os.path.join(directorio, d))
        )
    except OSError:
        return 0
    protegida = os.path.basename(proteger) if proteger else None
    sobrantes = [d for d in carpetas[:-conservar] if d != protegida] if len(carpetas) > conservar else []
    liberado = 0
    for d in sobrantes:
        ruta = os.path.join(directorio, d)
        try:
            liberado += sum(os.path.getsize(os.path.join(r, f))
                            for r, _s, fs in os.walk(ruta) for f in fs)
            shutil.rmtree(ruta)
        except OSError:
            liberado = max(0, liberado)
    if sobrantes:
        decir(f"  [OK] {len(sobrantes)} copias de seguridad antiguas eliminadas "
              f"({liberado / (1024 * 1024):.0f} MB liberados). Se conservan las "
              f"{conservar} más recientes.")
    return len(sobrantes)


def set_audio_helper_autostart(exe_path, enable=True):
    """
    Registra (o quita) el arranque automático del servicio en HKCU\\...\\Run.
    Se usa HKCU y no HKLM a propósito: no requiere privilegios de administrador
    y el servicio solo necesita los permisos del usuario que juega.
    El propio servicio se queda dormido mientras amtrucks.exe no esté en marcha.
    """
    import winreg
    clave = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, AUDIO_HELPER_RUN_KEY, 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                try:
                    winreg.DeleteValue(k, AUDIO_HELPER_RUN_KEY)
                except FileNotFoundError:
                    pass
        return True, None
    except OSError as e:
        return False, str(e)


def launch_audio_helper(exe_path):
    """
    Arranca el servicio ya mismo para que el usuario no tenga que reiniciar.

    DETACHED_PROCESS es imprescindible: sin él, el servicio sería hijo del
    instalador y arrastraría su consola. No se guarda la referencia al Popen a
    propósito: al salir de la función se libera el handle del hijo, que ya vive
    por su cuenta.
    """
    try:
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
        subprocess.Popen([exe_path], creationflags=flags, close_fds=True,
                         cwd=os.path.dirname(exe_path))
        return True, None
    except Exception as e:
        return False, str(e)

def calculate_sha256(filepath):
    """Calcula el hash SHA-256 de un archivo."""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def check_dll_x64(filepath):
    """Verifica si un archivo PE (DLL) es compatible con arquitectura x64 (AMD64)."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(1024)
            if len(header) < 64 or header[:2] != b'MZ':
                return False, "Cabecera DOS inválida"
            e_lfanew = int.from_bytes(header[0x3C:0x40], byteorder='little')
            f.seek(e_lfanew)
            pe_signature = f.read(4)
            if pe_signature != b'PE\x00\x00':
                return False, "Firma PE inválida"
            machine = int.from_bytes(f.read(2), byteorder='little')
            if machine == 0x8664:  # IMAGE_FILE_MACHINE_AMD64
                return True, "Compatible (x64 / AMD64)"
            return False, f"Arquitectura incompatible: {hex(machine)}"
    except Exception as e:
        return False, str(e)

def is_ats_running():
    """
    Comprueba si el proceso del juego amtrucks.exe está activo.

    Antes se lanzaba `tasklist` con shell=True: eso crea un cmd.exe y un
    tasklist.exe (~150 ms y un parpadeo de consola) cada vez que se llama. Ahora
    se pregunta directamente a la API de Windows.
    """
    return bool(pids_de_imagen(GAME_EXE))

def parse_vdf_library_folders(vdf_path):
    """Parsea el archivo libraryfolders.vdf de Steam para encontrar rutas de librerías."""
    libraries = []
    if not os.path.isfile(vdf_path):
        return libraries
    try:
        with open(vdf_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for line in lines:
            line_str = line.strip()
            if '"path"' in line_str:
                parts = line_str.split('"path"')
                if len(parts) > 1:
                    path_val = parts[1].replace('"', '').strip().replace('\\\\', '\\')
                    if os.path.isdir(path_val):
                        libraries.append(path_val)
    except Exception:
        pass
    return libraries

def detect_ats_installation():
    """Detecta automáticamente la instalación de American Truck Simulator en el sistema."""
    potential_roots = []
    
    # 1. Registro: Desinstalador Steam App 270880 (64-bit y 32-bit WOW64)
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 270880"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 270880"),
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
    ]
    
    for hkey, subkey in registry_keys:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                try:
                    loc, _ = winreg.QueryValueEx(key, "InstallLocation")
                    if loc and os.path.isdir(loc):
                        potential_roots.append(loc)
                except Exception:
                    pass
                try:
                    steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
                    if steam_path and os.path.isdir(steam_path):
                        vdf = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
                        for lib in parse_vdf_library_folders(vdf):
                            potential_roots.append(os.path.join(lib, "steamapps", "common", "American Truck Simulator"))
                        potential_roots.append(os.path.join(steam_path, "steamapps", "common", "American Truck Simulator"))
                except Exception:
                    pass
                try:
                    steam_install, _ = winreg.QueryValueEx(key, "InstallPath")
                    if steam_install and os.path.isdir(steam_install):
                        vdf = os.path.join(steam_install, "steamapps", "libraryfolders.vdf")
                        for lib in parse_vdf_library_folders(vdf):
                            potential_roots.append(os.path.join(lib, "steamapps", "common", "American Truck Simulator"))
                        potential_roots.append(os.path.join(steam_install, "steamapps", "common", "American Truck Simulator"))
                except Exception:
                    pass
        except Exception:
            continue

    # 2. Escaneo en todas las unidades disponibles de Windows (C:, D:, E:, F:, G:, H:, etc.)
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = f"{letter}:\\"
        if os.path.isdir(drive):
            potential_roots.extend([
                os.path.join(drive, "Program Files (x86)", "Steam", "steamapps", "common", "American Truck Simulator"),
                os.path.join(drive, "Program Files", "Steam", "steamapps", "common", "American Truck Simulator"),
                os.path.join(drive, "SteamLibrary", "steamapps", "common", "American Truck Simulator"),
                os.path.join(drive, "Steam", "steamapps", "common", "American Truck Simulator"),
                os.path.join(drive, "Juegos", "American Truck Simulator"),
                os.path.join(drive, "Games", "American Truck Simulator")
            ])
            
    # 3. Comprobar la existencia del binario amtrucks.exe en bin\win_x64
    for root in potential_roots:
        if os.path.isdir(root):
            target_bin = os.path.join(root, "bin", "win_x64")
            exe_path = os.path.join(target_bin, "amtrucks.exe")
            if os.path.isfile(exe_path):
                return os.path.abspath(target_bin)
            # Si el usuario ya apuntó directamente a bin\win_x64
            if os.path.isfile(os.path.join(root, "amtrucks.exe")):
                return os.path.abspath(root)

    return None

def resolve_target_bin_dir(user_path):
    """
    Normaliza y verifica la ruta elegida por el usuario.
    Retorna la ruta absoluta hacia la carpeta bin\\win_x64 donde reside amtrucks.exe.
    """
    if not user_path or not os.path.isdir(user_path):
        return None, "La ruta seleccionada no es un directorio válido."
        
    clean_path = os.path.abspath(user_path.strip('"').strip("'"))
    
    # Caso 1: El usuario seleccionó la carpeta raíz del juego
    sub_bin = os.path.join(clean_path, "bin", "win_x64")
    if os.path.isfile(os.path.join(sub_bin, "amtrucks.exe")):
        return sub_bin, None
        
    # Caso 2: El usuario seleccionó directamente bin\win_x64
    if os.path.isfile(os.path.join(clean_path, "amtrucks.exe")):
        return clean_path, None
        
    # Caso 3: No se encontró amtrucks.exe pero la carpeta existe
    if os.path.isdir(sub_bin):
        return sub_bin, "Advertencia: No se encontró 'amtrucks.exe' en la carpeta bin\\win_x64, pero se usará esta estructura."
        
    return clean_path, "Advertencia: No se detectó 'amtrucks.exe'. Los archivos se instalarán en la carpeta especificada."

# ==============================================================================
# MOTOR PRINCIPAL DE INSTALACIÓN Y DESINSTALACIÓN
# ==============================================================================

class ModInstallerEngine:
    def __init__(self, log_callback=None, progress_callback=None):
        self.log_callback = log_callback or (lambda msg, lvl='INFO': print(f"[{lvl}] {msg}"))
        self.progress_callback = progress_callback or (lambda p, text='': None)

    def log(self, message, level="INFO"):
        self.log_callback(message, level)

    def set_progress(self, percent, status_text=""):
        self.progress_callback(percent, status_text)

    def install(self, target_bin_dir, create_backup=True):
        """Ejecuta la instalación completa de MULTIMEDIA ATS SANTI."""
        sources = get_source_files()
        
        self.log("="*70)
        self.log(f"INICIANDO INSTALACIÓN DE {APP_NAME} v{APP_VERSION}")
        self.log(f"Fecha y hora: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Directorio destino: {target_bin_dir}")
        self.log("="*70)
        self.set_progress(5, "Comprobando entorno...")

        # 1. Comprobar proceso amtrucks.exe
        if is_ats_running():
            err_msg = "American Truck Simulator (amtrucks.exe) está en ejecución. Por favor, cierra el juego antes de continuar."
            self.log(f"[ERROR] {err_msg}", "ERROR")
            return False, err_msg

        # 2. Validar archivos fuente incluidos
        self.log("[1/8] Verificando integridad de los archivos fuente empaquetados...")
        if not os.path.isfile(sources["dxgi"]):
            err_msg = f"Archivo requerido no encontrado: {sources['dxgi']}"
            self.log(f"[ERROR] {err_msg}", "ERROR")
            return False, err_msg
            
        if not os.path.isfile(sources["webview"]):
            err_msg = f"Archivo requerido no encontrado: {sources['webview']}"
            self.log(f"[ERROR] {err_msg}", "ERROR")
            return False, err_msg
            
        if not os.path.isdir(sources["menu_dir"]):
            err_msg = f"Carpeta MENU_EXTRAIDO no encontrada: {sources['menu_dir']}"
            self.log(f"[ERROR] {err_msg}", "ERROR")
            return False, err_msg

        # 3. Comprobar arquitectura x64 de las DLL
        self.set_progress(15, "Verificando compatibilidad x64...")
        dxgi_ok, dxgi_arch = check_dll_x64(sources["dxgi"])
        self.log(f"  - dxgi.dll: {dxgi_arch}")
        if not dxgi_ok:
            return False, f"dxgi.dll no es compatible con x64: {dxgi_arch}"

        wv_ok, wv_arch = check_dll_x64(sources["webview"])
        self.log(f"  - WebView2Loader.dll: {wv_arch}")
        if not wv_ok:
            return False, f"WebView2Loader.dll no es compatible con x64: {wv_arch}"

        os.makedirs(target_bin_dir, exist_ok=True)

        # 3b. Detener el servicio de audio ANTES de tocar nada.
        # Es lo primero que hay que hacer: mientras corre, su .exe está mapeado
        # por Windows y cualquier intento de sobrescribirlo da WinError 32. Y al
        # detenerlo también deja de tocar el volumen del WebView2.
        self.set_progress(22, "Deteniendo el servicio de Audio Inmersivo 3D...")
        self.log("[2/8] Deteniendo el servicio de audio si estaba en marcha...")
        ok_stop, detalle_stop = stop_audio_helper(self.log)
        if not ok_stop:
            self.log(f"  [WARN] {detalle_stop}. Se instalará apartando el archivo en uso.", "WARN")
        else:
            self.log(f"  [OK] Servicio de audio: {detalle_stop}.")

        # Restos de instalaciones anteriores que quedaron bloqueados en su día.
        limpiar_restos(target_bin_dir, self.log)

        # 4. Creación de Backup previo
        self.set_progress(30, "Creando copia de seguridad...")
        backup_folder_name = f"BACKUP_MULTIMEDIAATS_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_dir = os.path.join(target_bin_dir, backup_folder_name)
        
        backed_up_items = []
        if create_backup:
            self.log(f"[3/8] Creando copia de seguridad en: {backup_folder_name}")
            target_dxgi = os.path.join(target_bin_dir, "dxgi.dll")
            target_webview = os.path.join(target_bin_dir, "WebView2Loader.dll")
            target_menu = os.path.join(target_bin_dir, "MENU_EXTRAIDO")

            os.makedirs(backup_dir, exist_ok=True)

            if os.path.isfile(target_dxgi):
                dest = os.path.join(backup_dir, "dxgi.dll")
                shutil.copy2(target_dxgi, dest)
                backed_up_items.append("dxgi.dll")
                self.log("  [BACKUP] dxgi.dll existente respaldado.")

            if os.path.isfile(target_webview):
                dest = os.path.join(backup_dir, "WebView2Loader.dll")
                shutil.copy2(target_webview, dest)
                backed_up_items.append("WebView2Loader.dll")
                self.log("  [BACKUP] WebView2Loader.dll existente respaldado.")

            if os.path.isdir(target_menu):
                dest = os.path.join(backup_dir, "MENU_EXTRAIDO")
                shutil.copytree(target_menu, dest, dirs_exist_ok=True)
                backed_up_items.append("MENU_EXTRAIDO")
                self.log("  [BACKUP] Carpeta MENU_EXTRAIDO existente respaldada.")

            if not backed_up_items:
                self.log("  [INFO] No existían archivos previos que requirieran respaldo.")
                try:
                    os.rmdir(backup_dir)
                    backup_dir = None
                except Exception:
                    pass

        # 4b. Podar copias de seguridad antiguas: sin esto la carpeta del juego
        # engorda unos 3 MB por instalación y nunca se limpia sola.
        podar_backups(target_bin_dir, proteger=backup_dir, log=self.log)

        # 5. Despliegue de DLLs
        self.set_progress(50, "Copiando librerías DLL...")
        self.log("[4/8] Desplegando librerías dinámicas DirectX 11 y WebView2...")
        installed_records = []

        # Copiar dxgi.dll
        dest_dxgi = os.path.join(target_bin_dir, "dxgi.dll")
        copiar_reemplazando(sources["dxgi"], dest_dxgi, self.log)
        dxgi_hash = calculate_sha256(dest_dxgi)
        installed_records.append({
            "relative_path": "dxgi.dll",
            "full_path": dest_dxgi,
            "size_bytes": os.path.getsize(dest_dxgi),
            "sha256": dxgi_hash,
            "type": "dll"
        })
        self.log(f"  [OK] dxgi.dll instalado -> SHA-256: {dxgi_hash[:16]}...")

        # Copiar WebView2Loader.dll
        dest_webview = os.path.join(target_bin_dir, "WebView2Loader.dll")
        copiar_reemplazando(sources["webview"], dest_webview, self.log)
        wv_hash = calculate_sha256(dest_webview)
        installed_records.append({
            "relative_path": "WebView2Loader.dll",
            "full_path": dest_webview,
            "size_bytes": os.path.getsize(dest_webview),
            "sha256": wv_hash,
            "type": "dll"
        })
        self.log(f"  [OK] WebView2Loader.dll instalado -> SHA-256: {wv_hash[:16]}...")

        # 6. Despliegue de MENU_EXTRAIDO y recursos web
        self.set_progress(70, "Desplegando archivos de interfaz HTML/CSS/JS...")
        self.log("[5/8] Desplegando contenido completo de MENU_EXTRAIDO...")
        
        target_menu_dir = os.path.join(target_bin_dir, "MENU_EXTRAIDO")
        os.makedirs(target_menu_dir, exist_ok=True)
        # Instalaciones anteriores dejaron ahí la subcarpeta BACKUP y las notas
        # de desarrollo. Como el instalador nunca borraba lo que dejaba de
        # enviar, esos restos se quedaban para siempre en la carpeta del juego.
        limpiar_menu_obsoleto(target_menu_dir, self.log)

        for root, dirs, files in os.walk(sources["menu_dir"]):
            # No desplegar en la carpeta del juego lo que no forma parte del mod:
            # MENU_EXTRAIDO/BACKUP son copias viejas de los mismos HTML/CSS/JS
            # (226 KB duplicados y desactualizados) y los .txt son notas de
            # desarrollo. Ninguno lo carga el WebView.
            dirs[:] = [d for d in dirs if d.upper() not in MENU_DIRS_EXCLUIDOS]
            rel_dir = os.path.relpath(root, sources["menu_dir"])
            curr_target_dir = target_menu_dir if rel_dir == "." else os.path.join(target_menu_dir, rel_dir)
            os.makedirs(curr_target_dir, exist_ok=True)

            for file in files:
                if file.upper() in MENU_ARCHIVOS_EXCLUIDOS:
                    continue
                src_file_path = os.path.join(root, file)
                dst_file_path = os.path.join(curr_target_dir, file)
                shutil.copy2(src_file_path, dst_file_path)
                f_hash = calculate_sha256(dst_file_path)
                rel_path = os.path.relpath(dst_file_path, target_bin_dir)
                installed_records.append({
                    "relative_path": rel_path.replace("\\", "/"),
                    "full_path": dst_file_path,
                    "size_bytes": os.path.getsize(dst_file_path),
                    "sha256": f_hash,
                    "type": "web_asset"
                })
                self.log(f"  [OK] {rel_path} desplegado.")

        # 6b. Servicio de Audio Inmersivo 3D por cámara
        self.set_progress(80, "Instalando el servicio de Audio Inmersivo 3D...")
        self.log("[6/8] Desplegando el servicio de Audio Inmersivo 3D por cámara...")

        if os.path.isfile(sources["audio_helper"]):
            # Ya se detuvo en el paso [2/8]; aquí solo nos aseguramos de que no
            # ha vuelto a arrancar (autostart, doble clic del usuario...).
            stop_audio_helper(self.log)
            dest_audio = os.path.join(target_bin_dir, AUDIO_HELPER_EXE)
            try:
                copiar_reemplazando(sources["audio_helper"], dest_audio, self.log)
                audio_hash = calculate_sha256(dest_audio)
                installed_records.append({
                    "relative_path": AUDIO_HELPER_EXE,
                    "full_path": dest_audio,
                    "size_bytes": os.path.getsize(dest_audio),
                    "sha256": audio_hash,
                    "type": "audio_service"
                })
                self.log(f"  [OK] {AUDIO_HELPER_EXE} instalado -> SHA-256: {audio_hash[:16]}...")

                ok_reg, err_reg = set_audio_helper_autostart(dest_audio, True)
                if ok_reg:
                    self.log("  [OK] Arranque automático registrado (solo para tu usuario).")
                else:
                    self.log(f"  [WARN] No se pudo registrar el arranque automático: {err_reg}", "WARN")

                ok_run, err_run = launch_audio_helper(dest_audio)
                if ok_run:
                    self.log("  [OK] Servicio iniciado. Se queda dormido hasta que abras ATS.")
                else:
                    self.log(f"  [WARN] No se pudo iniciar ahora: {err_run}. Se iniciará al reiniciar Windows.", "WARN")
            except Exception as e:
                self.log(f"  [WARN] No se pudo instalar el servicio de audio: {e}", "WARN")
        else:
            self.log("  [INFO] Servicio de audio no incluido en este paquete. El mod funcionará "
                     "igual, pero sin atenuación por cámara.")

        # 7. Generación de Manifiesto y Registro de Instalación
        self.set_progress(88, "Generando registros de instalación...")
        self.log("[7/8] Creando manifiesto JSON y log oficial...")

        manifest_data = {
            "mod_name": APP_NAME,
            "version": APP_VERSION,
            "install_date": datetime.datetime.now().isoformat(),
            "target_dir": target_bin_dir,
            "backup_dir": backup_dir,
            "universal_license": UNIVERSAL_LICENSE,
            "installed_files": installed_records
        }
        manifest_path = os.path.join(target_bin_dir, MANIFEST_FILENAME)
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        log_path = os.path.join(target_bin_dir, LOG_FILENAME)
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write(f"REGISTRO OFICIAL DE INSTALACIÓN - {APP_NAME} v{APP_VERSION}\n")
            f.write("="*80 + "\n")
            f.write(f"Fecha de Instalación: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Ruta de Instalación: {target_bin_dir}\n")
            f.write(f"Copia de Respaldo: {backup_dir if backup_dir else 'Ninguna (instalación limpia)'}\n")
            f.write(f"Clave Universal Offline: {UNIVERSAL_LICENSE}\n")
            f.write("="*80 + "\n")
            f.write("ARCHIVOS INSTALADOS Y COMPROBACIONES SHA-256:\n")
            f.write("-"*80 + "\n")
            for rec in installed_records:
                f.write(f"- {rec['relative_path']} ({rec['size_bytes']} bytes) | SHA256: {rec['sha256']}\n")
            f.write("="*80 + "\n")
            f.write("ESTADO: INSTALACIÓN COMPLETADA EXITOSAMENTE SIN ERRORES.\n")
            f.write("="*80 + "\n")

        # 8. Verificación de Integridad Final
        self.set_progress(95, "Verificando integridad final...")
        self.log("[8/8] Comprobando existencia y accesibilidad de todos los archivos...")
        for rec in installed_records:
            if not os.path.isfile(rec["full_path"]):
                return False, f"Fallo al verificar el archivo instalado: {rec['full_path']}"

        self.set_progress(100, "¡Instalación completada exitosamente!")
        self.log("="*70)
        self.log(f"¡{APP_NAME} HA SIDO INSTALADO CORRECTAMENTE!")
        self.log(f"Archivos registrados en: {LOG_FILENAME}")
        self.log(f"Clave de activación offline: {UNIVERSAL_LICENSE}")
        self.log("="*70)
        return True, "Instalación completada con éxito."

    def uninstall(self, target_bin_dir, restore_backup=True):
        """Desinstala de forma limpia MULTIMEDIA ATS SANTI y restaura respaldos."""
        self.log("="*70)
        self.log(f"INICIANDO DESINSTALACIÓN DE {APP_NAME}")
        self.log(f"Directorio: {target_bin_dir}")
        self.log("="*70)
        self.set_progress(10, "Verificando archivos a desinstalar...")

        if is_ats_running():
            err_msg = "American Truck Simulator (amtrucks.exe) está en ejecución. Por favor, cierra el juego antes de desinstalar."
            self.log(f"[ERROR] {err_msg}", "ERROR")
            return False, err_msg

        manifest_path = os.path.join(target_bin_dir, MANIFEST_FILENAME)
        files_to_remove = []
        backup_dir = None

        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest_data = json.load(f)
                    backup_dir = manifest_data.get("backup_dir")
                    for item in manifest_data.get("installed_files", []):
                        files_to_remove.append(item.get("full_path"))
            except Exception as e:
                self.log(f"[WARN] Error leyendo manifiesto: {e}", "WARN")

        # Archivos predeterminados en caso de que el manifiesto no exista
        if not files_to_remove:
            files_to_remove = [
                os.path.join(target_bin_dir, "dxgi.dll"),
                os.path.join(target_bin_dir, "WebView2Loader.dll"),
                os.path.join(target_bin_dir, AUDIO_HELPER_EXE)
            ]

        # Parar el servicio de audio y quitar su arranque automático antes de
        # borrar nada: mientras corre, su .exe está bloqueado por Windows.
        self.set_progress(30, "Deteniendo el servicio de Audio Inmersivo 3D...")
        ok_stop, detalle_stop = stop_audio_helper(self.log)
        if not ok_stop:
            self.log(f"  [WARN] {detalle_stop}. Su .exe podría no poder borrarse todavía.", "WARN")
        ok_reg, err_reg = set_audio_helper_autostart(None, False)
        if ok_reg:
            self.log("  [OK] Arranque automático del servicio de audio eliminado.")
        else:
            self.log(f"  [WARN] No se pudo limpiar el arranque automático: {err_reg}", "WARN")

        self.set_progress(40, "Eliminando archivos del mod...")
        removed_count = 0
        for fpath in files_to_remove:
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                    self.log(f"  [ELIMINADO] {os.path.basename(fpath)}")
                    removed_count += 1
                except OSError as e:
                    # Si algo lo tiene abierto, apartarlo y programar su borrado
                    # en vez de dejar la desinstalación a medias.
                    if borrar_o_programar_borrado(fpath):
                        self.log(f"  [ELIMINADO] {os.path.basename(fpath)}")
                        removed_count += 1
                    else:
                        self.log(f"  [ERROR] No se pudo eliminar {fpath}: {e}", "ERROR")

        # Restos apartados por instalaciones anteriores.
        limpiar_restos(target_bin_dir, self.log)

        # Eliminar carpeta MENU_EXTRAIDO
        target_menu = os.path.join(target_bin_dir, "MENU_EXTRAIDO")
        if os.path.isdir(target_menu):
            try:
                shutil.rmtree(target_menu)
                self.log("  [ELIMINADO] Carpeta MENU_EXTRAIDO eliminada.")
            except Exception as e:
                self.log(f"  [ERROR] No se pudo eliminar MENU_EXTRAIDO: {e}", "ERROR")

        # Eliminar manifiesto y log de instalación
        for aux in [manifest_path, os.path.join(target_bin_dir, LOG_FILENAME)]:
            if os.path.isfile(aux):
                try:
                    os.remove(aux)
                except Exception:
                    pass

        # Restaurar backup si existe
        self.set_progress(75, "Restaurando archivos de respaldo...")
        restored = False
        if restore_backup and backup_dir and os.path.isdir(backup_dir):
            self.log(f"[RESTAURACIÓN] Restaurando copias de seguridad desde: {os.path.basename(backup_dir)}")
            for item in os.listdir(backup_dir):
                s = os.path.join(backup_dir, item)
                d = os.path.join(target_bin_dir, item)
                if os.path.isfile(s):
                    shutil.copy2(s, d)
                    self.log(f"  [RESTAURADO] {item}")
                    restored = True
                elif os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                    self.log(f"  [RESTAURADO] Carpeta {item}")
                    restored = True
            try:
                shutil.rmtree(backup_dir)
                self.log("  [INFO] Copia de seguridad temporal limpiada tras la restauración.")
            except Exception:
                pass

        self.set_progress(100, "Desinstalación finalizada.")
        self.log("="*70)
        self.log(f"{APP_NAME} ha sido desinstalado correctamente.")
        if restored:
            self.log("Los archivos respaldados originales han sido restaurados.")
        self.log("="*70)
        return True, "Desinstalación completada con éxito."


# ==============================================================================
# INTERFAZ GRÁFICA DE USUARIO MODERNA (GUI)
# ==============================================================================

class ModernInstallerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("820x680")
        self.root.minsize(780, 620)
        self.root.configure(bg="#0f172a")
        
        # Intentar habilitar High DPI en Windows
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        # Configurar icono de ventana
        icon_path = os.path.join(get_bundle_dir(), "installer_assets", "installer_icon.ico")
        if not os.path.isfile(icon_path):
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer_assets", "installer_icon.ico")
        if os.path.isfile(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self.engine = ModInstallerEngine(
            log_callback=self.gui_log,
            progress_callback=self.gui_progress
        )

        self.target_path_var = tk.StringVar()
        self.backup_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Listo para instalar")
        self.is_working = False
        self._cerrando = False
        self._hilo_trabajo = None

        self._build_ui()
        # Sin esto, cerrar la ventana con la X mientras un hilo seguía escribiendo
        # en el log dejaba el proceso del instalador vivo en segundo plano.
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.auto_detect_ats()

    def on_close(self):
        """Cierre ordenado de la ventana."""
        if self.is_working:
            if not messagebox.askyesno(
                    "Operación en curso",
                    "Hay una instalación o desinstalación en marcha.\n\n"
                    "Cerrar ahora puede dejar los archivos a medias.\n"
                    "¿Cerrar de todos modos?"):
                return
        self._cerrando = True
        # Cancelar los after() pendientes: si uno se dispara con la ventana ya
        # destruida, Tk lanza una excepción y el proceso puede quedar colgado.
        try:
            for pendiente in self.root.tk.call("after", "info"):
                try:
                    self.root.after_cancel(pendiente)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.root.quit()
        finally:
            self.root.destroy()

    def _build_ui(self):
        # 1. Cabecera con banner y estilo moderno
        header_frame = tk.Frame(self.root, bg="#1e293b", height=90)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        title_container = tk.Frame(header_frame, bg="#1e293b")
        title_container.pack(side="left", padx=25, pady=12)

        lbl_title = tk.Label(
            title_container,
            text="MULTIMEDIA ATS SANTI",
            font=("Segoe UI", 18, "bold"),
            fg="#60a5fa",
            bg="#1e293b"
        )
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(
            title_container,
            text="Instalador Oficial para American Truck Simulator (x64) • DirectX 11 & WebView2",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#1e293b"
        )
        lbl_sub.pack(anchor="w")

        badge_frame = tk.Frame(header_frame, bg="#1e293b")
        badge_frame.pack(side="right", padx=25, pady=15)

        lbl_badge = tk.Label(
            badge_frame,
            text="  v2.0 OFICIAL  ",
            font=("Segoe UI", 10, "bold"),
            fg="#10b981",
            bg="#064e3b",
            relief="flat",
            padx=8,
            pady=4
        )
        lbl_badge.pack()

        # 2. Contenedor Principal
        main_container = tk.Frame(self.root, bg="#0f172a")
        main_container.pack(fill="both", expand=True, padx=25, pady=15)

        # Tarjeta: Selección de Carpeta
        card_folder = tk.Frame(main_container, bg="#1e293b", highlightbackground="#334155", highlightthickness=1)
        card_folder.pack(fill="x", pady=(0, 12))

        folder_inner = tk.Frame(card_folder, bg="#1e293b", padx=16, pady=14)
        folder_inner.pack(fill="x")

        lbl_path_info = tk.Label(
            folder_inner,
            text="Carpeta de American Truck Simulator (o bin\\win_x64):",
            font=("Segoe UI", 10, "bold"),
            fg="#e2e8f0",
            bg="#1e293b"
        )
        lbl_path_info.pack(anchor="w", pady=(0, 6))

        entry_row = tk.Frame(folder_inner, bg="#1e293b")
        entry_row.pack(fill="x")

        self.entry_path = tk.Entry(
            entry_row,
            textvariable=self.target_path_var,
            font=("Segoe UI", 10),
            bg="#0f172a",
            fg="#f8fafc",
            insertbackground="#60a5fa",
            relief="flat",
            highlightbackground="#475569",
            highlightthickness=1
        )
        self.entry_path.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        btn_browse = tk.Button(
            entry_row,
            text="📁 Examinar...",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg="#ffffff",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.browse_folder
        )
        btn_browse.pack(side="left", padx=(0, 6))

        btn_detect = tk.Button(
            entry_row,
            text="🔍 Autodetectar",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.auto_detect_ats
        )
        btn_detect.pack(side="left")

        # Opciones
        opt_frame = tk.Frame(folder_inner, bg="#1e293b")
        opt_frame.pack(fill="x", pady=(10, 0))

        chk_backup = tk.Checkbutton(
            opt_frame,
            text="Crear copia de seguridad automática antes de instalar",
            variable=self.backup_var,
            font=("Segoe UI", 9),
            fg="#cbd5e1",
            bg="#1e293b",
            selectcolor="#0f172a",
            activebackground="#1e293b",
            activeforeground="#ffffff"
        )
        chk_backup.pack(side="left")

        # Tarjeta: Botones de Acción
        action_card = tk.Frame(main_container, bg="#0f172a")
        action_card.pack(fill="x", pady=(0, 10))

        self.btn_install = tk.Button(
            action_card,
            text="▶ INSTALAR MULTIMEDIA ATS SANTI",
            font=("Segoe UI", 11, "bold"),
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            relief="flat",
            padx=20,
            pady=10,
            cursor="hand2",
            command=self.start_install_thread
        )
        self.btn_install.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_uninstall = tk.Button(
            action_card,
            text="🗑️ Desinstalar Mod",
            font=("Segoe UI", 10, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=10,
            cursor="hand2",
            command=self.start_uninstall_thread
        )
        self.btn_uninstall.pack(side="left", padx=(0, 8))

        btn_open_folder = tk.Button(
            action_card,
            text="📂 Abrir Carpeta",
            font=("Segoe UI", 10),
            bg="#334155",
            fg="#f1f5f9",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=10,
            cursor="hand2",
            command=self.open_target_folder
        )
        btn_open_folder.pack(side="left")

        # Barra de progreso y estado
        progress_card = tk.Frame(main_container, bg="#0f172a")
        progress_card.pack(fill="x", pady=(0, 8))

        self.progress_bar = ttk.Progressbar(progress_card, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", ipady=2)

        self.lbl_status = tk.Label(
            progress_card,
            textvariable=self.status_var,
            font=("Segoe UI", 9, "italic"),
            fg="#94a3b8",
            bg="#0f172a"
        )
        self.lbl_status.pack(anchor="w", pady=(4, 0))

        # Tarjeta: Consola de Registro
        log_frame = tk.Frame(main_container, bg="#1e293b", highlightbackground="#334155", highlightthickness=1)
        log_frame.pack(fill="both", expand=True)

        log_header = tk.Frame(log_frame, bg="#1e293b", padx=10, pady=6)
        log_header.pack(fill="x")

        lbl_log_title = tk.Label(
            log_header,
            text="Registro de Operaciones:",
            font=("Segoe UI", 9, "bold"),
            fg="#94a3b8",
            bg="#1e293b"
        )
        lbl_log_title.pack(side="left")

        btn_clear_log = tk.Button(
            log_header,
            text="Limpiar",
            font=("Segoe UI", 8),
            bg="#334155",
            fg="#cbd5e1",
            relief="flat",
            padx=8,
            pady=1,
            command=self.clear_log
        )
        btn_clear_log.pack(side="right")

        self.txt_log = tk.Text(
            log_frame,
            font=("Consolas", 9),
            bg="#090d16",
            fg="#cbd5e1",
            insertbackground="#60a5fa",
            relief="flat",
            wrap="word",
            padx=10,
            pady=8
        )
        self.txt_log.pack(fill="both", expand=True, side="left")

        scroll = tk.Scrollbar(log_frame, command=self.txt_log.yview)
        scroll.pack(side="right", fill="y")
        self.txt_log.config(yscrollcommand=scroll.set)

        # Configuración de tags de color en consola
        self.txt_log.tag_config("INFO", foreground="#cbd5e1")
        self.txt_log.tag_config("OK", foreground="#34d399")
        self.txt_log.tag_config("WARN", foreground="#fbbf24")
        self.txt_log.tag_config("ERROR", foreground="#f87171")
        self.txt_log.tag_config("BACKUP", foreground="#60a5fa")

        # 3. Pie de página informativo
        footer_frame = tk.Frame(self.root, bg="#1e293b", height=38)
        footer_frame.pack(fill="x", side="bottom")
        footer_frame.pack_propagate(False)

        lbl_footer_info = tk.Label(
            footer_frame,
            text=f"Clave Universal: {UNIVERSAL_LICENSE}  |  Atajos: Re Pág (Page Up) / F8",
            font=("Segoe UI", 8, "bold"),
            fg="#94a3b8",
            bg="#1e293b"
        )
        lbl_footer_info.pack(side="left", padx=20, pady=8)

        lbl_footer_right = tk.Label(
            footer_frame,
            text="MULTIMEDIA ATS SANTI (c) 2026",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#1e293b"
        )
        lbl_footer_right.pack(side="right", padx=20, pady=8)

    def gui_log(self, message, level="INFO"):
        if self._cerrando:
            return
        def _append():
            if self._cerrando:
                return
            tag = "INFO"
            if "[OK]" in message or "EXITOSAMENTE" in message or "CORRECTAMENTE" in message:
                tag = "OK"
            elif "[ERROR]" in message or "Fallo" in message:
                tag = "ERROR"
            elif "[WARN]" in message or "Advertencia" in message:
                tag = "WARN"
            elif "[BACKUP]" in message or "[RESTAURADO]" in message:
                tag = "BACKUP"

            self.txt_log.insert(tk.END, message + "\n", tag)
            self.txt_log.see(tk.END)
        self.root.after(0, _append)

    def gui_progress(self, percent, status_text=""):
        if self._cerrando:
            return
        def _update():
            if self._cerrando:
                return
            self.progress_bar["value"] = percent
            if status_text:
                self.status_var.set(status_text)
        self.root.after(0, _update)

    def clear_log(self):
        self.txt_log.delete("1.0", tk.END)

    def auto_detect_ats(self):
        detected = detect_ats_installation()
        if detected:
            self.target_path_var.set(detected)
            self.gui_log(f"[OK] American Truck Simulator detectado automáticamente en:\n{detected}", "OK")
            self.status_var.set("Juego detectado automáticamente. Listo para instalar.")
        else:
            self.gui_log("[WARN] No se detectó automáticamente la instalación de American Truck Simulator.", "WARN")
            self.gui_log("[INFO] Usa el botón 'Examinar...' para seleccionar la carpeta del juego o bin\\win_x64.", "INFO")
            self.status_var.set("No detectado automáticamente. Por favor selecciona la carpeta.")

    def browse_folder(self):
        initial = self.target_path_var.get() or "C:\\"
        folder = filedialog.askdirectory(
            title="Selecciona la carpeta de American Truck Simulator o bin\\win_x64",
            initialdir=initial
        )
        if folder:
            resolved_bin, warn_msg = resolve_target_bin_dir(folder)
            self.target_path_var.set(resolved_bin or folder)
            if warn_msg:
                self.gui_log(f"[WARN] {warn_msg}", "WARN")
            else:
                self.gui_log(f"[OK] Carpeta seleccionada y validada: {resolved_bin}", "OK")

    def open_target_folder(self):
        path = self.target_path_var.get()
        if path and os.path.isdir(path):
            os.startfile(path)
        else:
            messagebox.showwarning("Aviso", "La carpeta seleccionada no existe actualmente.")

    def set_ui_busy(self, busy=True):
        """
        Se llama desde los hilos de trabajo. Tkinter NO es thread-safe: tocar un
        widget fuera del hilo de la GUI cuelga o revienta la ventana de forma
        aleatoria (y era una de las formas de que el instalador se quedara
        colgado al terminar). Todo pasa por root.after().
        """
        self.is_working = busy

        def _aplicar():
            if self._cerrando:
                return
            state = "disabled" if busy else "normal"
            self.btn_install.config(state=state)
            self.btn_uninstall.config(state=state)
        self.root.after(0, _aplicar)

    def _aviso(self, tipo, titulo, mensaje):
        """messagebox desde un hilo de trabajo, servido en el hilo de la GUI."""
        def _mostrar():
            if self._cerrando:
                return
            {"info": messagebox.showinfo, "error": messagebox.showerror}[tipo](titulo, mensaje)
        self.root.after(0, _mostrar)

    def start_install_thread(self):
        if self.is_working:
            return
        raw_path = self.target_path_var.get()
        target_bin, err = resolve_target_bin_dir(raw_path)
        if not target_bin:
            messagebox.showerror("Error", err or "Por favor especifica una ruta válida.")
            return

        if err and "Advertencia" in err:
            if not messagebox.askyesno("Confirmar Instalación", f"{err}\n\n¿Deseas continuar con la instalación en esta carpeta?"):
                return

        self.set_ui_busy(True)
        threading.Thread(target=self._run_install, args=(target_bin,), daemon=True).start()

    def _run_install(self, target_bin):
        try:
            success, msg = self.engine.install(target_bin, create_backup=self.backup_var.get())
        except Exception as e:
            # Sin esto, una excepción aquí mataba el hilo en silencio: la GUI se
            # quedaba con los botones deshabilitados y sin decir nada.
            success, msg = False, f"{type(e).__name__}: {e}"
            self.gui_log(f"[ERROR] Excepción no controlada durante la instalación: {msg}", "ERROR")
        finally:
            self.set_ui_busy(False)
        if success:
            self._aviso("info", "Instalación Exitosa",
                        f"¡{APP_NAME} ha sido instalado correctamente en:\n{target_bin}\n\n"
                        f"Ya puedes abrir American Truck Simulator.")
        else:
            self._aviso("error", "Error de Instalación",
                        f"No se pudo completar la instalación:\n{msg}")

    def start_uninstall_thread(self):
        if self.is_working:
            return
        raw_path = self.target_path_var.get()
        target_bin, _ = resolve_target_bin_dir(raw_path)
        if not target_bin or not os.path.isdir(target_bin):
            messagebox.showerror("Error", "Por favor selecciona una carpeta válida de instalación.")
            return

        if not messagebox.askyesno("Confirmar Desinstalación", f"¿Estás seguro de que deseas desinstalar {APP_NAME} de:\n{target_bin}?"):
            return

        self.set_ui_busy(True)
        threading.Thread(target=self._run_uninstall, args=(target_bin,), daemon=True).start()

    def _run_uninstall(self, target_bin):
        try:
            success, msg = self.engine.uninstall(target_bin, restore_backup=True)
        except Exception as e:
            success, msg = False, f"{type(e).__name__}: {e}"
            self.gui_log(f"[ERROR] Excepción no controlada durante la desinstalación: {msg}", "ERROR")
        finally:
            self.set_ui_busy(False)
        if success:
            self._aviso("info", "Desinstalación Exitosa",
                        f"{APP_NAME} ha sido desinstalado correctamente.")
        else:
            self._aviso("error", "Error", f"Error durante la desinstalación:\n{msg}")


# ==============================================================================
# MODO LÍNEA DE COMANDOS (CLI) Y PUNTO DE ENTRADA
# ==============================================================================

def run_cli_mode():
    args = sys.argv[1:]
    engine = ModInstallerEngine()

    if "--help" in args or "-h" in args:
        print(f"{APP_NAME} - Instalador CLI v{APP_VERSION}")
        print("Uso:")
        print("  --detect                 Detecta la ruta de American Truck Simulator")
        print("  --install [ruta]         Instala el mod en la ruta especificada")
        print("  --uninstall [ruta]       Desinstala el mod de la ruta especificada")
        print("  (Sin argumentos)         Abre la interfaz gráfica moderna")
        return

    if "--detect" in args:
        detected = detect_ats_installation()
        if detected:
            print(f"ATS_DETECTED={detected}")
        else:
            print("ATS_NOT_FOUND")
        return

    if "--install" in args:
        idx = args.index("--install")
        target = args[idx+1] if idx+1 < len(args) else detect_ats_installation()
        if not target:
            print("[ERROR] No se especificó ruta y no se detectó ATS automáticamente.")
            sys.exit(1)
        target_bin, _ = resolve_target_bin_dir(target)
        ok, msg = engine.install(target_bin)
        sys.exit(0 if ok else 1)

    if "--uninstall" in args:
        idx = args.index("--uninstall")
        target = args[idx+1] if idx+1 < len(args) else detect_ats_installation()
        if not target:
            print("[ERROR] No se especificó ruta y no se detectó ATS automáticamente.")
            sys.exit(1)
        target_bin, _ = resolve_target_bin_dir(target)
        ok, msg = engine.uninstall(target_bin)
        sys.exit(0 if ok else 1)


def main():
    # Si se pasan parámetros de línea de comandos, ejecutar en modo CLI
    if len(sys.argv) > 1 and any(arg.startswith("--") for arg in sys.argv[1:]):
        run_cli_mode()
        return

    # Si no hay argumentos, iniciar la GUI moderna
    root = tk.Tk()
    app = ModernInstallerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
================================================================================
MULTIMEDIA ATS SANTI - Audio Inmersivo 3D por Camara
================================================================================
La multimedia (Spotify / YouTube / Twitch / Netflix, que corren dentro de
msedgewebview2.exe) suena EXCLUSIVAMENTE con la camara 1. En cuanto el jugador
sale de la cabina se corta, y al volver se reactiva.

  Camara 1 (cabina)      -> volumen pleno del usuario
  Camaras 2..8 / libre   -> silencio total, sin residuo ni cola

QUE SIGNIFICA "SILENCIO TOTAL" AQUI, Y POR QUE NO ES UN SetMute
--------------------------------------------------------------------------------
Fuera de la camara 1 se escribe 0.0 en TODOS los canales de la sesion
(IChannelAudioVolume). Windows mezcla volumen_final = maestro * canal, asi que
un canal a 0.0 no es "volumen bajo": es la muestra a cero, silencio digital. No
queda cola, ni residuo, ni fragmentos.

Y no se usa ISimpleAudioVolume.SetMute a proposito. El watchdog de audio de
dxgi.dll lo deshace activamente -en el binario estan las cadenas
"mm_audio_force_unmute" y "[WV2-AUDIO] revertido MUTE de {} sessao(oes) do
WebView2"-, asi que un mute nuestro duraria hasta su siguiente pasada (~1 s) y
volveria el audio a rachas. El volumen por canal es el unico mando que ese
watchdog no toca, de modo que aqui no hay carrera que perder.

Lo que NO se hace es pausar la reproduccion: pararla de verdad exigiria
secuestrar las teclas multimedia del sistema (afectaria tambien a Spotify de
escritorio) y el jugador perderia la posicion del video o de la cancion al
volver a la cabina. El stream sigue donde estaba, pero no llega ni una muestra
audible a la mezcla mientras la camara no sea la 1.

POR QUE ES UN PROCESO EXTERNO Y NO ESTA DENTRO DE dxgi.dll
--------------------------------------------------------------------------------
1. No existe codigo fuente C++ del mod: dxgi.dll es un binario de terceros que
   el proyecto solo parchea byte a byte con pefile. Anadir deteccion de camara
   ahi obligaria a inyectar ensamblador x64 en un code cave.
2. El SDK oficial de SCS Telemetry NO expone la camara activa. La DLL solo
   registra los canales game.time, truck.electric.enabled y truck.engine.enabled.
3. Hacerlo en JavaScript dentro del WebView no funciona en pantalla completa:
   al abrir Spotify la pagina lucidgfx_home.html se sustituye por la del sitio y
   cualquier script del mod deja de existir. Un proceso externo sigue vivo
   siempre, en pantalla completa y en modo split.

CONVIVENCIA CON EL WATCHDOG DE AUDIO DEL MOD
--------------------------------------------------------------------------------
dxgi.dll trae su propio vigilante de audio ("[WV2-AUDIO] watchdog de audio
ativo") que reaplica mm_audio_volume sobre las sesiones del WebView2. Por eso
este proceso no escribe el volumen una sola vez: lo REAFIRMA en cada ciclo
mientras el estado sea exterior, de modo que gana siempre la carrera. En cabina
hace lo contrario: si detecta que el volumen cambio por fuera (el usuario movio
el slider del overlay o pulso Ctrl +/-), adopta ese valor como nuevo volumen
base en vez de pelearse con el.

POR QUE EL PC SE COLGABA AL CERRAR EL JUEGO (corregido el 2026-08-29)
--------------------------------------------------------------------------------
Este proceso instalaba un hook de teclado de bajo nivel (WH_KEYBOARD_LL) que
vivia SIEMPRE, desde el arranque de Windows, jugase o no el usuario. Windows
ejecuta ese callback en el hilo que lo instalo y le concede LowLevelHooksTimeout
-300 ms de fabrica- para responder a CADA tecla del sistema. Si no contesta a
tiempo, el teclado y el raton de todo el equipo se quedan clavados.

El callback necesita el GIL de Python, y el resto del programa se lo quitaba:

  - _procesar_tecla leia lucidgfx_settings.ini del disco, creaba objetos psutil,
    tomaba estado.lock (compartido con el hilo de audio y con el servidor HTTP)
    y escribia en el log. Todo eso, dentro del hook.
  - psutil.Process().parents(), que se usaba para saber si un msedgewebview2.exe
    colgaba de ATS, cuesta ~50 ms medidos en este equipo. Se llamaba por cada
    sesion de audio nueva.
  - psutil.process_iter() recorria los 300 procesos del sistema cada 1,5 s
    mientras el juego no estuviese.
  - y soltar(), que se ejecuta justo al detectar que ATS se ha cerrado, empezaba
    por un GetAllSessions() completo: la llamada COM mas lenta del programa,
    lanzada en el peor instante posible, con el juego y sus WebView2
    desmontandose. Ademas iba con pid_juego=0, valor con el que el filtro daba
    por bueno CUALQUIER WebView2 del sistema.

Al cerrar el juego coincidian las cuatro cosas y el hook se quedaba segundos sin
interprete: de ahi el tiron que obligaba a reiniciar a lo bruto.

QUE SE CAMBIO
--------------------------------------------------------------------------------
  1. El hook solo existe mientras amtrucks.exe esta en marcha (HookTeclado).
     Fuera de la partida no queda ningun hook global instalado en el sistema.
  2. El callback solo copia (tecla, pid_con_foco) a una cola y devuelve. El
     trabajo real ocurre en hilo_eventos, un hilo normal.
  3. soltar() ya no reenumera: devuelve a 1.0 las sesiones que ya tiene en la
     mano, que son las unicas que pueden estar atenuadas.
  4. Fuera psutil del camino caliente. Se localiza el juego una vez y se guarda
     su HANDLE: saber si sigue vivo pasa de 1,35 ms a 0,9 us, y de regalo Windows
     no puede reciclar ese PID y colarnos otro programa. La ascendencia de los
     WebView2 se resuelve sobre un censo de procesos en memoria: 50 ms -> 1 us.
  5. En cabina (ganancia 1.0, nada que corregir) se barre cada 3 s en vez de
     cada 1 s y el bucle despierta la mitad de veces.
  6. El hilo de audio corre por debajo de lo normal y el del hook por encima, y
     el intervalo de cambio de hilo del interprete baja a 1 ms.
  7. Parada ordenada por POST /apagar, para que el instalador no tenga que
     matarlo con taskkill /F dejando el hook huerfano.

USO
--------------------------------------------------------------------------------
    python mmats_audio_inmersivo.py                 # demonio normal
    python mmats_audio_inmersivo.py --diagnostico   # informe y salida
    python mmats_audio_inmersivo.py --consola       # demonio con log en pantalla
================================================================================
"""

import argparse
import atexit
import ctypes
import json
import os
import re
import sys
import threading
import time
from collections import deque
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = "MULTIMEDIA ATS SANTI"
PUERTO_DEFECTO = 48221
GAME_EXE = "amtrucks.exe"
WEBVIEW_EXE = "msedgewebview2.exe"

# Ganancia inmersiva por camara. Es TODA la logica de audio del servicio.
#
#   camara == 1  -> GANANCIA_CABINA    (audio activado y audible)
#   camara != 1  -> GANANCIA_EXTERIOR  (silencio, sin excepciones)
#
# No son configurables a proposito: el audio de la tablet es exclusivo de la
# camara 1. Un valor intermedio dejaria musica sonando fuera de la cabina, que
# es justo lo que este servicio existe para evitar.
GANANCIA_CABINA = 1.0
GANANCIA_EXTERIOR = 0.0

# Valores por defecto de la configuracion persistida.
#
# exterior_pct y fade_ms se conservan porque el overlay del mod los lee y los
# envia, pero ya no gobiernan nada: se fuerzan a 0 al cargar y el POST /config
# los ignora. Asi el panel sigue funcionando (muestra "silenciado") sin poder
# reintroducir audio fuera de la cabina ni retrasar el corte con un fundido.
CONFIG_DEFECTO = {
    "enabled": True,        # audio inmersivo activo
    "exterior_pct": 0,      # fijo: fuera de la camara 1 no hay volumen que repartir
    "fade_ms": 0,           # fijo: el corte y la reactivacion son instantaneos
    "port": PUERTO_DEFECTO,
}

# Claves que se aceptan por compatibilidad pero ya no se aplican.
CONFIG_FIJA = ("exterior_pct", "fade_ms")


# ==============================================================================
# Rutas y configuracion
# ==============================================================================

def dir_datos():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    ruta = os.path.join(base, APP_NAME)
    os.makedirs(ruta, exist_ok=True)
    return ruta


RUTA_CONFIG = os.path.join(dir_datos(), "audio_inmersivo.json")
RUTA_LOG = os.path.join(dir_datos(), "audio_inmersivo.log")

_log_lock = threading.Lock()
_log_consola = False
_log_fichero = None
_log_bytes = 0
LOG_MAXIMO = 1_048_576


def log(msg):
    """
    Escribe una linea en el log.

    Antes cada linea abria el fichero, consultaba su tamano con os.path.getsize()
    y lo volvia a cerrar: tres viajes al disco por linea. Ahora el handle se
    mantiene abierto y el tamano se lleva en un contador, asi que rotar cuesta lo
    mismo pero registrar no cuesta casi nada. Sigue haciendo flush en cada linea:
    si el equipo se cuelga, el log tiene que contar hasta el ultimo segundo.
    """
    global _log_fichero, _log_bytes
    linea = time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg)
    with _log_lock:
        if _log_consola:
            print(linea, flush=True)
        try:
            if _log_fichero is None:
                _log_bytes = os.path.getsize(RUTA_LOG) if os.path.exists(RUTA_LOG) else 0
                _log_fichero = open(RUTA_LOG, "a", encoding="utf-8")
            if _log_bytes > LOG_MAXIMO:
                _log_fichero.close()
                os.replace(RUTA_LOG, RUTA_LOG + ".old")
                _log_fichero = open(RUTA_LOG, "a", encoding="utf-8")
                _log_bytes = 0
            datos = linea + "\n"
            _log_fichero.write(datos)
            _log_fichero.flush()
            _log_bytes += len(datos)
        except OSError:
            _log_fichero = None


def cargar_config():
    cfg = dict(CONFIG_DEFECTO)
    try:
        with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
            guardado = json.load(f)
        if isinstance(guardado, dict):
            cfg.update({k: v for k, v in guardado.items() if k in CONFIG_DEFECTO})
    except (OSError, ValueError):
        pass
    cfg["enabled"] = bool(cfg["enabled"])
    # Un json viejo puede traer exterior_pct=12 y fade_ms=250 de la version que
    # atenuaba en vez de silenciar. Se normalizan aqui para que una instalacion
    # actualizada no siga oyendo la musica desde fuera del camion.
    for clave in CONFIG_FIJA:
        cfg[clave] = 0
    cfg["port"] = max(1024, min(65535, int(cfg["port"])))
    return cfg


def guardar_config(cfg):
    try:
        tmp = RUTA_CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, RUTA_CONFIG)
    except OSError as e:
        log(f"No se pudo guardar la configuracion: {e}")


# ==============================================================================
# controls.sii -> que teclas cambian de camara
# ==============================================================================

# Nombres de tecla de ATS -> codigo virtual de Windows.
_VK_NOMBRES = {}
for _i in range(10):
    _VK_NOMBRES[f"key{_i}"] = 0x30 + _i          # key0..key9  -> '0'..'9'
for _c in range(ord("a"), ord("z") + 1):
    _VK_NOMBRES[chr(_c)] = 0x41 + (_c - ord("a"))  # a..z
for _i in range(1, 13):
    _VK_NOMBRES[f"f{_i}"] = 0x6F + _i            # f1..f12 -> VK_F1..VK_F12
for _i in range(10):
    _VK_NOMBRES[f"num{_i}"] = 0x60 + _i          # teclado numerico
_VK_NOMBRES.update({
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "escape": 0x1B,
    "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25,
    "right": 0x27, "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3,
    "lalt": 0xA4, "ralt": 0xA5, "numplus": 0x6B, "numminus": 0x6D,
    "nummultiply": 0x6A, "numdivide": 0x6F, "numperiod": 0x6E,
})

# Acciones de camara de ATS. cam1 es la unica interior.
_ACCIONES_CAMARA = [f"cam{i}" for i in range(1, 9)] + ["camdbg"]
_ACCIONES_CICLO = ["j_tr_cam_swi", "camcycle"]

_RE_MIX = re.compile(r'mix\s+([a-z0-9_]+)\s+`([^`]*)`', re.IGNORECASE)
_RE_TECLA = re.compile(r'keyboard\.([a-z0-9_]+)', re.IGNORECASE)


def dir_perfiles_ats():
    docs = os.path.join(os.path.expanduser("~"), "Documents", "American Truck Simulator")
    return os.path.join(docs, "profiles")


def perfil_mas_reciente():
    """El perfil que el jugador uso por ultima vez (profile.sii mas nuevo)."""
    raiz = dir_perfiles_ats()
    if not os.path.isdir(raiz):
        return None
    mejor, mejor_ts = None, -1
    for nombre in os.listdir(raiz):
        ruta = os.path.join(raiz, nombre)
        marca = os.path.join(ruta, "profile.sii")
        if os.path.isfile(marca):
            ts = os.path.getmtime(marca)
            if ts > mejor_ts:
                mejor, mejor_ts = ruta, ts
    return mejor


def nombre_legible_perfil(ruta_perfil):
    """Los perfiles de ATS llevan el nombre en hexadecimal."""
    if not ruta_perfil:
        return "?"
    carpeta = os.path.basename(ruta_perfil)
    try:
        return bytes.fromhex(carpeta).decode("utf-8", "replace")
    except ValueError:
        return carpeta


# Mapa por defecto (bindings de fabrica de ATS) por si no hay controls.sii.
MAPA_DEFECTO = {
    "interior": {0x31},                                              # tecla 1
    "exterior": {0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x30},    # 2..8 y 0 (libre)
    "ciclo": {0x43},                                                 # tecla C
}


def leer_mapa_camaras(ruta_perfil):
    """
    Extrae de controls.sii que teclas activan cada camara.
    Devuelve {"interior": {vk}, "exterior": {vk}, "ciclo": {vk}}.
    """
    if not ruta_perfil:
        return dict(MAPA_DEFECTO), "sin perfil (usando bindings de fabrica)"

    ruta = os.path.join(ruta_perfil, "controls.sii")
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except OSError as e:
        return dict(MAPA_DEFECTO), f"no se pudo leer controls.sii ({e})"

    mapa = {"interior": set(), "exterior": set(), "ciclo": set()}
    for accion, binding in _RE_MIX.findall(texto):
        accion = accion.lower()
        if accion in _ACCIONES_CAMARA:
            destino = "interior" if accion == "cam1" else "exterior"
        elif accion in _ACCIONES_CICLO:
            destino = "ciclo"
        else:
            continue
        for tecla in _RE_TECLA.findall(binding):
            vk = _VK_NOMBRES.get(tecla.lower())
            if vk is not None:
                mapa[destino].add(vk)

    if not mapa["interior"] and not mapa["exterior"]:
        return dict(MAPA_DEFECTO), "controls.sii sin bindings de camara (usando los de fabrica)"

    # Una tecla no puede significar dos cosas: la camara directa manda sobre el ciclo.
    mapa["ciclo"] -= mapa["interior"] | mapa["exterior"]
    return mapa, "leido de controls.sii"


# ==============================================================================
# Estado compartido entre hilos
# ==============================================================================

class Estado:
    def __init__(self, cfg):
        self.lock = threading.Lock()
        self.cfg = cfg
        # Aviso de "la camara ha cambiado" para el hilo de audio.
        #
        # Es lo que evita tener un bucle vigilando la camara: el hilo de audio
        # duerme en este evento en vez de sondear, y el hilo de eventos -que ya
        # existe para consumir las teclas del hook- lo despierta en el instante
        # del cambio. Cero sondeo, cero hilos nuevos, latencia de milisegundos.
        self.senal_camara = threading.Event()
        self.interior = True        # se asume cabina al arrancar
        self.camara = 1             # ultima camara conocida (1..8, 0 = libre)
        self.juego_activo = False
        self.sesiones = 0
        # Volumen maestro de la sesion, 0-100. Lo gobierna dxgi.dll (slider del
        # overlay / Ctrl +/- / watchdog); aqui solo se LEE para mostrarlo.
        self.base_pct = 100.0
        self.interact = False       # el cursor F8 tiene tomado el teclado
        self.mapa = dict(MAPA_DEFECTO)
        self.origen_mapa = "pendiente"
        self.perfil = "?"
        self.cambios = 0
        self.parada = None      # callable inyectado en main() para /apagar

    def pedir_parada(self):
        if self.parada:
            self.parada()

    def instantanea(self):
        with self.lock:
            return {
                "ok": 1,
                "enabled": self.cfg["enabled"],
                "exterior_pct": self.cfg["exterior_pct"],
                "fade_ms": self.cfg["fade_ms"],
                "interior": 1 if self.interior else 0,
                "camara": self.camara,
                "juego": 1 if self.juego_activo else 0,
                "sesiones": self.sesiones,
                "base_pct": round(self.base_pct, 1),
                "interact": 1 if self.interact else 0,
                "perfil": self.perfil,
                "origen_mapa": self.origen_mapa,
                "cambios": self.cambios,
            }


# ==============================================================================
# Hook de teclado de bajo nivel (WH_KEYBOARD_LL)
# ==============================================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelKeyboardProc, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_longlong
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL

WM_QUIT = 0x0012
WM_APP_HOOK_ON = 0x8001         # WM_APP+1: el juego arranco, poner el hook
WM_APP_HOOK_OFF = 0x8002        # WM_APP+2: el juego se fue, quitarlo
PM_NOREMOVE = 0x0000

# Orden con el que ATS recorre las camaras al pulsar la tecla de ciclo.
_ORDEN_CICLO = [1, 2, 3, 4, 5, 6, 7, 8]


def pid_en_primer_plano():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


# ==============================================================================
# Procesos y prioridades sin psutil (el camino caliente del servicio)
# ==============================================================================
#
# POR QUE SE SACO psutil DE AQUI
# ------------------------------------------------------------------------------
# psutil.process_iter() abre un handle y construye un objeto Python por CADA
# proceso del sistema. El servicio lo hacia hasta 40 veces por minuto, siempre,
# desde el arranque de Windows. Eso no solo gasta CPU: es trabajo en Python
# puro, y mientras dura, el interprete no puede atender el callback del hook de
# teclado. Windows concede LowLevelHooksTimeout (300 ms de fabrica) a ese
# callback; si no responde, congela el teclado y el raton de TODO el sistema.
#
# Aqui se usa el API nativo, que corre fuera del GIL y sin objetos intermedios:
#   - un CreateToolhelp32Snapshot puntual cuando de verdad hay que buscar algo,
#   - y un HANDLE abierto al juego mientras dura la partida, de modo que saber
#     si sigue vivo cuesta un WaitForSingleObject(0). De regalo, el handle fija
#     la identidad del proceso: Windows no puede reciclar ese PID y colarnos
#     otro programa como si fuese ATS.

TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
WAIT_TIMEOUT = 0x00000102

# Margen que se le da a los WebView2 del mod para cerrarse solos cuando ATS
# termina. Pasado ese tiempo, los que sigan vivos son huerfanos de verdad.
GRACIA_HUERFANOS = 6.0
THREAD_PRIORITY_ABOVE_NORMAL = 1
THREAD_PRIORITY_BELOW_NORMAL = -1


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ULONG_PTR),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetCurrentThread.restype = wintypes.HANDLE
kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
kernel32.SetThreadPriority.restype = wintypes.BOOL
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL


def censo_procesos():
    """{pid: (nombre_en_minusculas, ppid)} con una sola llamada al sistema."""
    censo = {}
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return censo
    try:
        entrada = PROCESSENTRY32W()
        entrada.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entrada))
        while ok:
            censo[entrada.th32ProcessID] = (entrada.szExeFile.lower(),
                                            entrada.th32ParentProcessID)
            ok = kernel32.Process32NextW(snap, ctypes.byref(entrada))
    finally:
        kernel32.CloseHandle(snap)
    return censo


def ruta_exe(pid):
    """Ruta completa del ejecutable de un PID, o None. Sustituye a psutil.exe()."""
    if not pid:
        return None
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        tam = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(tam.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
            return buf.value
    finally:
        kernel32.CloseHandle(h)
    return None


def prioridad_hilo(valor):
    """Ajusta la prioridad del hilo que llama. Nunca debe abortar el arranque."""
    try:
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), valor)
    except Exception:
        pass


class RastreadorJuego:
    """
    Localiza amtrucks.exe y comprueba si sigue vivo sin volver a enumerar nada.

    Mientras el juego corre no se recorre la lista de procesos ni una sola vez:
    basta con preguntarle al handle. Solo cuando el juego no esta (o acaba de
    cerrarse) se hace un barrido, y como mucho cada ESPERA_BUSQUEDA segundos.
    """

    ESPERA_BUSQUEDA = 3.0

    def __init__(self):
        self._pid = 0
        self._handle = None
        self._ultimo_barrido = 0.0

    @property
    def pid(self):
        return self._pid

    def _cerrar(self):
        if self._handle:
            try:
                kernel32.CloseHandle(self._handle)
            except Exception:
                pass
        self._handle = None
        self._pid = 0

    def vivo(self):
        if not self._handle:
            return False
        if kernel32.WaitForSingleObject(self._handle, 0) == WAIT_TIMEOUT:
            return True
        self._cerrar()
        return False

    def refrescar(self):
        """PID del juego, o 0 si no esta en marcha."""
        if self.vivo():
            return self._pid
        ahora = time.monotonic()
        if ahora - self._ultimo_barrido < self.ESPERA_BUSQUEDA:
            return 0
        self._ultimo_barrido = ahora
        for pid, (nombre, _padre) in censo_procesos().items():
            if nombre == GAME_EXE:
                h = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if h:
                    self._handle, self._pid = h, pid
                    return pid
        return 0

    def soltar(self):
        self._cerrar()


class HookTeclado:
    """
    Hook WH_KEYBOARD_LL que (a) solo existe mientras se juega y (b) no hace
    absolutamente nada caro dentro del callback.

    POR QUE SE REESCRIBIO: ESTO ERA LO QUE COLGABA EL PC AL CERRAR EL JUEGO
    ------------------------------------------------------------------------------
    Un hook de bajo nivel se ejecuta en el hilo que lo instalo, y Windows le da
    LowLevelHooksTimeout (300 ms de fabrica) para responder a CADA tecla del
    sistema. Si no contesta a tiempo, el teclado y el raton de todo el equipo se
    quedan clavados hasta que lo haga.

    La version anterior, dentro de ese callback:
      - leia lucidgfx_settings.ini del disco (tecla_interact),
      - creaba objetos psutil,
      - tomaba estado.lock, que comparte con el hilo de audio y con el servidor
        HTTP del overlay,
      - y escribia una linea en el log, con su propio lock y su acceso a disco.

    Y todo eso necesita el GIL. Al cerrar el juego, el hilo de audio lanzaba a la
    vez una enumeracion COM completa de sesiones (GetAllSessions) justo mientras
    ATS y sus msedgewebview2.exe se estaban desmontando -la llamada mas lenta de
    todo el ciclo de vida-, mas un psutil.process_iter() en bucle buscando un
    juego que ya no estaba. El callback se quedaba sin interprete durante
    segundos y Windows congelaba la entrada. Ese es el tiron que obligaba a
    reiniciar a lo bruto.

    Ahora el callback copia un entero a una cola y devuelve; el trabajo de
    verdad -mapa de teclas, foco, log- ocurre en un hilo normal (hilo_eventos).
    Y fuera de la partida no queda ningun hook global instalado en el sistema.
    """

    def __init__(self, cola, aviso):
        self._cola = cola                   # deque acotado, compartido
        self._aviso = aviso                 # Event: despierta a hilo_eventos
        self._hook = None
        self._tid = 0
        # El puntero se guarda como atributo a proposito: si lo recolecta el GC
        # mientras el hook vive, Windows salta a memoria liberada.
        self._puntero = LowLevelKeyboardProc(self._on_key)

    # -- callback ---------------------------------------------------------
    def _on_key(self, nCode, wParam, lParam):
        # Presupuesto: microsegundos. Ni disco, ni locks, ni log, ni psutil.
        # pid_en_primer_plano() son dos llamadas a user32 que se resuelven fuera
        # del GIL, y hay que hacerlas aqui: 200 ms mas tarde el foco puede ser
        # otro y la tecla se atribuiria a la ventana equivocada.
        if nCode == 0 and (wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN):
            try:
                vk = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
                self._cola.append((vk, pid_en_primer_plano()))
                self._aviso.set()
            except Exception:
                pass                        # jamas dejar escapar nada al hook
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    # -- instalacion ------------------------------------------------------
    def _instalar(self):
        if self._hook is not None:
            return
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._puntero, None, 0)
        if not self._hook:
            self._hook = None
            log(f"FALLO al instalar el hook de teclado (error {ctypes.get_last_error()})")
        else:
            log("Hook de teclado instalado (ATS en marcha).")

    def _retirar(self):
        if self._hook is None:
            return
        try:
            user32.UnhookWindowsHookEx(self._hook)
        except Exception:
            pass
        self._hook = None
        self._cola.clear()
        log("Hook de teclado retirado (ATS cerrado).")

    # -- avisos desde otros hilos ----------------------------------------
    def _postear(self, mensaje):
        if self._tid:
            user32.PostThreadMessageW(self._tid, mensaje, 0, 0)

    def encender(self):
        self._postear(WM_APP_HOOK_ON)

    def apagar(self):
        self._postear(WM_APP_HOOK_OFF)

    def terminar(self):
        self._postear(WM_QUIT)

    # -- hilo -------------------------------------------------------------
    def bucle(self, listo):
        """
        Bomba de mensajes bloqueante. GetMessageW duerme sin consumir CPU y es
        justo lo que Windows necesita para poder entregar el callback; se
        despierta sola con los WM_APP_* que le mandan los demas hilos.
        """
        self._tid = kernel32.GetCurrentThreadId()
        # Forzar la creacion de la cola de mensajes antes de que nadie postee:
        # un PostThreadMessage a un hilo sin cola se pierde en silencio.
        arranque = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(arranque), None, 0, 0, PM_NOREMOVE)
        # Este hilo debe responder antes que nadie: es el que sostiene la
        # entrada de todo el sistema mientras el hook esta puesto.
        prioridad_hilo(THREAD_PRIORITY_ABOVE_NORMAL)
        listo.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP_HOOK_ON:
                self._instalar()
            elif msg.message == WM_APP_HOOK_OFF:
                self._retirar()
            else:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        self._retirar()


def hilo_eventos(estado, rastreador, cola, aviso, parar):
    """
    Consume las teclas que el hook dejo en la cola. Aqui si se puede tomar
    locks, leer ficheros y escribir en el log: un retraso en este hilo no afecta
    a la entrada del sistema, solo a la latencia del cambio de camara (que en la
    practica es de milisegundos, porque el hook despierta este hilo al instante).
    """
    while not parar.is_set():
        aviso.wait(0.5)
        aviso.clear()
        while cola:
            try:
                vk, pid_foco = cola.popleft()
            except IndexError:
                break
            try:
                _procesar_tecla(estado, rastreador.pid, pid_foco, vk)
            except Exception as e:
                log(f"Error procesando una tecla: {e}")


VK_INTERACT_DEFECTO = 0x77      # F8, el que inyecta build_multimedia_ats_santi.py


def tecla_interact(pid_juego, _cache=[0, 0.0, 0]):
    """
    Tecla que activa/desactiva el cursor multimedia (F8 de fabrica).

    Se lee del propio lucidgfx_settings.ini del mod ([Hotkeys] hotkey_interact),
    que vive junto a amtrucks.exe, en vez de codificarla aqui: si el usuario la
    reasigna desde el overlay, este servicio la sigue sin tocar nada. El
    resultado se cachea 30 s.

    OJO: esto toca el disco. Se llama desde hilo_eventos, NUNCA desde el hook de
    teclado (ver HookTeclado): una lectura de fichero dentro del callback congela
    la entrada de todo el sistema mientras dura.
    """
    vk, visto, pid_visto = _cache
    ahora = time.monotonic()
    if vk and pid_juego == pid_visto and (ahora - visto) < 30.0:
        return vk
    vk = VK_INTERACT_DEFECTO
    exe = ruta_exe(pid_juego)
    if exe:
        try:
            ini = os.path.join(os.path.dirname(exe), "lucidgfx_settings.ini")
            with open(ini, "r", encoding="utf-8", errors="ignore") as f:
                for linea in f:
                    linea = linea.strip()
                    if linea.startswith("hotkey_interact"):
                        valor = int(linea.split("=", 1)[1].strip())
                        if 1 <= valor <= 254:
                            vk = valor
                        break
        except (OSError, ValueError):
            pass
    _cache[:] = [vk, ahora, pid_juego]
    return vk


def _procesar_tecla(estado, pid_juego, pid_foco, vk):
    # Solo reaccionar si ATS tenia el foco EN EL MOMENTO DE LA PULSACION: si no,
    # el jugador estaba escribiendo en otra ventana y un "2" cualquiera no debe
    # bajar la musica. El foco lo captura el hook y viaja con la tecla, para que
    # no se falsee si este hilo llega tarde.
    if not pid_juego or pid_foco != pid_juego:
        return

    # Espejo del modo interactivo del mod.
    #
    # Mientras el cursor F8 esta activo, dxgi.dll se queda el teclado del juego
    # (ver "[WV2-KB-POLL] bloqueio teclado" en lucidgfx.log) y lo reenvia a la
    # pagina: escribir una URL de YouTube o buscar en Spotify manda esas teclas
    # al WebView, NO a ATS. Nuestro hook de bajo nivel las ve igualmente, asi
    # que sin esto teclear un "2" bajaba la musica aunque la camara no hubiese
    # cambiado. Se mantiene el mismo estado que el mod, con la misma tecla y la
    # misma condicion de foco, para no desincronizarse.
    if vk == tecla_interact(pid_juego):
        with estado.lock:
            estado.interact = not estado.interact
            activo = estado.interact
        log(f"Cursor multimedia {'ACTIVO' if activo else 'inactivo'}: "
            f"teclas de camara {'ignoradas' if activo else 'atendidas'}.")
        return

    with estado.lock:
        if estado.interact:
            return              # el jugador esta escribiendo en la tablet
        mapa = estado.mapa
        if vk in mapa["interior"]:
            nueva_cam = 1
        elif vk in mapa["exterior"]:
            nueva_cam = _camara_de_tecla(mapa, vk)
        elif vk in mapa["ciclo"]:
            try:
                idx = _ORDEN_CICLO.index(estado.camara)
            except ValueError:
                idx = 0
            nueva_cam = _ORDEN_CICLO[(idx + 1) % len(_ORDEN_CICLO)]
        else:
            return

        interior = (nueva_cam == 1)
        if nueva_cam == estado.camara and interior == estado.interior:
            return
        estado.camara = nueva_cam
        estado.interior = interior
        estado.cambios += 1
    # Despertar al hilo de audio AHORA, sin esperar a su siguiente vuelta: es lo
    # que hace que salir de la cabina corte el sonido en el acto y volver a ella
    # lo devuelva igual de rapido.
    estado.senal_camara.set()
    log(f"Camara -> {nueva_cam} ({'INTERIOR' if interior else 'EXTERIOR'})")


def _camara_de_tecla(mapa, vk):
    """Traduce la tecla pulsada al numero de camara (para que el ciclo siga bien)."""
    if 0x31 <= vk <= 0x38:      # '1'..'8'
        return vk - 0x30
    if vk == 0x30:              # '0' = camara libre de desarrollador
        return 0
    return 2                    # binding personalizado: exterior generico


# ==============================================================================
# Recogida de los WebView2 que el mod deja huerfanos al cerrar el juego
# ==============================================================================
#
# POR QUE HACE FALTA ESTO
# ------------------------------------------------------------------------------
# La multimedia del mod corre dentro de msedgewebview2.exe, y ese arbol de
# procesos NO siempre muere con ATS: al cerrar el juego se quedan vivos el
# proceso raiz y sus hijos (GPU, red, renderer, uno por pestana). Como no tienen
# ventana, el jugador no los ve, pero siguen ahi ocupando memoria. Y se ACUMULAN:
# cada partida deja otra tanda. Medido en este equipo con el juego ya cerrado:
# 25 procesos y 1,4 GB de RAM retenidos. De ahi que el equipo se arrastre despues
# de jugar y que cerrar el juego se sienta como un tiron.
#
# COMO SE HACE SIN RIESGO
# ------------------------------------------------------------------------------
# Solo se tocan los WebView2 que cuelgan del PID de ATS: se recorre la
# descendencia completa del juego (el WebView2 raiz cuelga de ATS y los de
# GPU/red/renderer cuelgan a su vez de ese raiz). Nunca se mata "cualquier
# msedgewebview2.exe", porque WhatsApp, Copilot y el propio Windows usan el mismo
# ejecutable y les estariamos cerrando la aplicacion al usuario.
#
# Los handles se abren MIENTRAS el juego vive, que es cuando se puede establecer
# el parentesco. Despues ya no haria falta: al morir ATS se pierde el arbol. Un
# handle abierto ademas fija la identidad del proceso, asi que Windows no puede
# reciclar ese PID y colarnos otro programa entre medias.
#
# Al detectar que ATS se ha ido se les da GRACIA_HUERFANOS segundos para cerrarse
# solos (lo normal) y solo se remata a los que sigan vivos pasado ese margen.

class RecolectorWebView:
    def __init__(self):
        self._handles = {}      # pid -> HANDLE
        self._pid_juego = 0

    def observar(self, pid_juego, censo):
        """
        Apunta los msedgewebview2.exe que cuelgan de ATS. Barato: solo recorre el
        censo que ya esta en memoria, sin abrir procesos ni usar psutil.
        """
        if pid_juego != self._pid_juego:
            self.soltar()
            self._pid_juego = pid_juego

        hijos = {}
        for pid, (_nombre, ppid) in censo.items():
            hijos.setdefault(ppid, []).append(pid)

        pendientes = list(hijos.get(pid_juego, ()))
        vistos = set()
        while pendientes:
            pid = pendientes.pop()
            if pid in vistos:
                continue
            vistos.add(pid)
            pendientes.extend(hijos.get(pid, ()))
            dato = censo.get(pid)
            if dato and dato[0] == WEBVIEW_EXE and pid not in self._handles:
                h = kernel32.OpenProcess(
                    PROCESS_TERMINATE | SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                    False, pid)
                if h:
                    self._handles[pid] = h

    def _vivos(self):
        muertos = []
        for pid, h in self._handles.items():
            if kernel32.WaitForSingleObject(h, 0) != WAIT_TIMEOUT:
                muertos.append(pid)
        for pid in muertos:
            kernel32.CloseHandle(self._handles.pop(pid))
        return list(self._handles.items())

    def recolectar(self, parar):
        """Llamar justo despues de que ATS desaparezca."""
        if not self._handles:
            return 0
        total = len(self._handles)
        fin = time.monotonic() + GRACIA_HUERFANOS
        while time.monotonic() < fin:
            if not self._vivos():
                break
            if parar.wait(0.5):
                break

        rematados = 0
        for pid, h in self._vivos():
            if kernel32.TerminateProcess(h, 0):
                rematados += 1
            else:
                log(f"No se pudo cerrar el WebView2 huerfano {pid} "
                    f"(error {ctypes.get_last_error()}).")
        self.soltar()
        if rematados:
            log(f"WebView2 huerfanos del mod cerrados: {rematados} de {total} "
                f"(el resto se cerro solo).")
        return rematados

    def soltar(self):
        for h in self._handles.values():
            kernel32.CloseHandle(h)
        self._handles.clear()
        self._pid_juego = 0


# ==============================================================================
# Control de volumen WASAPI sobre las sesiones del WebView2
# ==============================================================================
#
# POR QUE SE USA EL VOLUMEN POR CANAL Y NO EL VOLUMEN MAESTRO DE LA SESION
# ------------------------------------------------------------------------------
# dxgi.dll trae un watchdog de audio que, ~1 vez por segundo, reescribe
# mm_audio_volume sobre las sesiones del WebView2 con ISimpleAudioVolume
# (verificado en el binario: usa IAudioSessionManager2 + ISimpleAudioVolume y
# NO usa IChannelAudioVolume). La primera version de este servicio escribia ese
# mismo ISimpleAudioVolume, asi que los dos se peleaban por el mismo valor:
#
#     t+0.00  watchdog  -> 100%
#     t+0.10  servicio  -> 12%
#     t+1.02  watchdog  -> 100%      <- ~100 ms de musica a todo volumen
#     t+1.12  servicio  -> 12%          cada segundo, estando fuera del camion
#
# Eso es exactamente el "audio entrecortado / en pequenos fragmentos / residual
# desde fuera". Se ve en lucidgfx.log como una racha de
# "[WV2-AUDIO] volume aplicado 100% em 1 sessao(oes)" cada 1,02 s mientras el
# jugador esta en camara exterior. Acelerar el bucle no lo arregla: solo acorta
# el pitido, no lo elimina.
#
# La solucion no es correr mas, es dejar de compartir el mando. Windows aplica
# volumen_final = maestro (ISimpleAudioVolume) * canal (IChannelAudioVolume),
# y son dos campos independientes: escribir uno no altera el otro (comprobado
# contra una sesion real). Asi que:
#
#     maestro -> lo sigue gobernando el mod (slider del overlay, Ctrl +/-,
#                watchdog). No lo tocamos NUNCA.
#     canal   -> lo gobierna este servicio. Es la "ganancia inmersiva":
#                1.0 en la camara 1, 0.0 en cualquier otra.
#
# Resultado: cero carreras, cero parpadeos, y el usuario puede mover su volumen
# en cualquier momento sin que nada lo sobrescriba; lo que ajusta es el volumen
# que oira al volver a la cabina, porque fuera de ella el producto es cero.

def _importar_audio():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    return comtypes, AudioUtilities


def _es_webview_del_juego(pid, pid_juego, censo, cache):
    """
    Solo tocar los WebView2 que cuelgan de ATS. Asi no bajamos el volumen de un
    Edge o de otra app del usuario que tambien use msedgewebview2.exe.

    La ascendencia se resuelve subiendo por el censo -un diccionario ya en
    memoria- en lugar de con psutil.Process.parents(), que abria un handle por
    cada antepasado y por cada sesion de audio, varias veces por segundo.
    El resultado se cachea por PID.
    """
    if not pid:
        return False
    if pid in cache:
        return cache[pid]
    resultado = False
    dato = censo.get(pid)
    if dato and dato[0] == WEBVIEW_EXE:
        if not pid_juego:
            resultado = True                # solo el diagnostico llega asi
        else:
            actual, saltos = dato[1], 0
            while actual and saltos < 16:   # tope, por si un PID reciclado cierra un ciclo
                if actual == pid_juego:
                    resultado = True
                    break
                padre = censo.get(actual)
                if padre is None:
                    break
                actual = padre[1]
                saltos += 1
    cache[pid] = resultado
    return resultado


class ControlAudio:
    """
    Aplica la ganancia inmersiva sobre el volumen POR CANAL de las sesiones del
    WebView2 del juego. Ver la explicacion larga de arriba: el volumen maestro
    es del mod, el de canal es nuestro.
    """

    # s entre enumeraciones de sesiones. GetAllSessions() es una llamada COM
    # cara; en cabina no hace falta correr (ver hilo_audio).
    INTERVALO_SCAN = 1.0
    INTERVALO_SCAN_CABINA = 3.0
    # Suelo para las reenumeraciones forzadas. Al salir de la cabina se pide una
    # inmediata, pero sin este tope, machacar las teclas de camara lanzaria un
    # GetAllSessions() -la llamada COM mas cara del programa- por pulsacion.
    INTERVALO_MINIMO = 0.2

    def __init__(self):
        self._sesiones = []     # [(clave, IChannelAudioVolume, n_canales)]
        self._maestro = []      # ISimpleAudioVolume, solo para LEER e informar
        self._firma = ()        # claves de las sesiones vistas en el ultimo scan
        self._ultimo_scan = 0.0
        self._cache_padre = {}  # pid -> es WebView2 de ATS
        self._pid_cacheado = 0
        self._ganancia = None   # ultima ganancia escrita (0.0-1.0)

    def refrescar(self, pid_juego, forzar=False, intervalo=None):
        """
        Reenumera las sesiones. Devuelve True si el conjunto cambio, para que el
        llamante reaplique la ganancia sobre las sesiones nuevas: una pestana que
        empieza a sonar aparece con el canal a 1.0 y se oiria a todo volumen
        estando fuera del camion.
        """
        ahora = time.monotonic()
        if intervalo is None:
            intervalo = self.INTERVALO_SCAN
        desde_el_ultimo = ahora - self._ultimo_scan
        if desde_el_ultimo < (self.INTERVALO_MINIMO if forzar else intervalo):
            return False
        self._ultimo_scan = ahora

        if pid_juego != self._pid_cacheado:
            self._cache_padre.clear()       # otro arranque del juego, otros PIDs
            self._pid_cacheado = pid_juego
        elif len(self._cache_padre) > 256:
            # Windows recicla PIDs: sin este tope el cache crecia sin limite
            # durante toda la sesion y podia dar por bueno un PID heredado.
            self._cache_padre.clear()

        _, AudioUtilities = _importar_audio()
        sesiones, maestro, claves = [], [], []
        censo = None
        try:
            for s in AudioUtilities.GetAllSessions():
                # s.ProcessId es un entero que ya trae la interfaz COM; s.Process
                # construia ademas un objeto psutil por sesion y por barrido.
                try:
                    pid = s.ProcessId
                except Exception:
                    continue
                if pid not in self._cache_padre:
                    if censo is None:
                        censo = censo_procesos()    # una sola foto por barrido
                    _es_webview_del_juego(pid, pid_juego, censo, self._cache_padre)
                if not self._cache_padre.get(pid):
                    continue
                try:
                    cav = s.channelAudioVolume()
                    n = cav.GetChannelCount()
                    if n <= 0:
                        continue
                    clave = s.InstanceIdentifier or id(s)
                    sesiones.append((clave, cav, n))
                    claves.append(clave)
                except Exception:
                    continue
                try:
                    maestro.append(s.SimpleAudioVolume)
                except Exception:
                    pass
        except Exception as e:
            log(f"No se pudieron enumerar las sesiones de audio: {e}")
            return False

        firma = tuple(sorted(str(c) for c in claves))
        cambio = firma != self._firma
        self._sesiones, self._maestro, self._firma = sesiones, maestro, firma
        return cambio

    @property
    def n_sesiones(self):
        return len(self._sesiones)

    @property
    def ganancia(self):
        return self._ganancia

    def volumen_maestro(self):
        """El volumen que gobierna el mod, 0-100. Solo se LEE, para informar en
        el overlay: quien lo escribe es dxgi.dll."""
        for v in list(self._maestro):
            try:
                return v.GetMasterVolume() * 100.0
            except Exception:
                try:
                    self._maestro.remove(v)
                except ValueError:
                    pass
        return None

    def aplicar(self, ganancia, forzar=False):
        """
        Escribe la ganancia (0.0-1.0) en todos los canales de todas las sesiones.
        Sin cambio de valor y sin sesiones nuevas no escribe nada: en cabina el
        servicio no hace ni una sola llamada COM.
        """
        ganancia = max(0.0, min(1.0, ganancia))
        if not forzar and self._ganancia is not None and abs(ganancia - self._ganancia) < 0.0005:
            return
        muertas = []
        for entrada in self._sesiones:
            _clave, cav, n = entrada
            try:
                for i in range(n):
                    cav.SetChannelVolume(i, ganancia, None)
            except Exception:
                muertas.append(entrada)
        for entrada in muertas:
            try:
                self._sesiones.remove(entrada)
            except ValueError:
                pass
        self._ganancia = ganancia

    def soltar(self, pid_juego=0):
        """
        Devolver a 1.0 las sesiones que tenemos y olvidarlas. Pase lo que pase
        (juego cerrado, funcion apagada, servicio muriendose) el usuario nunca se
        queda con la musica atenuada.

        ESTA FUNCION YA NO REENUMERA, Y ESO ES DELIBERADO
        --------------------------------------------------------------------------
        Antes empezaba por un refrescar(forzar=True), es decir, un GetAllSessions()
        completo. Y se llama justo al detectar que ATS se ha cerrado: el peor
        instante posible, con el juego y sus msedgewebview2.exe desmontandose,
        donde esa llamada COM puede tardar segundos con el interprete tomado.
        Ademas se llamaba con pid_juego=0, y con 0 el filtro aceptaba CUALQUIER
        WebView2 del sistema, no solo los del juego.

        Y no hacia ninguna falta: las unicas sesiones que pueden estar atenuadas
        son las que ya tenemos en la mano, porque son las unicas que hemos
        tocado. Cualquier otra sigue en 1.0.
        """
        try:
            if self._sesiones and self._ganancia is not None and self._ganancia < 1.0:
                self.aplicar(1.0, forzar=True)
        except Exception:
            pass
        self._sesiones, self._maestro, self._firma = [], [], ()
        self._ganancia = None
        self._cache_padre.clear()
        self._pid_cacheado = 0


def hilo_audio(estado, parar, rastreador, hook):
    """
    Unico hilo que habla con WASAPI. Ademas es quien enciende y apaga el hook de
    teclado, para que fuera de la partida no quede ningun hook global instalado.

    Se ejecuta con prioridad por debajo de lo normal: su trabajo no es urgente y
    asi no le quita turno ni al juego ni al hilo del hook.

    NO SONDEA LA CAMARA. Duerme en estado.senal_camara, que el hilo de eventos
    dispara justo cuando el jugador cambia de camara. Los tiempos de espera de
    abajo son solo la red de seguridad para detectar pestanas nuevas, no la
    latencia del corte: esa la marca el evento y son milisegundos.
    """
    comtypes, _ = _importar_audio()
    comtypes.CoInitialize()
    prioridad_hilo(THREAD_PRIORITY_BELOW_NORMAL)
    control = ControlAudio()
    recolector = RecolectorWebView()
    ultimo_censo = 0.0          # ultima vez que se apunto la descendencia de ATS
    ultimo_interior = None      # None = todavia no hemos aplicado nada
    aviso_sin_sesion = 0.0
    apagado = False             # la funcion esta desactivada y ya hemos soltado
    hook_puesto = False

    def dormir(segundos):
        """
        Espera, pero se despierta en el acto si cambia la camara o si hay que
        parar (parada_ordenada() dispara la misma senal). El clear() va al
        principio de cada vuelta, no aqui, para que un cambio ocurrido mientras
        aplicabamos la ganancia no se pierda.
        """
        estado.senal_camara.wait(segundos)

    try:
        while not parar.is_set():
            # Consumir el aviso ANTES de leer el estado: si la camara cambia a
            # partir de este punto, la senal se queda puesta y la espera del
            # final de la vuelta retorna sin dormir. Asi no hay cambio perdido
            # por mucho que el jugador machaque las teclas de camara.
            estado.senal_camara.clear()
            pid = rastreador.refrescar()

            # El hook solo vive mientras vive el juego.
            if bool(pid) != hook_puesto:
                hook_puesto = bool(pid)
                (hook.encender if hook_puesto else hook.apagar)()

            if not pid:
                # Sin juego: soltar el control y dormir barato. soltar() ya no
                # reenumera nada, asi que este camino -el del cierre del juego-
                # cuesta microsegundos en vez de bloquearse contra el desmontaje
                # de ATS y de sus WebView2.
                if control.n_sesiones or control.ganancia is not None:
                    control.soltar()
                    log("ATS cerrado: ganancia inmersiva liberada (volumen del usuario intacto).")
                # El juego se ha ido: rematar los WebView2 del mod que hayan
                # sobrevivido. Sin esto se acumulan partida tras partida y acaban
                # reteniendo mas de un giga con el juego ya cerrado.
                recolector.recolectar(parar)
                ultimo_censo = 0.0
                ultimo_interior = None
                with estado.lock:
                    estado.juego_activo = False
                    estado.sesiones = 0
                    # ATS siempre arranca la partida en la camara 1. Sin este
                    # reinicio, cerrar el juego estando fuera de la cabina dejaba
                    # el servicio creyendo que seguimos en la camara 3, y en la
                    # siguiente partida el audio nacia mudo hasta que el jugador
                    # pulsaba "1" a ciegas.
                    estado.camara = 1
                    estado.interior = True
                parar.wait(2.0)
                continue

            # Apuntar la descendencia WebView2 de ATS mientras el juego vive, que
            # es cuando se puede establecer el parentesco. Cada 5 s basta y cuesta
            # una sola foto de procesos.
            ahora_censo = time.monotonic()
            if ahora_censo - ultimo_censo > 5.0:
                ultimo_censo = ahora_censo
                try:
                    recolector.observar(pid, censo_procesos())
                except Exception as e:
                    log(f"No se pudo apuntar la descendencia del juego: {e}")

            with estado.lock:
                estado.juego_activo = True
                cfg = dict(estado.cfg)
                interior = estado.interior
                camara = estado.camara

            if not cfg["enabled"]:
                # Funcion apagada: devolver el mando entero al mod.
                if not apagado:
                    control.soltar(pid)
                    ultimo_interior = None
                    apagado = True
                    log("Audio inmersivo desactivado: ganancia liberada.")
                dormir(1.0)
                continue
            apagado = False

            # La camara 1 es la cabina, y la unica en la que suena la multimedia.
            # Cualquier otra -2..8 o la camara libre- va a silencio.
            cambio_camara = (interior != ultimo_interior)

            # En cabina la ganancia es 1.0, que es justo con la que nace toda
            # sesion nueva: no hay nada que corregir, asi que se puede barrer
            # tres veces mas despacio. Fuera del camion si conviene detectar
            # rapido una pestana que empieza a sonar a todo volumen.
            #
            # Al cambiar de camara se reenumera en el acto (forzar): una pestana
            # que empezo a sonar justo antes del cambio aun no estaria en la
            # lista, y se oiria desde fuera hasta el siguiente barrido.
            intervalo = (ControlAudio.INTERVALO_SCAN_CABINA if interior
                         else ControlAudio.INTERVALO_SCAN)
            sesiones_nuevas = control.refrescar(pid,
                                                forzar=cambio_camara and not interior,
                                                intervalo=intervalo)
            n = control.n_sesiones
            with estado.lock:
                estado.sesiones = n
                maestro = control.volumen_maestro()
                if maestro is not None:
                    estado.base_pct = maestro

            if n == 0:
                ahora = time.monotonic()
                if ahora - aviso_sin_sesion > 60:
                    aviso_sin_sesion = ahora
                    log("Aun sin sesiones de audio del WebView2 (abre Spotify/YouTube en la tablet).")
                # ultimo_interior NO se toca: si el jugador cambia de camara sin
                # musica abierta, el siguiente barrido con sesiones ya la aplica
                # por sesiones_nuevas (la firma habra cambiado de vacia a llena).
                dormir(1.0)
                continue

            # Toda la decision de audio, en una linea. Sin fundido: el enunciado
            # es "detener inmediatamente", y un fundido de salida es justamente
            # musica sonando fuera de la cabina durante 250 ms.
            destino = GANANCIA_CABINA if interior else GANANCIA_EXTERIOR

            # aplicar() no escribe si el valor no ha cambiado, asi que las
            # vueltas de vigilancia no cuestan ni una llamada COM. Se fuerza solo
            # cuando hay sesiones nuevas -nacen con el canal a 1.0 y se oirian a
            # todo volumen estando fuera- o cuando acabamos de cambiar de camara.
            control.aplicar(destino, forzar=sesiones_nuevas or cambio_camara)
            if cambio_camara:
                ultimo_interior = interior
                log("Audio " + ("ACTIVADO (camara 1)" if interior
                                else f"SILENCIADO (camara {camara})"))

            # Estas esperas ya no marcan la latencia del corte -eso lo hace
            # senal_camara- sino cada cuanto se busca una pestana nueva. Por eso
            # pueden ser largas: en cabina el servicio se queda dormido de verdad.
            dormir(intervalo)
    finally:
        # Pase lo que pase, nunca dejar al usuario con la musica atenuada.
        try:
            control.soltar(rastreador.pid)
            log("Cerrando: ganancia inmersiva liberada.")
        except Exception:
            pass
        try:
            hook.apagar()
        except Exception:
            pass
        try:
            # Si el que se cierra es este servicio y el juego sigue vivo, NO se
            # rematan sus WebView2: la tablet del camion tiene que seguir
            # funcionando. Solo se sueltan los handles.
            if rastreador.pid:
                recolector.soltar()
            else:
                recolector.recolectar(parar)
        except Exception:
            pass
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


# ==============================================================================
# Servidor local: lo consume el overlay del mod (lucidgfx_overlay.html)
# ==============================================================================

# ==============================================================================
# Control por voz (SAPI 5, es-ES, sin conexion)
# ==============================================================================
# Modulo INDEPENDIENTE: vive en este proceso, que ya existe y ya esta corriendo
# junto al juego. No abre ventanas, no crea sesiones nuevas y no toca ni el
# audio inmersivo ni el hook de camaras: solo se cuelga del servidor HTTP que
# este proceso ya publicaba para el overlay.
#
# Por que aqui y no dentro del WebView2 de la multimedia:
#   - dxgi.dll NO registra add_PermissionRequested, asi que el WebView2 no puede
#     conceder el microfono; y el runtime de WebView2 no trae el servicio de
#     reconocimiento de Chromium. La Web Speech API no es una opcion.
#   - Windows si trae un motor es-ES sin conexion (Microsoft Speech Recognizer
#     8.0 Spanish - Spain), accesible por SAPI 5 via COM. comtypes ya es
#     dependencia de este proceso (lo usa pycaw), asi que no se anade nada.
#
# Reparto de trabajo (cada comando por el camino que YA funciona):
#   - Raton y volumen -> aqui, sintetizando las teclas rapidas que dxgi.dll ya
#     escucha (F8 = hotkey_interact, Ctrl +/- = hotkey_vol_up/down). Es el mismo
#     camino que el teclado fisico, sin tocar el binario.
#   - Navegacion y play/pausa -> los ejecuta la propia multimedia: se publican
#     en /voz y lucidgfx_home.html los recoge y llama a SUS funciones ya
#     existentes (go, launchApp, gpsClick...). Ver COMANDOS_EN_LA_HOME.

VK_F8 = 0x77
VK_CONTROL = 0x11
VK_OEM_PLUS = 0xBB          # hotkey_vol_up   (187)
VK_OEM_MINUS = 0xBD         # hotkey_vol_down (189)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("relleno", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _pulsar(vks, con_ctrl=False):
    """Sintetiza una pulsacion de teclas hacia la ventana en primer plano."""
    secuencia = []
    if con_ctrl:
        secuencia.append((VK_CONTROL, 0))
    for vk in vks:
        secuencia.append((vk, 0))
    for vk in reversed(vks):
        secuencia.append((vk, KEYEVENTF_KEYUP))
    if con_ctrl:
        secuencia.append((VK_CONTROL, KEYEVENTF_KEYUP))

    eventos = (_INPUT * len(secuencia))()
    for i, (vk, flags) in enumerate(secuencia):
        eventos[i].type = INPUT_KEYBOARD
        eventos[i].ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0,
                                    dwExtraInfo=None)
    user32.SendInput(len(secuencia), ctypes.byref(eventos), ctypes.sizeof(_INPUT))


# Comandos que ejecuta la multimedia (la home los recoge por /voz).
COMANDOS_EN_LA_HOME = {"youtube", "spotify", "netflix", "twitch", "gps",
                       "play", "pause", "cerrar"}

# Gramatica: frases exactas -> (comando, confirmacion que se muestra en pantalla).
# Se declaran variantes naturales porque el motor es de vocabulario cerrado:
# cuantas mas formas se declaren, menos se equivoca.
COMANDOS_VOZ = [
    (("abrir youtube", "youtube", "pon youtube"), "youtube", "YouTube"),
    (("abrir spotify", "spotify", "pon spotify"), "spotify", "Spotify"),
    (("abrir netflix", "netflix", "pon netflix"), "netflix", "Netflix"),
    (("abrir twitch", "twitch", "pon twitch"), "twitch", "Twitch"),
    (("abrir gps", "gps", "abrir mapa"), "gps", "GPS"),
    (("subir volumen", "sube el volumen", "mas volumen"), "vol_subir", "Volumen +"),
    (("bajar volumen", "baja el volumen", "menos volumen"), "vol_bajar", "Volumen -"),
    (("reproducir", "reanudar", "play"), "play", "Reproduciendo"),
    (("pausar", "pausa", "detener"), "pause", "En pausa"),
    (("cerrar multimedia", "cerrar", "volver al inicio"), "cerrar", "Multimedia cerrada"),
    (("activar mouse", "activar raton", "activar el raton"), "raton_on", "Raton activado"),
    (("desactivar mouse", "desactivar raton", "desactivar el raton"), "raton_off", "Raton desactivado"),
]

# Frases que se reconocen pero NO son ejecutables con la arquitectura actual: se
# avisa en pantalla en vez de fallar en silencio. Ver el informe de integracion.
COMANDOS_SIN_RUTA = [
    (("silenciar", "silencio", "mutear"), "silenciar", "Silenciar: no disponible"),
    (("volumen al diez", "volumen al veinte", "volumen al treinta",
      "volumen al cuarenta", "volumen al cincuenta", "volumen al sesenta",
      "volumen al setenta", "volumen al ochenta", "volumen al noventa",
      "volumen al cien"), "volumen_pct", "Volumen exacto: no disponible"),
]

SRA_TOP_LEVEL = 0x1
SRA_DYNAMIC = 0x20
SGDS_ACTIVE = 1
SGDS_INACTIVE = 0


def _interfaz_eventos_sapi(cc):
    """
    Devuelve _ISpeechRecoContextEvents, generando el typelib si hiciera falta.

    comtypes no trae las interfaces COM escritas: las genera leyendo el typelib y
    las deja como modulos .py en comtypes/gen. Dentro del .exe ese directorio es
    de solo lectura, asi que tienen que viajar ya generados (lo hace el .spec).
    Si aun asi faltaran, se intenta generarlos en caliente desde sapi.dll, que es
    la via que funciona al ejecutar el .py suelto.
    """
    try:
        from comtypes.gen.SpeechLib import _ISpeechRecoContextEvents
    except ImportError:
        cc.GetModule("sapi.dll")
        from comtypes.gen.SpeechLib import _ISpeechRecoContextEvents
    return _ISpeechRecoContextEvents


class ControlVoz:
    """Reconocedor de comandos en espanol. Arranca y para bajo demanda."""

    def __init__(self, estado):
        self.estado = estado
        self.lock = threading.Lock()
        self.activo = False
        self.disponible = None      # None = todavia sin probar
        self.motivo = ""
        self.seq = 0
        self.ultimo = {"comando": "", "texto": "", "aviso": ""}
        self._parar = threading.Event()
        self._hilo = None
        self._frases = {}
        for frases, comando, aviso in COMANDOS_VOZ + COMANDOS_SIN_RUTA:
            for f in frases:
                self._frases[f] = (comando, aviso)

    # -- API que usa el servidor HTTP -----------------------------------------
    def instantanea(self):
        with self.lock:
            return {
                "ok": 1,
                "disponible": 1 if self.disponible else 0,
                "motivo": self.motivo,
                "escuchando": 1 if self.activo else 0,
                "seq": self.seq,
                "comando": self.ultimo["comando"],
                "texto": self.ultimo["texto"],
                "aviso": self.ultimo["aviso"],
            }

    def encender(self):
        with self.lock:
            if self.activo:
                return True
            self._parar.clear()
            self.activo = True
            self.disponible = None
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="voz")
        self._hilo.start()
        # Esperar a saber si el motor arranca, para poder contestar al boton.
        for _ in range(60):
            if self.disponible is not None:
                break
            time.sleep(0.05)
        return bool(self.disponible)

    def apagar(self):
        with self.lock:
            self.activo = False
        self._parar.set()

    # -- Motor ----------------------------------------------------------------
    def _publicar(self, comando, aviso, texto):
        with self.lock:
            self.seq += 1
            self.ultimo = {"comando": comando, "aviso": aviso, "texto": texto}
        log(f"[VOZ] '{texto}' -> {comando or aviso}")

    def _ejecutar_local(self, comando):
        """Comandos que se resuelven aqui, con las teclas que el mod ya escucha."""
        if not self.estado.juego_activo:
            return False
        if comando in ("raton_on", "raton_off"):
            quiere = (comando == "raton_on")
            if self.estado.interact == quiere:
                return True                     # ya esta como se pide
            _pulsar([VK_F8])
            return True
        if comando == "vol_subir":
            _pulsar([VK_OEM_PLUS], con_ctrl=True)
            return True
        if comando == "vol_bajar":
            _pulsar([VK_OEM_MINUS], con_ctrl=True)
            return True
        return False

    def _gramatica_xml(self):
        """Escribe la gramatica de comandos en el directorio de datos.

        SAPI acepta la gramatica por XML (CmdLoadFromFile). Se usa esa via y no
        AddWordTransition porque comtypes no sabe pasar el parametro opcional
        DestState de esa llamada y el motor devuelve E_INVALIDARG.
        LANGID 0C0A = es-ES, que es el motor instalado en Windows.
        """
        partes = ['<GRAMMAR LANGID="0C0A">', '  <RULE NAME="mmats" TOPLEVEL="ACTIVE">', '    <L>']
        for frase in self._frases:
            partes.append("      <P>%s</P>" % frase)
        partes += ["    </L>", "  </RULE>", "</GRAMMAR>", ""]
        ruta = os.path.join(dir_datos(), "gramatica_voz.xml")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(chr(10).join(partes))
        return ruta

    def _bucle(self):
        import comtypes
        comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
        try:
            import comtypes.client as cc
            _ISpeechRecoContextEvents = _interfaz_eventos_sapi(cc)

            motor = cc.CreateObject("SAPI.SpInprocRecognizer")
            entradas = motor.GetAudioInputs()
            if entradas.Count == 0:
                raise RuntimeError("no hay microfono disponible")
            motor.AudioInput = entradas.Item(0)

            ctx = motor.CreateRecoContext()
            gram = ctx.CreateGrammar(1)
            gram.DictationSetState(SGDS_INACTIVE)
            gram.CmdLoadFromFile(self._gramatica_xml(), 0)
            gram.CmdSetRuleState("mmats", SGDS_ACTIVE)

            duenno = self

            class _Eventos:
                def OnRecognition(self, _num, _pos, _tipo, resultado):
                    try:
                        texto = str(resultado.PhraseInfo.GetText()).strip().lower()
                    except Exception:
                        return
                    par = duenno._frases.get(texto)
                    if not par:
                        return
                    comando, aviso = par
                    if comando in ("silenciar", "volumen_pct"):
                        duenno._publicar("", aviso, texto)
                    elif comando in COMANDOS_EN_LA_HOME:
                        duenno._publicar(comando, aviso, texto)
                    elif duenno._ejecutar_local(comando):
                        duenno._publicar("", aviso, texto)
                    else:
                        duenno._publicar("", "Requiere el juego en primer plano", texto)

            conexion = cc.GetEvents(ctx, _Eventos(), interface=_ISpeechRecoContextEvents)
            motor.State = 1                 # SRSActive: el microfono empieza a leerse
            with self.lock:
                self.disponible = True
                self.motivo = ""
            log("[VOZ] Reconocedor es-ES activo (%d frases)." % len(self._frases))

            while not self._parar.is_set():
                cc.PumpEvents(0.2)

            try:
                motor.State = 0             # SRSInactive: suelta el microfono
                gram.CmdSetRuleState("mmats", SGDS_INACTIVE)
            except Exception:
                pass
            del conexion
            log("[VOZ] Reconocedor detenido.")
        except Exception as e:
            with self.lock:
                self.disponible = False
                self.motivo = "%s: %s" % (type(e).__name__, e)
                self.activo = False
            log("[VOZ] No se pudo iniciar el reconocedor: %s" % e)
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass


class Manejador(BaseHTTPRequestHandler):
    estado = None       # inyectado al crear el servidor
    voz = None          # ControlVoz, inyectado al crear el servidor
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass            # silenciar el log por peticion de BaseHTTPRequestHandler

    def _responder(self, payload, codigo=200):
        cuerpo = json.dumps(payload).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        # El overlay se sirve desde un esquema propio del mod: hace falta CORS.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_OPTIONS(self):
        self._responder({"ok": 1})

    def do_GET(self):
        ruta = self.path.split("?")[0]
        if ruta in ("/estado", "/salud", "/"):
            self._responder(self.estado.instantanea())
        elif ruta == "/voz":
            self._responder(self.voz.instantanea() if self.voz
                            else {"ok": 0, "disponible": 0, "motivo": "sin modulo"})
        else:
            self._responder({"ok": 0, "error": "ruta desconocida"}, 404)

    def do_POST(self):
        ruta = self.path.split("?")[0]
        if ruta == "/apagar":
            # Salida ordenada, para que el instalador no tenga que recurrir a
            # taskkill /F. Matar a la brava un proceso que tiene puesto un hook
            # de bajo nivel deja el hook huerfano hasta que Windows lo purga por
            # timeout, y ese es otro camino conocido a los tirones de entrada.
            self._responder({"ok": 1, "apagando": 1})
            log("Apagado solicitado por el instalador.")
            threading.Thread(target=self.estado.pedir_parada, daemon=True).start()
            return
        if ruta == "/voz":
            if not self.voz:
                self._responder({"ok": 0, "motivo": "sin modulo"}, 404)
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                datos = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            except (ValueError, OSError):
                self._responder({"ok": 0, "error": "json invalido"}, 400)
                return
            if datos.get("activo"):
                self.voz.encender()
            else:
                self.voz.apagar()
            self._responder(self.voz.instantanea())
            return
        if ruta != "/config":
            self._responder({"ok": 0, "error": "ruta desconocida"}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            datos = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except (ValueError, OSError):
            self._responder({"ok": 0, "error": "json invalido"}, 400)
            return

        # exterior_pct y fade_ms se siguen aceptando en el cuerpo -el overlay los
        # manda- pero se descartan: fuera de la camara 1 el audio esta silenciado
        # y no hay nivel intermedio que ofrecer. La respuesta los devuelve en 0,
        # que es lo que el panel pinta como "silenciado".
        with self.estado.lock:
            if "enabled" in datos:
                self.estado.cfg["enabled"] = bool(datos["enabled"])
            for clave in CONFIG_FIJA:
                self.estado.cfg[clave] = 0
            cfg = dict(self.estado.cfg)
        # Que activar/desactivar el audio inmersivo desde el overlay surta efecto
        # ya, sin esperar a la siguiente vuelta del hilo de audio.
        self.estado.senal_camara.set()
        guardar_config(cfg)
        log(f"Configuracion actualizada desde el overlay: {cfg}")
        self._responder(self.estado.instantanea())


def arrancar_servidor(estado):
    puerto = estado.cfg["port"]
    Manejador.estado = estado
    Manejador.voz = ControlVoz(estado)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    except OSError as e:
        log(f"No se pudo abrir el puerto {puerto}: {e}. "
            f"Probablemente ya hay otra copia del audio inmersivo en marcha.")
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="http").start()
    log(f"Servidor local escuchando en http://127.0.0.1:{puerto}")
    return srv


# ==============================================================================
# Instancia unica
# ==============================================================================

def tomar_mutex():
    """Un mutex con nombre evita dos demonios peleandose por el volumen."""
    h = kernel32.CreateMutexW(None, True, "Global\\MMATS_AUDIO_INMERSIVO")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return h


# ==============================================================================
# Diagnostico
# ==============================================================================

def diagnostico():
    print("=" * 78)
    print("MULTIMEDIA ATS SANTI - Diagnostico de Audio Inmersivo 3D")
    print("=" * 78)
    cfg = cargar_config()
    print(f"\nConfiguracion  : {RUTA_CONFIG}")
    print(f"  activo       : {cfg['enabled']}")
    print(f"  camara 1     : audio ACTIVADO ({GANANCIA_CABINA * 100:.0f}%)")
    print(f"  resto        : audio SILENCIADO ({GANANCIA_EXTERIOR * 100:.0f}%), corte inmediato")
    print(f"  puerto       : {cfg['port']}")

    perfil = perfil_mas_reciente()
    mapa, origen = leer_mapa_camaras(perfil)
    print(f"\nPerfil de ATS  : {nombre_legible_perfil(perfil)}")
    print(f"  ruta         : {perfil or '(no encontrado)'}")
    print(f"  origen mapa  : {origen}")
    fmt = lambda s: ", ".join(_nombre_vk(v) for v in sorted(s)) or "(ninguna)"
    print(f"  interior     : {fmt(mapa['interior'])}")
    print(f"  exterior     : {fmt(mapa['exterior'])}")
    print(f"  ciclo        : {fmt(mapa['ciclo'])}")

    pid = RastreadorJuego().refrescar()
    print(f"\nATS en marcha  : {'si (pid ' + str(pid) + ')' if pid else 'no'}")

    try:
        comtypes, AudioUtilities = _importar_audio()
        comtypes.CoInitialize()
        censo = censo_procesos()
        cache, total, nuestras = {}, 0, 0
        for s in AudioUtilities.GetAllSessions():
            spid = 0
            try:
                spid = s.ProcessId
            except Exception:
                pass
            if spid:
                total += 1
                if _es_webview_del_juego(spid, pid, censo, cache):
                    nuestras += 1
                    try:
                        v = s.SimpleAudioVolume.GetMasterVolume() * 100
                        cav = s.channelAudioVolume()
                        ch = [cav.GetChannelVolume(i) for i in range(cav.GetChannelCount())]
                        g = (sum(ch) / len(ch) * 100) if ch else 100.0
                        print(f"  WebView2 pid {spid}: maestro {v:.0f}% (del mod) "
                              f"x ganancia {g:.0f}% (nuestra) = {v * g / 100:.0f}%")
                    except Exception as e:
                        print(f"  WebView2 pid {spid}: ilegible ({e})")
        print(f"\nSesiones audio : {total} en total, {nuestras} del WebView2 de ATS")
        if nuestras == 0:
            print("  (abre Spotify o YouTube en la tablet del camion y repite)")
        comtypes.CoUninitialize()
    except Exception as e:
        print(f"\nERROR al enumerar audio: {e}")

    # -- Control por voz --------------------------------------------------------
    # Se comprueba aqui porque es la unica forma de saber si el .exe congelado
    # lleva dentro las interfaces COM generadas: son modulos .py que comtypes
    # normalmente crea al vuelo en site-packages, y dentro del .exe no puede.
    print("\nControl por voz:")
    try:
        import comtypes
        import comtypes.client as cc
        comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
        try:
            _interfaz_eventos_sapi(cc)
            print("  interfaces   : SpeechLib disponible")
            motor = cc.CreateObject("SAPI.SpInprocRecognizer")
            micros = motor.GetAudioInputs()
            print(f"  microfonos   : {micros.Count}")
            for i in range(micros.Count):
                print(f"     - {micros.Item(i).GetDescription()}")
            recos = motor.GetRecognizers()
            print(f"  reconocedores: {recos.Count}")
            for i in range(recos.Count):
                print(f"     - {recos.Item(i).GetDescription()}")
            if micros.Count and recos.Count:
                print("  estado       : LISTO (activalo desde la multimedia)")
            else:
                print("  estado       : falta microfono o reconocedor es-ES en Windows")
        finally:
            comtypes.CoUninitialize()
    except Exception as e:
        print(f"  estado       : NO DISPONIBLE -> {type(e).__name__}: {e}")

    print(f"\nLog            : {RUTA_LOG}")
    print("=" * 78)


def _nombre_vk(vk):
    for nombre, codigo in _VK_NOMBRES.items():
        if codigo == vk:
            return f"{nombre}(0x{vk:02X})"
    return f"0x{vk:02X}"


# ==============================================================================
# Principal
# ==============================================================================

def main():
    global _log_consola
    # El callback del hook de teclado necesita el GIL para ejecutarse. Con el
    # intervalo de fabrica (5 ms) puede esperar demasiado detras de otro hilo;
    # a 1 ms el interprete cede el turno cinco veces mas a menudo y la entrada
    # del sistema deja de depender de lo ocupado que este el hilo de audio.
    sys.setswitchinterval(0.001)
    ap = argparse.ArgumentParser(description="Audio inmersivo 3D por camara para MULTIMEDIA ATS SANTI")
    ap.add_argument("--diagnostico", action="store_true", help="imprime un informe del estado y sale")
    ap.add_argument("--consola", action="store_true", help="muestra el log por pantalla")
    args = ap.parse_args()

    if args.diagnostico:
        diagnostico()
        return 0

    _log_consola = args.consola

    if tomar_mutex() is None:
        log("Ya hay otra instancia del audio inmersivo en marcha. Saliendo.")
        return 1

    cfg = cargar_config()
    guardar_config(cfg)     # deja el json creado la primera vez
    estado = Estado(cfg)

    perfil = perfil_mas_reciente()
    mapa, origen = leer_mapa_camaras(perfil)
    with estado.lock:
        estado.mapa = mapa
        estado.origen_mapa = origen
        estado.perfil = nombre_legible_perfil(perfil)

    log("=" * 60)
    log(f"Audio Inmersivo 3D iniciado. Perfil '{estado.perfil}' ({origen}).")
    log("Audio exclusivo de la camara 1: en cabina suena, en cualquier otra "
        "camara queda en silencio total (corte inmediato, sin fundido).")

    if arrancar_servidor(estado) is None:
        return 1

    parar = threading.Event()
    rastreador = RastreadorJuego()
    # Cola acotada: si algo se atascara, se pierden las teclas mas viejas en vez
    # de crecer sin limite. El hook nunca puede quedarse esperando memoria.
    cola_teclas = deque(maxlen=256)
    aviso_teclas = threading.Event()
    hook = HookTeclado(cola_teclas, aviso_teclas)

    def parada_ordenada():
        parar.set()
        aviso_teclas.set()
        # El hilo de audio duerme en senal_camara, no en parar: hay que tocarle
        # el hombro por ahi o se quedaria esperando hasta el proximo barrido.
        estado.senal_camara.set()
        hook.terminar()

    estado.parada = parada_ordenada
    atexit.register(parada_ordenada)

    listo = threading.Event()
    hilo_hook = threading.Thread(target=hook.bucle, args=(listo,),
                                 daemon=True, name="teclado")
    hilo_hook.start()
    # No arrancar el resto hasta que el hilo del hook tenga cola de mensajes:
    # un PostThreadMessage anterior a eso se pierde sin avisar.
    listo.wait(5.0)

    threading.Thread(target=hilo_eventos,
                     args=(estado, rastreador, cola_teclas, aviso_teclas, parar),
                     daemon=True, name="eventos").start()

    hilo = threading.Thread(target=hilo_audio, args=(estado, parar, rastreador, hook),
                            daemon=False, name="audio")
    hilo.start()

    try:
        hilo.join()             # sin sondeo: se despierta cuando toca
    except KeyboardInterrupt:
        log("Interrumpido por el usuario.")
        parada_ordenada()
        hilo.join(3)
    rastreador.soltar()
    return 0


if __name__ == "__main__":
    sys.exit(main())

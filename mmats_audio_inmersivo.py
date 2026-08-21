# -*- coding: utf-8 -*-
"""
================================================================================
MULTIMEDIA ATS SANTI - Audio Inmersivo 3D por Camara
================================================================================
Baja el volumen de la multimedia (Spotify / YouTube / Twitch / Netflix, que
corren dentro de msedgewebview2.exe) cuando el jugador sale a una camara
exterior, y lo restaura al volver a la cabina.

  Camara 1 (cabina)      -> volumen pleno del usuario
  Camaras 2..8 / libre   -> ~12% (se oye lejano, "filtrado" desde dentro)

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
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = "MULTIMEDIA ATS SANTI"
PUERTO_DEFECTO = 48221
GAME_EXE = "amtrucks.exe"
WEBVIEW_EXE = "msedgewebview2.exe"

# Valores por defecto de la configuracion persistida.
CONFIG_DEFECTO = {
    "enabled": True,        # audio inmersivo activo
    "exterior_pct": 12,     # % del volumen del usuario al estar en camara exterior
    "fade_ms": 250,         # duracion del fundido entre estados
    "port": PUERTO_DEFECTO,
}


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


def log(msg):
    linea = time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg)
    with _log_lock:
        if _log_consola:
            print(linea, flush=True)
        try:
            # Rotacion simple: si supera 1 MB se empieza de cero.
            if os.path.exists(RUTA_LOG) and os.path.getsize(RUTA_LOG) > 1_048_576:
                os.replace(RUTA_LOG, RUTA_LOG + ".old")
            with open(RUTA_LOG, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
        except OSError:
            pass


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
    cfg["exterior_pct"] = max(0, min(100, int(cfg["exterior_pct"])))
    cfg["fade_ms"] = max(0, min(2000, int(cfg["fade_ms"])))
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
        self.interior = True        # se asume cabina al arrancar
        self.camara = 1             # ultima camara conocida (1..8, 0 = libre)
        self.juego_activo = False
        self.sesiones = 0
        self.base_pct = 100.0       # volumen "pleno" del usuario, 0-100
        self.mapa = dict(MAPA_DEFECTO)
        self.origen_mapa = "pendiente"
        self.perfil = "?"
        self.cambios = 0

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

# Orden con el que ATS recorre las camaras al pulsar la tecla de ciclo.
_ORDEN_CICLO = [1, 2, 3, 4, 5, 6, 7, 8]


def pid_en_primer_plano():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def hilo_teclado(estado, pid_juego_getter):
    """
    Hilo propio con su bomba de mensajes: un hook de bajo nivel exige que el hilo
    que lo instala procese mensajes, o Windows lo desactiva por timeout.
    """
    def on_key(nCode, wParam, lParam):
        # Nunca bloquear ni tardar: cualquier retraso aqui se nota en todo el sistema.
        try:
            if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                vk = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
                _procesar_tecla(estado, pid_juego_getter, vk)
        except Exception as e:  # jamas dejar escapar una excepcion al hook
            log(f"Error en el hook de teclado: {e}")
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    puntero = LowLevelKeyboardProc(on_key)
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, puntero, None, 0)
    if not hook:
        log(f"FALLO al instalar el hook de teclado (error {ctypes.get_last_error()})")
        return
    log("Hook de teclado instalado.")

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def _procesar_tecla(estado, pid_juego_getter, vk):
    pid_juego = pid_juego_getter()
    # Solo reaccionar si ATS tiene el foco: si no, el jugador esta escribiendo
    # en otra ventana y un "2" cualquiera no debe bajar la musica.
    if not pid_juego or pid_en_primer_plano() != pid_juego:
        return

    with estado.lock:
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
    log(f"Camara -> {nueva_cam} ({'INTERIOR' if interior else 'EXTERIOR'})")


def _camara_de_tecla(mapa, vk):
    """Traduce la tecla pulsada al numero de camara (para que el ciclo siga bien)."""
    if 0x31 <= vk <= 0x38:      # '1'..'8'
        return vk - 0x30
    if vk == 0x30:              # '0' = camara libre de desarrollador
        return 0
    return 2                    # binding personalizado: exterior generico


# ==============================================================================
# Control de volumen WASAPI sobre las sesiones del WebView2
# ==============================================================================

def _importar_audio():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    return comtypes, AudioUtilities


def _es_webview_del_juego(proc, pid_juego, cache):
    """
    Solo tocar los WebView2 que cuelgan de ATS. Asi no bajamos el volumen de un
    Edge o de otra app del usuario que tambien use msedgewebview2.exe.
    """
    if proc is None:
        return False
    if proc.pid in cache:
        return cache[proc.pid]
    resultado = False
    try:
        if proc.name().lower() == WEBVIEW_EXE:
            if pid_juego:
                for padre in proc.parents():
                    if padre.pid == pid_juego:
                        resultado = True
                        break
            else:
                resultado = True  # sin pid del juego, aceptar cualquiera
    except Exception:
        resultado = False
    cache[proc.pid] = resultado
    return resultado


class ControlAudio:
    """Mantiene los ISimpleAudioVolume de las sesiones del WebView2 del juego."""

    def __init__(self):
        self._volumenes = []
        self._ultimo_scan = 0.0

    def refrescar(self, pid_juego, forzar=False):
        ahora = time.monotonic()
        if not forzar and (ahora - self._ultimo_scan) < 2.0:
            return
        self._ultimo_scan = ahora
        _, AudioUtilities = _importar_audio()
        cache = {}
        encontrados = []
        try:
            for s in AudioUtilities.GetAllSessions():
                if _es_webview_del_juego(s.Process, pid_juego, cache):
                    try:
                        encontrados.append(s.SimpleAudioVolume)
                    except Exception:
                        pass
        except Exception as e:
            log(f"No se pudieron enumerar las sesiones de audio: {e}")
            return
        self._volumenes = encontrados

    @property
    def n_sesiones(self):
        return len(self._volumenes)

    def leer(self):
        """Volumen actual en 0-100, o None si no hay sesiones legibles."""
        for v in list(self._volumenes):
            try:
                return v.GetMasterVolume() * 100.0
            except Exception:
                self._volumenes.remove(v)
        return None

    def escribir(self, pct):
        nivel = max(0.0, min(1.0, pct / 100.0))
        for v in list(self._volumenes):
            try:
                v.SetMasterVolume(nivel, None)
            except Exception:
                try:
                    self._volumenes.remove(v)
                except ValueError:
                    pass


def buscar_pid_juego():
    import psutil
    for p in psutil.process_iter(["name", "pid"]):
        try:
            if (p.info["name"] or "").lower() == GAME_EXE:
                return p.info["pid"]
        except Exception:
            continue
    return 0


def hilo_audio(estado, parar, pid_box):
    comtypes, _ = _importar_audio()
    comtypes.CoInitialize()
    control = ControlAudio()
    objetivo_actual = None      # % que estamos aplicando ahora mismo
    ultimo_interior = True
    fade_desde = fade_hasta = 0.0
    fade_t0 = 0.0
    fade_dur = 0.0
    aviso_sin_sesion = 0.0

    try:
        while not parar.is_set():
            pid = buscar_pid_juego()
            pid_box[0] = pid

            if not pid:
                # Sin juego: soltar el control y dormir barato.
                if objetivo_actual is not None:
                    with estado.lock:
                        base = estado.base_pct
                    control.refrescar(0, forzar=True)
                    control.escribir(base)
                    log(f"ATS cerrado: volumen restaurado a {base:.0f}%.")
                    objetivo_actual = None
                    control._volumenes = []
                with estado.lock:
                    estado.juego_activo = False
                    estado.sesiones = 0
                parar.wait(2.0)
                continue

            with estado.lock:
                estado.juego_activo = True
                cfg = dict(estado.cfg)
                interior = estado.interior
                base = estado.base_pct

            control.refrescar(pid)
            with estado.lock:
                estado.sesiones = control.n_sesiones

            if control.n_sesiones == 0:
                ahora = time.monotonic()
                if ahora - aviso_sin_sesion > 60:
                    aviso_sin_sesion = ahora
                    log("Aun sin sesiones de audio del WebView2 (abre Spotify/YouTube en la tablet).")
                objetivo_actual = None
                parar.wait(1.0)
                continue

            observado = control.leer()

            if not cfg["enabled"]:
                # Funcion apagada: devolver el mando al mod y no tocar nada.
                if objetivo_actual is not None:
                    control.escribir(base)
                    objetivo_actual = None
                parar.wait(0.4)
                continue

            destino = base if interior else base * cfg["exterior_pct"] / 100.0

            # Cambio de camara -> arrancar un fundido en vez de un corte seco.
            if interior != ultimo_interior:
                ultimo_interior = interior
                fade_desde = observado if observado is not None else (objetivo_actual or base)
                fade_hasta = destino
                fade_dur = cfg["fade_ms"] / 1000.0
                fade_t0 = time.monotonic()

            if fade_dur > 0 and (time.monotonic() - fade_t0) < fade_dur:
                # Curva suave (ease-in-out) para que el cambio no se note escalonado.
                t = (time.monotonic() - fade_t0) / fade_dur
                suave = t * t * (3 - 2 * t)
                objetivo = fade_desde + (fade_hasta - fade_desde) * suave
                control.escribir(objetivo)
                objetivo_actual = objetivo
                parar.wait(0.016)
                continue

            if interior:
                # En cabina el mando es del usuario: si alguien movio el volumen
                # (slider del overlay, Ctrl +/-, watchdog del mod), lo adoptamos
                # como nuevo volumen base en lugar de sobrescribirlo.
                if observado is not None and abs(observado - base) > 1.5:
                    with estado.lock:
                        estado.base_pct = observado
                    log(f"Volumen base actualizado por el usuario: {observado:.0f}%.")
                    objetivo_actual = observado
                elif objetivo_actual is None:
                    control.escribir(base)
                    objetivo_actual = base
            else:
                # En exterior mandamos nosotros y REAFIRMAMOS: asi ganamos siempre
                # al watchdog de audio de dxgi.dll, que reaplica mm_audio_volume.
                if observado is None or abs(observado - destino) > 1.0:
                    control.escribir(destino)
                objetivo_actual = destino

            parar.wait(0.10 if not interior else 0.25)
    finally:
        # Pase lo que pase, nunca dejar al usuario con la musica al 12%.
        try:
            with estado.lock:
                base = estado.base_pct
            control.refrescar(pid_box[0], forzar=True)
            control.escribir(base)
            log(f"Cerrando: volumen restaurado a {base:.0f}%.")
        except Exception:
            pass
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


# ==============================================================================
# Servidor local: lo consume el overlay del mod (lucidgfx_overlay.html)
# ==============================================================================

class Manejador(BaseHTTPRequestHandler):
    estado = None       # inyectado al crear el servidor
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
        else:
            self._responder({"ok": 0, "error": "ruta desconocida"}, 404)

    def do_POST(self):
        if self.path.split("?")[0] != "/config":
            self._responder({"ok": 0, "error": "ruta desconocida"}, 404)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            datos = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except (ValueError, OSError):
            self._responder({"ok": 0, "error": "json invalido"}, 400)
            return

        with self.estado.lock:
            if "enabled" in datos:
                self.estado.cfg["enabled"] = bool(datos["enabled"])
            if "exterior_pct" in datos:
                try:
                    self.estado.cfg["exterior_pct"] = max(0, min(100, int(datos["exterior_pct"])))
                except (TypeError, ValueError):
                    pass
            if "fade_ms" in datos:
                try:
                    self.estado.cfg["fade_ms"] = max(0, min(2000, int(datos["fade_ms"])))
                except (TypeError, ValueError):
                    pass
            cfg = dict(self.estado.cfg)
        guardar_config(cfg)
        log(f"Configuracion actualizada desde el overlay: {cfg}")
        self._responder(self.estado.instantanea())


def arrancar_servidor(estado):
    puerto = estado.cfg["port"]
    Manejador.estado = estado
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
    print(f"  exterior     : {cfg['exterior_pct']}%")
    print(f"  fundido      : {cfg['fade_ms']} ms")
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

    pid = buscar_pid_juego()
    print(f"\nATS en marcha  : {'si (pid ' + str(pid) + ')' if pid else 'no'}")

    try:
        comtypes, AudioUtilities = _importar_audio()
        comtypes.CoInitialize()
        cache, total, nuestras = {}, 0, 0
        for s in AudioUtilities.GetAllSessions():
            if s.Process:
                total += 1
                if _es_webview_del_juego(s.Process, pid, cache):
                    nuestras += 1
                    try:
                        v = s.SimpleAudioVolume.GetMasterVolume() * 100
                        print(f"  WebView2 pid {s.Process.pid}: volumen {v:.0f}%")
                    except Exception as e:
                        print(f"  WebView2 pid {s.Process.pid}: ilegible ({e})")
        print(f"\nSesiones audio : {total} en total, {nuestras} del WebView2 de ATS")
        if nuestras == 0:
            print("  (abre Spotify o YouTube en la tablet del camion y repite)")
        comtypes.CoUninitialize()
    except Exception as e:
        print(f"\nERROR al enumerar audio: {e}")

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
    log(f"Exterior al {cfg['exterior_pct']}%, fundido {cfg['fade_ms']} ms.")

    if arrancar_servidor(estado) is None:
        return 1

    parar = threading.Event()
    pid_box = [0]
    atexit.register(parar.set)

    threading.Thread(target=hilo_teclado, args=(estado, lambda: pid_box[0]),
                     daemon=True, name="teclado").start()
    hilo = threading.Thread(target=hilo_audio, args=(estado, parar, pid_box),
                            daemon=False, name="audio")
    hilo.start()

    try:
        while hilo.is_alive():
            hilo.join(0.5)
    except KeyboardInterrupt:
        log("Interrumpido por el usuario.")
        parar.set()
        hilo.join(3)
    return 0


if __name__ == "__main__":
    sys.exit(main())

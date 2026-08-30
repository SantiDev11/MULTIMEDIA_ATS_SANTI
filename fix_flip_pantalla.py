#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_flip_pantalla.py - Corrige la orientacion (imagen al reves) de las pantallas
multimedia de MULTIMEDIA ATS SANTI (dxgi.dll).

El dxgi.dll trae una tabla interna que, para cada preset de pantalla, guarda dos
banderas: si hay que invertir verticalmente la textura (V-flip) al pintarla sobre
el mesh de la pantalla del camion. De fabrica solo el preset "Multimidia Compacta
/ Scania (mod)" viene con el flip ACTIVADO; si el mod de Scania que usas ya trae
las UV corregidas, esa compensacion es justamente la que hace que la imagen
salga al reves.

Uso:
    python fix_flip_pantalla.py --listar
    python fix_flip_pantalla.py --preset scania --flip off
    python fix_flip_pantalla.py --preset scania --flip off --dll RUTA\\dxgi.dll
    python fix_flip_pantalla.py --restaurar
"""

import argparse
import os
import shutil
import struct
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Tabla de presets de pantalla.
#
# offset : offset EN EL ARCHIVO de la instruccion que inicializa las 2 banderas
#          dentro del constructor estatico del mapa  rtHash -> {flip, flip_split}
# disp8  : desplazamiento respecto a rbp que usa esa instruccion
# ---------------------------------------------------------------------------
PRESETS = {
    "scania": {
        "titulo": "Multimidia Compacta / Scania (mod)",
        "rt_hash": 0xE2A0D7B1DF649166,
        "offset": 0x7A4,
        "disp8": 0xFB,
    },
    "central": {
        "titulo": "Multimidia Central / Volvo FH5-FH6, Scania",
        "rt_hash": 0x6E445921D4FBB174,
        "offset": 0x7D5,
        "disp8": 0x13,
    },
    "vidrio": {
        "titulo": "GPS Vidro / Generico",
        "rt_hash": 0x5891A3883361780B,
        "offset": 0x804,
        "disp8": 0x2B,
    },
    "celular": {
        "titulo": "GPS Celular / Generico",
        "rt_hash": 0xF778E70824018E0B,
        "offset": 0x833,
        "disp8": 0x43,
    },
}

# "movzx eax, word ptr [rbp-0x1b]" -> copia bytes de relleno, se puede sobrescribir
PADDING_COPY = bytes((0x0F, 0xB7, 0x45, 0xE5))
NOP2 = bytes((0x66, 0x90))

RUTAS_JUEGO = [
    "C:\\Program Files (x86)\\Steam\\steamapps\\common\\American Truck Simulator\\bin\\win_x64\\dxgi.dll",
    "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Euro Truck Simulator 2\\bin\\win_x64\\dxgi.dll",
]


def _forma_imm(disp8, flip, flip_split):
    """mov word ptr [rbp+disp8], imm16"""
    return bytes((0x66, 0xC7, 0x45, disp8, 1 if flip else 0, 1 if flip_split else 0))


def _forma_cero(disp8):
    """mov word ptr [rbp+disp8], bx   (bx vale 0 en ese punto)"""
    return bytes((0x66, 0x89, 0x5D, disp8))


def leer_estado(data, preset):
    """Devuelve (flip, flip_split) o None si el patron no se reconoce."""
    off, disp8 = preset["offset"], preset["disp8"]
    trozo = data[off:off + 6]
    if trozo[:4] == _forma_cero(disp8):
        return (0, 0)
    if trozo[:4] == bytes((0x66, 0xC7, 0x45, disp8)):
        return (trozo[4], trozo[5])
    return None


def aplicar(data, preset, flip, flip_split):
    off, disp8 = preset["offset"], preset["disp8"]
    nuevo = bytearray(data)
    if data[off:off + 4] == _forma_cero(disp8):
        # 4 bytes de la instruccion + 4 de la copia de relleno = 8 bytes de sitio
        if data[off + 4:off + 8] != PADDING_COPY:
            raise RuntimeError(
                "Patron inesperado en 0x%X; ese dxgi.dll no coincide con esta version." % off)
        nuevo[off:off + 8] = _forma_imm(disp8, flip, flip_split) + NOP2
    elif data[off:off + 4] == bytes((0x66, 0xC7, 0x45, disp8)):
        nuevo[off + 4] = 1 if flip else 0
        nuevo[off + 5] = 1 if flip_split else 0
    else:
        raise RuntimeError(
            "Patron inesperado en 0x%X; ese dxgi.dll no coincide con esta version." % off)
    return bytes(nuevo)


def verificar_dll(ruta):
    with open(ruta, "rb") as f:
        data = f.read()
    if data[:2] != b"MZ":
        raise RuntimeError("%s no es un PE valido." % ruta)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise RuntimeError("%s no es un PE valido." % ruta)
    for clave, preset in PRESETS.items():
        if leer_estado(data, preset) is None:
            raise RuntimeError(
                "El preset '%s' no se reconoce en %s.\n"
                "Este script es para el dxgi.dll de MULTIMEDIA ATS SANTI v2.0 "
                "(build Jul 22 2026)." % (clave, ruta))
    return data


def listar(rutas):
    for ruta in rutas:
        print("\n=== %s ===" % ruta)
        data = verificar_dll(ruta)
        for clave, preset in PRESETS.items():
            flip, split = leer_estado(data, preset)
            print("  %-9s %-44s RT=%016X  flip=%-3s flip_split=%s"
                  % (clave, preset["titulo"], preset["rt_hash"],
                     "SI" if flip else "no", "SI" if split else "no"))


def respaldar(ruta):
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = "%s.flipbak_%s" % (ruta, marca)
    shutil.copy2(ruta, destino)
    return destino


def restaurar(ruta):
    carpeta = os.path.dirname(os.path.abspath(ruta)) or "."
    base = os.path.basename(ruta) + ".flipbak_"
    copias = sorted(n for n in os.listdir(carpeta) if n.startswith(base))
    if not copias:
        print("  sin copias de seguridad para %s" % ruta)
        return False
    origen = os.path.join(carpeta, copias[-1])
    shutil.copy2(origen, ruta)
    print("  restaurado desde %s" % copias[-1])
    return True


def rutas_objetivo(args):
    if args.dll:
        return [args.dll]
    rutas = []
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dxgi.dll")
    if os.path.isfile(local):
        rutas.append(local)
    for r in RUTAS_JUEGO:
        if os.path.isfile(r):
            rutas.append(r)
    return rutas


def main():
    ap = argparse.ArgumentParser(
        description="Corrige la imagen al reves en las pantallas de MULTIMEDIA ATS SANTI.")
    ap.add_argument("--listar", action="store_true",
                    help="muestra el estado actual de cada preset")
    ap.add_argument("--preset", choices=sorted(PRESETS),
                    help="preset de pantalla a modificar")
    ap.add_argument("--flip", choices=("on", "off"),
                    help="activar o desactivar la inversion vertical")
    ap.add_argument("--dll",
                    help="ruta concreta a un dxgi.dll (por defecto: el del proyecto y el del juego)")
    ap.add_argument("--restaurar", action="store_true",
                    help="deshace el ultimo cambio desde la copia .flipbak_*")
    args = ap.parse_args()

    rutas = rutas_objetivo(args)
    if not rutas:
        print("No se encontro ningun dxgi.dll. Usa --dll RUTA.")
        return 1

    if args.restaurar:
        for r in rutas:
            print("Restaurando %s" % r)
            restaurar(r)
        return 0

    if args.listar or not args.preset:
        listar(rutas)
        if not args.preset:
            print("\nEjemplo:  python fix_flip_pantalla.py --preset scania --flip off")
        return 0

    if not args.flip:
        print("Falta --flip on|off")
        return 1

    preset = PRESETS[args.preset]
    valor = 1 if args.flip == "on" else 0

    for ruta in rutas:
        print("\n=== %s ===" % ruta)
        data = verificar_dll(ruta)
        antes = leer_estado(data, preset)
        if antes == (valor, valor):
            print("  ya estaba en flip=%s, no se toca." % args.flip)
            continue
        copia = respaldar(ruta)
        nuevo = aplicar(data, preset, valor, valor)
        with open(ruta, "wb") as f:
            f.write(nuevo)
        print("  copia de seguridad: %s" % os.path.basename(copia))
        print("  %s: flip %s -> %s" % (preset["titulo"], antes, (valor, valor)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

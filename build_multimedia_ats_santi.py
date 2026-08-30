# -*- coding: utf-8 -*-
"""
================================================================================
MULTIMEDIA ATS SANTI - Official Master Build Script
================================================================================
1. Dual-Key XOR encryption e inyección de los 5 módulos HTML en .rdata.
2. Desbloqueos de Renderizado D3D11 y Navegación con Mouse.
3. Tecla Oficial de Navegación F8 (VK_F8 = 0x77 = 119).
4. Activación permanente de Licencia Universal Offline (MMATS-SANTI-2026-UNIVERSAL).
5. Roadworks Cursor: sustituye el HLSL del cursor F8 (bolinha) por la flecha con
   franjas de obra, con la punta como hotspot exacto.
6. Aviso "MOUSE ACTIVO" del modo interactivo (F8): textos en español, arreglo
   de las longitudes que el compilador dejó fijas para el prefijo y el sufijo,
   y repintado con la paleta azul de la multimedia.
7. Orientación de las pantallas: fija las banderas de V-flip de cada preset
   (la pantalla del mod de Scania lo lleva ACTIVADO) para que no se pierdan
   en cada recompilación.
================================================================================
"""
import pefile
import struct
import gc
import os
import shutil

print("=" * 80)
print("COMPILANDO MULTIMEDIA ATS SANTI")
print("=" * 80)

with open('BACKUP_MULTIMEDIAATS_SEGURIDAD/dxgi.dll', 'rb') as f:
    dll = bytearray(f.read())

pe = pefile.PE(data=bytes(dll))
image_base = pe.OPTIONAL_HEADER.ImageBase

def va_to_offset(va):
    return pe.get_offset_from_rva(va - image_base)

def encrypt_dual_key_xor(plain_data, key1, key2):
    klen1 = len(key1)
    klen2 = len(key2)
    encrypted = bytearray(len(plain_data))
    for i in range(len(plain_data)):
        b = plain_data[i]
        b ^= key1[i % klen1]
        b ^= key2[i % klen2]
        encrypted[i] = b
    return bytes(encrypted)

# ------------------------------------------------------------------------------
# 1. Inyección de recursos HTML con Dual-Key XOR
# ------------------------------------------------------------------------------
table_off = va_to_offset(0x180190E40)
files_map = [
    ("lucidgfx_home.html", "MENU_EXTRAIDO/lucidgfx_home.html"),
    ("lucidgfx_overlay.html", "MENU_EXTRAIDO/lucidgfx_overlay.html"),
    ("chat.html", "MENU_EXTRAIDO/chat.html"),
    ("split.html", "MENU_EXTRAIDO/split.html"),
    ("lucidgfx_gps.html", "MENU_EXTRAIDO/lucidgfx_gps.html")
]

# Cada recurso vive en un hueco fijo de .rdata, uno detras de otro. Si un HTML
# crece mas que su hueco, la escritura pisaria el recurso siguiente y el mod
# arrancaria con una pantalla en blanco sin ningun error visible. Calculamos el
# limite real de cada bloque (inicio del siguiente, o fin de seccion para el
# ultimo) y abortamos antes de tocar nada.
#
# Entre medias tambien viven las dos claves XOR de cada recurso, asi que cuentan
# como frontera: el hueco de lucidgfx_home.html, por ejemplo, termina en su
# propia clave, no en el bloque de datos siguiente.
_bloques = []
_fronteras = []
for i, (res_name, file_path) in enumerate(files_map):
    e = table_off + i * 48
    dva = int.from_bytes(dll[e+8 : e+16], 'little')
    off_b = va_to_offset(dva)
    _bloques.append((off_b, res_name, file_path))
    _fronteras.append(off_b)
    for campo in (24, 32):  # key1_va, key2_va
        _fronteras.append(va_to_offset(int.from_bytes(dll[e+campo : e+campo+8], 'little')))
_bloques.sort()
_fronteras.sort()

_sec = next(s for s in pe.sections
            if s.PointerToRawData <= _bloques[-1][0] < s.PointerToRawData + s.SizeOfRawData)
_fin_sec = _sec.PointerToRawData + _sec.SizeOfRawData

_desbordes = []
for j, (off_b, res_name, file_path) in enumerate(_bloques):
    siguientes = [f for f in _fronteras if f > off_b]
    tope = siguientes[0] if siguientes else _fin_sec
    hueco = tope - off_b
    with open(file_path, 'r', encoding='utf-8') as f:
        nuevo = len(f.read().encode('utf-8'))
    if nuevo > hueco:
        _desbordes.append(f"   - {res_name}: {nuevo} bytes, solo caben {hueco} "
                          f"(sobran {nuevo - hueco})")
    else:
        print(f" [CAP] {res_name}: {nuevo}/{hueco} bytes ({hueco - nuevo} libres)")

if _desbordes:
    print("\n" + "!" * 80)
    print("ABORTADO: uno o mas recursos no caben en su hueco de .rdata.")
    print("Reduce el tamano del HTML (minifica CSS/JS) o mueve la tabla de recursos.")
    print("\n".join(_desbordes))
    print("!" * 80)
    raise SystemExit(1)

print("-" * 80)

for i, (res_name, file_path) in enumerate(files_map):
    entry_off = table_off + i * 48
    data_va = int.from_bytes(dll[entry_off+8 : entry_off+16], 'little')
    key1_va = int.from_bytes(dll[entry_off+24 : entry_off+32], 'little')
    key2_va = int.from_bytes(dll[entry_off+32 : entry_off+40], 'little')
    key_len = int.from_bytes(dll[entry_off+40 : entry_off+48], 'little')

    data_off = va_to_offset(data_va)
    k1_off = va_to_offset(key1_va)
    k2_off = va_to_offset(key2_va)

    k1 = dll[k1_off : k1_off + key_len]
    k2 = dll[k2_off : k2_off + key_len]

    with open(file_path, 'r', encoding='utf-8') as f:
        new_content = f.read()

    new_bytes = new_content.encode('utf-8')
    enc_bytes = encrypt_dual_key_xor(new_bytes, k1, k2)
    dll[data_off : data_off + len(new_bytes)] = enc_bytes
    dll[entry_off+16 : entry_off+24] = struct.pack('<Q', len(new_bytes))
    print(f" [OK] Recurso inyectado: {res_name} ({len(new_bytes)} bytes)")

# ------------------------------------------------------------------------------
# 2. Desbloqueos de Renderizado y Navegación con Mouse
# ------------------------------------------------------------------------------
off2 = va_to_offset(0x1800c1bd5)
dll[off2 : off2 + 6] = b'\x90' * 6

off3 = va_to_offset(0x1800c212d)
dll[off3 : off3 + 8] = bytes([0x41, 0xB9, 0x01, 0x00, 0x00, 0x00, 0x90, 0x90])

off_feat = va_to_offset(0x1800ce420)
dll[off_feat : off_feat + 3] = bytes([0xB0, 0x01, 0xC3])

off_cancel = va_to_offset(0x1800cb24e)
dll[off_cancel + 4 : off_cancel + 9] = bytes([0xBA, 0x00, 0x00, 0x00, 0x00])
off_call = va_to_offset(0x1800cb25a)
dll[off_call : off_call + 2] = bytes([0x90, 0x90])

lic_off = va_to_offset(0x1801f9290)
dll[lic_off + 0x80] = 1
dll[lic_off + 0x81] = 1
dll[lic_off + 0x31c] = 1

# ------------------------------------------------------------------------------
# 3. Tecla Oficial de Navegación F8 (VK_F8 = 0x77 = 119)
# ------------------------------------------------------------------------------
key_off = va_to_offset(0x1801f9000)
dll[key_off] = 0x77 # VK_F8
print(" [OK] Tecla F8 configurada para activacion/desactivacion del mouse (Toggle ON/OFF)")

# ------------------------------------------------------------------------------
# 4. Roadworks Cursor
# ------------------------------------------------------------------------------
# El cursor del modo interactivo (F8) no es un bitmap ni un HCURSOR de Windows:
# es un pixel shader que dxgi.dll compila EN CALIENTE con D3DCompile sobre un
# triangulo a pantalla completa, descartando con clip() todo lo que quede fuera
# de la figura. El HLSL viaja como texto plano en .rdata y su puntero esta en la
# tabla de shaders de .data SIN campo de longitud (se pasa como cadena C), asi
# que se puede sustituir por otro de distinto tamano mientras quepa en el hueco.
#
# De fabrica dibuja una bolinha centrada en el punto de interaccion. La flecha
# nueva tiene la PUNTA en (0,0) del espacio del cursor, que es exactamente la
# coordenada que el mod usa para el clic: el hotspot deja de ser ambiguo.
#
# Se mantienen el cbuffer, el color configurable (mouse_color del overlay) y el
# clip(), asi que no cambia nada del lado C++.
NUL = bytes(1)
_marca = b'cbuffer CursorCB'
_i = dll.find(_marca)
if _i < 0:
    raise SystemExit(' [ERROR] No se encontro el shader del cursor en la DLL base.')
_ini_sh = dll.rfind(NUL, 0, _i) + 1
_hueco_sh = dll.find(NUL, _i)
while dll[_hueco_sh] == 0:           # el relleno de alineacion tambien es sitio
    _hueco_sh += 1
_cupo_sh = _hueco_sh - _ini_sh - 1   # -1: hay que dejar el terminador

with open('roadworks_cursor.hlsl', 'r', encoding='utf-8', newline='') as f:
    _hlsl = f.read().replace('\r\n', '\n').encode('utf-8')

if len(_hlsl) > _cupo_sh:
    raise SystemExit(f' [ERROR] roadworks_cursor.hlsl ocupa {len(_hlsl)} bytes y solo '
                     f'caben {_cupo_sh}. Acorta el shader.')
dll[_ini_sh:_hueco_sh] = _hlsl + NUL * (_hueco_sh - _ini_sh - len(_hlsl))
print(f' [OK] Roadworks Cursor inyectado ({len(_hlsl)}/{_cupo_sh} bytes, '
      f'{_cupo_sh - len(_hlsl)} libres)')

# ------------------------------------------------------------------------------
# 5. Aviso "MOUSE ACTIVO" del modo interactivo (F8)
# ------------------------------------------------------------------------------
# El badge que dxgi.dll dibuja en el backbuffer mientras el F8 tiene el raton
# cogido se arma en tiempo de ejecucion como prefijo + nombre de la tecla +
# sufijo, y el compilador dejo las LONGITUDES de esos dos literales metidas a
# pelo en el codigo (copia inline de 7 bytes para el prefijo, 0x14 = 20 para el
# sufijo, medidas del portugues "Aperte " / " para voltar ao jogo").
#
# El binario base ya traia los textos traducidos a mano, pero sin tocar esas
# longitudes, asi que el aviso salia roto: el prefijo "Pulsa " (6 bytes) se
# copiaba con 7, metiendo el NUL de mas EN MEDIO de la cadena -> el render
# paraba en "Pulsa" y del sufijo de 21 bytes solo se pegaban 20.
#
# Aqui se reescriben los tres literales en espanol y se ajustan las longitudes
# del codigo para que cuadren. No se toca la maquina de estados del F8: el
# toggle (SetInteractMode en 0x180017950) ya ignora la llamada si el valor no
# cambia, y los dos puntos que lo invocan hacen `sete cl` sobre interactMode,
# asi que F8 sigue siendo un interruptor con antirrebote propio.
PREFIJO = b'Pulsa '            # copiado inline: 4 bytes + 2 bytes, sin NUL
SUFIJO  = b' para volver al juego'
TITULO  = b'MOUSE ACTIVO'
LOG_HINT = b"[MOUSE-HINT] aviso 'MOUSE ACTIVO' dibujado en el backbuffer (tecla={} vk={})"

def escribir_cadena(va, texto, etiqueta):
    """Sustituye la cadena C que empieza en `va` respetando su hueco."""
    ini = va_to_offset(va)
    fin = dll.index(b'\x00', ini)
    while dll[fin] == 0:            # el relleno de alineacion tambien es sitio
        fin += 1
    cupo = fin - ini - 1            # -1: hay que dejar el terminador
    if len(texto) > cupo:
        raise SystemExit(f' [ERROR] "{etiqueta}" ocupa {len(texto)} bytes y solo '
                         f'caben {cupo} en .rdata.')
    dll[ini:fin] = texto + bytes(fin - ini - len(texto))
    return cupo

def parchear(va, esperado, nuevo, etiqueta):
    """Escribe `nuevo` en `va` solo si alli sigue estando `esperado`."""
    off = va_to_offset(va)
    if bytes(dll[off:off + len(esperado)]) != esperado:
        raise SystemExit(f' [ERROR] {etiqueta} en {va:#x}: la DLL base no trae el '
                         f'patron esperado {esperado.hex()}.')
    dll[off:off + len(nuevo)] = nuevo

if len(PREFIJO) != 6:
    raise SystemExit(' [ERROR] El prefijo del aviso tiene que medir 6 bytes.')
if len(SUFIJO) > 0xFF:
    raise SystemExit(' [ERROR] El sufijo del aviso no cabe en un imm8.')

escribir_cadena(0x180144128, PREFIJO, 'prefijo del aviso')
escribir_cadena(0x180144110, SUFIJO, 'sufijo del aviso')
escribir_cadena(0x180144130, TITULO, 'titulo del aviso')
escribir_cadena(0x1801440c0, LOG_HINT, 'log del aviso')

# Longitud del format string del log (fmt::string_view, imm32).
parchear(0x18003b06b,
         bytes.fromhex('48c744246849000000'),
         b'\x48\xc7\x44\x24\x68' + struct.pack('<I', len(LOG_HINT)),
         'longitud del log del aviso')

# Prefijo: reserva y copia inline de 7 -> 6 bytes.
parchear(0x18003b201, bytes.fromhex('498d7707'), bytes.fromhex('498d7706'),
         'reserva prefijo+tecla')           # lea rsi, [r15 + 6]
parchear(0x18003b25c, bytes.fromhex('0fb605cb8e1000884706'),
         bytes.fromhex('662e0f1f840000000000'),
         'copia del 7o byte del prefijo')   # nop de 10 bytes
parchear(0x18003b266, bytes.fromhex('488d4f07'), bytes.fromhex('488d4f06'),
         'destino del nombre de la tecla')  # lea rcx, [rdi + 6]

# Sufijo: las seis longitudes 0x14 (20) del append -> len(SUFIJO).
_n = len(SUFIJO)
for _va, _hex_ini, _hex_fin, _etq in [
    (0x18003b287, '4883f814',          '4883f8',          'hueco libre para el sufijo'),
    (0x18003b28d, '488d4114',          '488d41',          'avance del cursor de escritura'),
    (0x18003b2a5, '41b814000000',      '41b8',            'bytes a copiar del sufijo'),
    (0x18003b2ba, 'c6431400',          'c643',            'terminador tras el sufijo'),
    (0x18003b2c4, '48c744242014000000', '48c7442420',     'longitud en la ruta lenta'),
    (0x18003b2da, 'ba14000000',        'ba',              'longitud del append'),
]:
    _ini = bytes.fromhex(_hex_ini)
    _pre = bytes.fromhex(_hex_fin)
    if _hex_ini in ('4883f814', '488d4114', 'c6431400'):
        _nuevo = _pre + bytes([_n]) + _ini[len(_pre) + 1:]
    else:
        _nuevo = _pre + struct.pack('<I', _n) + _ini[len(_pre) + 4:]
    parchear(_va, _ini, _nuevo, _etq)

# Descripciones del .ini que hablan del modo raton (se escriben en el config).
escribir_cadena(0x180145b60, b'Activa el modo raton en la multimedia (119 = F8)',
                'descripcion hotkey_interact')
escribir_cadena(0x180145dc8, b'Velocidad del cursor multimedia en % (100=1.0x; 30..200)',
                'descripcion mouse_sensitivity')
escribir_cadena(0x180145e08, b'Color del cursor F8 (hex #RRGGBB)',
                'descripcion mouse_color')
escribir_cadena(0x180145f60,
                b"Muestra el aviso 'MOUSE ACTIVO' mientras el F8 tiene el raton "
                b'en la multimedia (1=si 0=no)',
                'descripcion mm_mouse_active_hint')

# --- Paleta: los mismos azules que la multimedia -------------------------------
# El aviso venia con el morado de LucidGFX (fondo 0.55/0.30/1.00). La multimedia
# es celeste #38bdf8 sobre paneles azul noche #0b1120, asi que se repinta con esa
# misma paleta, sin tocar las animaciones de alfa ni el latido del titulo.
#
# Fondo y borde llevan el RGB como inmediatos dentro del propio codigo: se
# reescriben en el sitio. El titulo lo calcula latiendo (canal = base + pulso *
# amplitud) leyendo floats del pool compartido de .rdata; esos floats los usan
# decenas de funciones mas, asi que NO se cambian sus valores: lo que se cambia
# es a QUE float apunta cada lectura, escogiendo entre los que ya existen los
# que dan el celeste. La ImVec4 de la segunda linea si es exclusiva del aviso
# (una sola referencia en toda la DLL), asi que esa se reescribe entera.
AZUL_PANEL   = '#0b1120'   # fondo de los paneles de la multimedia
AZUL_ACENTO  = '#38bdf8'   # celeste de la multimedia
AZUL_SUAVE   = '#bae6fd'   # texto secundario de la multimedia

def rgb(color):
    h = color.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def f32(x):
    return struct.pack('<f', x)

def color_inmediato(va, destino, antes, ahora, etiqueta):
    """Reescribe el imm32 de un `mov dword ptr [rsp+destino], <float>`."""
    pre = bytes([0xC7, 0x44, 0x24, destino])
    parchear(va, pre + f32(antes), pre + f32(ahora), etiqueta)

def repuntar(va, largo, destino_antes, destino_ahora, etiqueta):
    """Cambia el objetivo de una lectura rip-relativa sin mover la instruccion."""
    off = va_to_offset(va)
    esperado = struct.pack('<i', destino_antes - (va + largo))
    if bytes(dll[off + largo - 4 : off + largo]) != esperado:
        raise SystemExit(f' [ERROR] {etiqueta} en {va:#x}: no apunta a '
                         f'{destino_antes:#x} como se esperaba.')
    dll[off + largo - 4 : off + largo] = struct.pack('<i', destino_ahora - (va + largo))

_pr, _pg, _pb = rgb(AZUL_PANEL)
_ar, _ag, _ab = rgb(AZUL_ACENTO)

# Fondo del aviso (ImDrawList::AddRectFilled). El alfa sigue latiendo 0.45..1.0.
color_inmediato(0x18003b531, 0x50, 0.55, _pr, 'fondo del aviso (R)')
color_inmediato(0x18003b539, 0x54, 0.30, _pg, 'fondo del aviso (G)')
color_inmediato(0x18003b541, 0x58, 1.00, _pb, 'fondo del aviso (B)')

# Borde del aviso (AddRect). El alfa sigue latiendo 0.30..0.85.
color_inmediato(0x18003b599, 0x50, 0.70, _ar, 'borde del aviso (R)')
color_inmediato(0x18003b5a1, 0x54, 0.50, _ag, 'borde del aviso (G)')
color_inmediato(0x18003b5a9, 0x58, 1.00, _ab, 'borde del aviso (B)')

# Titulo "MOUSE ACTIVO": R = 0.20 + pulso*0.40, G = 0.72 + pulso*0.20, B = 0.97.
# Late entre #33b8f8 (el celeste de la multimedia) y un cian claro.
POOL_020 = 0x180144e84   # 0.2   \
POOL_040 = 0x180144e98   # 0.4    > valores que ya existen en el pool de .rdata
POOL_072 = 0x180144eb4   # 0.72  /
repuntar(0x18003b615, 8, 0x180144e84, POOL_040, 'amplitud R del titulo')
repuntar(0x18003b61d, 8, 0x180144eb0, POOL_020, 'base R del titulo')
repuntar(0x18003b62b, 9, 0x180144e8c, POOL_020, 'amplitud G del titulo')
repuntar(0x18003b634, 9, 0x180144ea0, POOL_072, 'base G del titulo')
color_inmediato(0x18003b644, 0x58, 1.00, _ab, 'titulo del aviso (B)')

# Segunda linea ("Pulsa F8 ..."): ImVec4 exclusiva, se reescribe entera.
_off_l2 = va_to_offset(0x180144fa0)
_l2_antes = struct.pack('<4f', 0.9, 0.88, 0.98, 0.92)
if bytes(dll[_off_l2:_off_l2 + 16]) != _l2_antes:
    raise SystemExit(' [ERROR] La ImVec4 de la segunda linea del aviso no es la '
                     'esperada.')
dll[_off_l2:_off_l2 + 16] = struct.pack('<4f', *rgb(AZUL_SUAVE), 0.92)

print(f' [OK] Aviso repintado con la paleta de la multimedia: fondo {AZUL_PANEL}, '
      f'borde/titulo {AZUL_ACENTO}, texto {AZUL_SUAVE}')

print(f' [OK] Aviso del modo raton en espanol: "{TITULO.decode()}" / '
      f'"{(PREFIJO + b"F8" + SUFIJO).decode()}"')

# ------------------------------------------------------------------------------
# 6. Orientacion de las pantallas (V-flip)
# ------------------------------------------------------------------------------
# Cada preset de pantalla guarda dos banderas: flip (invierte la textura en
# vertical al pintarla sobre el mesh del camion) y flip_split (fuerza el reparto
# vertical en pantalla dividida). La malla de la "Multimidia Compacta / Scania"
# tiene las UV al reves, asi que ESE preset necesita el V-flip ACTIVADO; los
# otros tres no. Son los valores con los que se calibro el mod y los que aqui se
# fijan de forma explicita en cada recompilacion.
#
# 2026-08-29: el build anterior forzaba (0, 0) en los cuatro presets, lo que
# dejaba la pantalla del mod de Scania siempre boca abajo. Comprobado en juego.
ORIENTACION = {
    "scania":  (1, 1),   # mesh con UV invertidas -> hay que compensar
    "central": (0, 0),
    "vidrio":  (0, 0),
    "celular": (0, 0),
}

import fix_flip_pantalla as flip

_dll_flip = bytes(dll)
for _clave, _preset in flip.PRESETS.items():
    _antes = flip.leer_estado(_dll_flip, _preset)
    if _antes is None:
        raise SystemExit(f" [ERROR] Preset de pantalla '{_clave}' no reconocido en la DLL base.")
    _quiero = ORIENTACION[_clave]
    if _antes != _quiero:
        _dll_flip = flip.aplicar(_dll_flip, _preset, *_quiero)
        print(f" [OK] V-flip {_antes} -> {_quiero} en '{_clave}' ({_preset['titulo']})")
    else:
        print(f" [OK] V-flip ya correcto {_quiero} en '{_clave}' ({_preset['titulo']})")
dll = bytearray(_dll_flip)

pe.close()
del pe
gc.collect()

with open('dxgi.dll', 'wb') as f:
    f.write(dll)

print("=" * 80)
print(">>> dxgi.dll generado y verificado con exito.")
print("=" * 80)

# -*- coding: utf-8 -*-
"""
================================================================================
MULTIMEDIA ATS SANTI - Official Master Build Script
================================================================================
1. Dual-Key XOR encryption e inyección de los 5 módulos HTML en .rdata.
2. Compuerta nativa de render (la multimedia no se pinta hasta que el usuario
   pulsa INICIAR), desbloqueo de planes/navegación y licencia universal offline.
3. Tecla Oficial de Navegación F8 (VK_F8 = 0x77 = 119).
4. Activación permanente de Licencia Universal Offline (MMATS-SANTI-2026-UNIVERSAL).
5. Roadworks Cursor: sustituye el HLSL del cursor F8 (bolinha) por la flecha con
   franjas de obra, con la punta como hotspot exacto.
6. Aviso "MOUSE ACTIVO" del modo interactivo (F8): textos en español, arreglo
   de las longitudes que el compilador dejó fijas para el prefijo y el sufijo,
   y repintado con la paleta azul de la multimedia.
7. Ocurrencia del render target de la Multimedia Compacta: SU preset venia con
   hit index 0, que significa "pinta en TODAS las ocurrencias", y por eso la
   multimedia salia tambien en el cuadro de instrumentos (DIC).
8. Orientación de las pantallas: fija las banderas de V-flip de cada preset
   para que no se pierdan en cada recompilación.
9. Calidad: quita --disable-gpu de los argumentos del WebView2.
10. Resolución de render del WebView2 (supermuestreo sobre el render target).
11. Cierre del juego: REPONE la guarda original de DllMain. Los parches que se
    saltaban destructores en DLL_PROCESS_DETACH no arreglaban nada (esa rama ya
    estaba guardada) y dejaban el WndProc del juego colgando. Prohibido volver.
12. Auditoría final: .text no puede cambiar en ningún byte que algún paso no
    haya declarado. Aborta la compilación si aparece uno.
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

# ------------------------------------------------------------------------------
# Escrituras verificadas sobre .text
# ------------------------------------------------------------------------------
# La DLL base de la que se parte (BACKUP_MULTIMEDIAATS_SEGURIDAD/dxgi.dll) NO es
# el binario original del mod: arrastra parches de compilaciones anteriores
# grabados dentro (por ejemplo en 0x1800c1bd5 hay seis NOP y en 0x1800c212d un
# 'mov r9d, 1' que puso una version vieja de este script). Por eso ningun paso
# puede dar por hecho lo que hay en un sitio: se comprueba antes de escribir y
# se acepta explicitamente tanto la forma original como la ya parcheada.
#
# Todo lo que este script escribe en .text pasa por aqui, y REGISTRO_TEXT lleva
# la cuenta para la auditoria final: al terminar se comparan base y resultado
# byte a byte y no puede haber ni un solo cambio en .text fuera de esta lista.
REGISTRO_TEXT = []

def parchear(va, esperado, nuevo, etiqueta):
    """Escribe `nuevo` en `va` solo si alli sigue estando `esperado`."""
    return parchear_variantes(va, [esperado], nuevo, etiqueta)

def parchear_variantes(va, aceptados, nuevo, etiqueta):
    """
    Igual que parchear() pero admitiendo varias formas de partida (la original
    y las que dejaron compilaciones anteriores). Devuelve False si lo que hay
    ya es exactamente lo que se queria escribir.
    """
    off = va_to_offset(va)
    actual = bytes(dll[off:off + len(nuevo)])
    REGISTRO_TEXT.append((off, len(nuevo), etiqueta, va))
    if actual == nuevo:
        return False
    for esperado in aceptados:
        if bytes(dll[off:off + len(esperado)]) == esperado:
            dll[off:off + len(nuevo)] = nuevo
            return True
    raise SystemExit(
        f' [ERROR] {etiqueta} en {va:#x}: la DLL base no trae ninguno de los\n'
        f'         patrones esperados. Hay: {actual.hex()}\n'
        f'         Se esperaba uno de: ' +
        ', '.join(e.hex() for e in aceptados))

def escribir_text(va, nuevo, etiqueta):
    """Escritura en .text sin patron de partida, pero anotada para la auditoria."""
    off = va_to_offset(va)
    REGISTRO_TEXT.append((off, len(nuevo), etiqueta, va))
    dll[off:off + len(nuevo)] = nuevo

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
        nuevo = len(f.read().replace('\r\n', '\n').encode('utf-8'))
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
        new_content = f.read().replace('\r\n', '\n')

    new_bytes = new_content.encode('utf-8')
    enc_bytes = encrypt_dual_key_xor(new_bytes, k1, k2)
    dll[data_off : data_off + len(new_bytes)] = enc_bytes
    dll[entry_off+16 : entry_off+24] = struct.pack('<Q', len(new_bytes))
    print(f" [OK] Recurso inyectado: {res_name} ({len(new_bytes)} bytes)")

# ------------------------------------------------------------------------------
# 2. Desbloqueo de Licencia Universal y Compuerta de Inicio de Multimedia
# ------------------------------------------------------------------------------
# COMPUERTA NATIVA DE RENDER: nada se pinta en la cabina hasta que se pulsa INICIAR
# ------------------------------------------------------------------------------
# El original de este sitio era la comprobacion de LICENCIA, no de arranque:
#
#     0x1800c1bc7  call 0x180030410            ; &config
#     0x1800c1bcc  movzx ecx, byte [rax+0x81]  ; config.modEn (licencia/entitlement)
#     0x1800c1bd3  test cl, cl
#     0x1800c1bd5  je   0x1800c22b5            ; sin licencia -> no pintar
#
# Una version anterior de este script puso seis NOP encima del `je` para saltarse
# la licencia. El efecto colateral fue que la funcion de pintado se quedo SIN
# ninguna condicion propia: en cuanto habia un render target reconocido, pintaba.
# Eso, sumado a que el overlay mandaba 'startMm' solo con abrirse, es lo que hacia
# que la multimedia apareciera en el camion sin que nadie pulsara INICIAR.
#
# La condicion correcta es el rtHash del renderizador, [rdi+0x1a0]. Es el estado
# de arranque de verdad y se comprobo instruccion a instruccion en el binario:
#
#   * nace a 0            -> constructor del renderizador (0x1800c7945)
#   * 'startMm'  lo pone  -> 0x1800e57df llama a SetRtHash(renderizador, hash)
#   * 'selectHash' lo pone-> 0x1800e5a6c, mismo SetRtHash
#   * 'stopMm'   lo borra -> 0x1800e5997 llama a SetRtHash(renderizador, 0)
#
# No hay ningun otro sitio en toda la DLL que escriba ese campo (los unicos que
# quedan son los botones "limpiar" de la ventana ImGui, que tambien mandan 0), y
# la lectura del .ini de multimedia_rt_hash NO lo toca. O sea: vale 0 mientras el
# usuario no arranque la multimedia, y vuelve a 0 en cuanto la para.
#
# 0x1800c1bc7: cmp qword [rdi+0x1a0], 0 ; je 0x1800c22b5 ; 6 NOP
_GATE_ORIGINAL = bytes.fromhex('e844e8f6ff0fb6888100000084c90f84da060000')
_GATE_P3       = bytes.fromhex('e844e8f6ff0fb6888100000084c9909090909090')
parchear_variantes(0x1800c1bc7, [_GATE_ORIGINAL, _GATE_P3],
                   bytes.fromhex('4883bfa001000000' '0f84e0060000' '909090909090'),
                   'compuerta de render de la multimedia')

# DIAGNOSTICO [MM-DIAG]: se devuelve el valor de verdad de modEn
# ------------------------------------------------------------------------------
# Este sitio NO es getState (getState se atiende en 0x1800e6fa9); es el ultimo
# argumento de la linea de log
#
#     [MM-DIAG] novo maxHit={} hitIdxAlvo={} hash=0x{:016X} pintaria={} modEn={}
#
# La misma version antigua que NOPeo la licencia dejo aqui un 'mov r9d, 1' para
# que el log dijera siempre modEn=1, y una posterior lo cambio por un
# 'neg rax / sbb r9d, r9d' que escribe -1. Las dos mienten. Se repone la forma
# original -leer config.modEn- que ademas cabe exacta en los 13 bytes:
#     call 0x180030410 ; movzx r9d, byte [rax+0x81]
_DIAG_P3 = bytes.fromhex('e8e3e2f6ff' '41b901000000' '9090')
_DIAG_P4 = bytes.fromhex('488b87a0010000' '48f7d8' '4519c9')
parchear_variantes(0x1800c2128, [_DIAG_P3, _DIAG_P4],
                   bytes.fromhex('e8e3e2f6ff' '440fb68881000000'),
                   'modEn del log [MM-DIAG]')

# Desbloqueos de planes / navegación web en WebView2 (YouTube, Spotify, etc.)
escribir_text(0x1800ce420, bytes([0xB0, 0x01, 0xC3]), 'plan/feature -> siempre disponible')
escribir_text(0x1800cb252, bytes([0xBA, 0x00, 0x00, 0x00, 0x00]), 'cancelacion de navegacion')
escribir_text(0x1800cb25a, bytes([0x90, 0x90]), 'llamada de bloqueo de navegacion')

# LICENCIA UNIVERSAL OFFLINE
# ------------------------------------------------------------------------------
# config+0x81 NO es "multimedia encendida": es el flag de licencia/entitlement
# del mod. Se comprobo en tres sitios del binario:
#
#   0x180030965  if (config.b81) reintento_licencia = 300000 ms  else 20000/8000
#   0x180031a6d  if (config.b81 && sesion && sesion.ok1 && sesion.ok2) { ... }
#   0x18002faf7  se pasa como argumento al aplicar la licencia
#
# y es el mismo byte que el log [MM-DIAG] imprime como modEn. La compilacion
# anterior lo puso a 0 creyendo que apagaba la multimedia al inicio; lo que hacia
# en realidad era dejar el mod en estado NO licenciado, con el reintento de
# licencia disparandose cada 8-20 segundos. Vuelve a 1.
#
# Lo que apaga la multimedia al inicio es la compuerta de render de arriba, que
# es estado de ejecucion y no se guarda en ningun sitio.
lic_off = va_to_offset(0x1801f9290)
dll[lic_off + 0x80] = 1   # Licencia activa permanente
dll[lic_off + 0x81] = 1   # modEn: mod licenciado (NO es el interruptor de arranque)
dll[lic_off + 0x31c] = 1  # Entitlements activos
print(" [OK] Compuerta de render: cero pintado hasta que el usuario pulse INICIAR")
print(" [OK] Licencia universal offline activa (modEn = 1)")

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
    REGISTRO_TEXT.append((off + largo - 4, 4, etiqueta, va))
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
# 7. Ocurrencia del render target de la "Multimidia Compacta"
# ------------------------------------------------------------------------------
# POR QUE LA MULTIMEDIA SALIA TAMBIEN EN EL CUADRO DE INSTRUMENTOS
# ------------------------------------------------------------------------------
# El rtHash con el que el mod localiza una pantalla es un FNV-1a del DESCRIPTOR
# de la textura (Width, Height, MipLevels, Format, ArraySize), no del recurso.
# Dos render targets distintos con el mismo tamano y formato dan el MISMO hash.
# En la cabina, la radio central y la pantallita del cuadro de instrumentos (DIC)
# son dos RT de 256x256 identicos en descriptor: los dos son E2A0D7B1DF649166 y
# no hay forma de separarlos por hash.
#
# Para eso existe el hit index: la DLL cuenta las ocurrencias de ese RT dentro
# del frame y solo pinta la que coincide. El preset "scania" venia con el hit
# index a **0**, y 0 significa "pinta en TODAS": de ahi que la multimedia
# apareciera a la vez en la radio y en el cuadro de instrumentos. No es una
# segunda instancia del reproductor ni una copia del contenido, es el MISMO
# pintado ejecutandose dos veces por frame.
#
# La tabla que de verdad se usa se construye en .text (constructor estatico del
# mapa rtHash -> preset), con entradas de 24 bytes:
#     u64 hash | f32 | f32 | u32 hit | u8 flip | u8 flip_split | 2 de relleno
# La tabla parecida de .rdata (0x180143e10) no tiene ninguna referencia desde el
# codigo: parchearla no hace nada.
#
# El bloque del preset scania ocupa 24 bytes y no sobra sitio, asi que el hueco
# sale de la copia de los 2 bytes de RELLENO de la estructura (movzx eax,
# word [rbp-0x1b] + mov [rbp-0x03], ax). Esa copia es prescindible -son bytes de
# alineacion dentro de un valor de mapa, nadie los lee- y fix_flip_pantalla.py
# ya la sobrescribe por su cuenta al convertir la forma "bx" en la forma "imm".
#
# La instruccion del V-flip se deja EXACTAMENTE donde estaba (tabla+0x44) para
# que fix_flip_pantalla.py siga encontrandola en su offset de siempre y el paso
# 8 pueda fijar el flip sin enterarse de este parche.
TABLA_PRESETS_VA = 0x180001360
SCANIA_VA = TABLA_PRESETS_VA + 0x3A     # primer byte del bloque a reescribir

# DE DONDE SALEN LOS VALORES NUEVOS: ESCALA DE MULTIMEDIA CENTRAL Y HIT = 1
# ------------------------------------------------------------------------------
# Comparando los cuatro presets de la DLL base, el de la Multimidia Compacta era
# el unico distinto EN TODOS los campos:
#
#     preset               f32 #1    f32 #2   hit   flip
#     Multimedia Central   0.31000   0.38000    3   (0,0)
#     GPS Parabrisas       0.31000   0.38000    1   (0,0)
#     GPS Movil            0.31000   0.38000    1   (0,0)
#     Multimidia Compacta  0.31800   0.36300    0   (1,1)   <- el raro
#
# Se le asigna la misma escala f32 (0.31000 / 0.38000) de Multimedia Central,
# hit = 1 (para renderizar de inmediato en la cabina del Scania) y flip = (0, 0).
CENTRAL_F1 = TABLA_PRESETS_VA + 0x63     # imm32 del primer float (Multimedia Central: 0x1800013c3)
CENTRAL_F2 = TABLA_PRESETS_VA + 0x6A     # imm32 del segundo float (Multimedia Central: 0x1800013ca)

_f1 = bytes(dll[va_to_offset(CENTRAL_F1):va_to_offset(CENTRAL_F1) + 4])
_f2 = bytes(dll[va_to_offset(CENTRAL_F2):va_to_offset(CENTRAL_F2) + 4])
_hit = struct.pack('<I', 1)              # hit = 1 para que pinte de inmediato en cabina

print(f' [..] Configurando Multimedia Compacta (Scania mod): '
      f'f32 {struct.unpack("<f", _f1)[0]:.5f} / {struct.unpack("<f", _f2)[0]:.5f}, '
      f'hit {int.from_bytes(_hit, "little")}')

# Primer float de la Compacta: instruccion propia, justo antes del bloque.
_off_f1_sc = va_to_offset(TABLA_PRESETS_VA + 0x36)
if bytes(dll[_off_f1_sc - 3:_off_f1_sc]) != bytes.fromhex('c745ef'):
    raise SystemExit(' [ERROR] El primer float del preset scania no esta donde se esperaba.')
escribir_text(TABLA_PRESETS_VA + 0x36, _f1, 'preset scania: primer float')

_off_sc = va_to_offset(SCANIA_VA)
_orig_sc = bytes(dll[_off_sc:_off_sc + 24])
_esperado_sc = bytes.fromhex(
    '48c745f323dbb93e'      # mov qword [rbp-0x0D], 0x3EB9DB23  (f32 + hit = 0)
    '33db'                  # xor  ebx, ebx
    '66c745fb0101'          # mov  word  [rbp-0x05], 0x0101     (flip, flip_split)
    '0fb745e5'              # movzx eax, word [rbp-0x1b]        (copia de relleno)
    '668945fd'              # mov  [rbp-0x03], ax               (copia de relleno)
)
if _orig_sc != _esperado_sc:
    raise SystemExit(
        f' [ERROR] El bloque del preset scania en {SCANIA_VA:#x} no es el esperado.\n'
        f'         hay: {_orig_sc.hex()}\n'
        f'         esp: {_esperado_sc.hex()}')

# Los 2 bytes de valor del flip, tal cual estaban: van detras de los 4 de opcode
# del 'mov word [rbp-0x05], imm16', que empieza en el byte 10 del bloque.
_flip_orig = _orig_sc[14:16]
_nuevo_sc = (
    bytes.fromhex('c745f3') + _f2       # mov dword [rbp-0x0D], f32 #2 de Multimedia Central
    + b'\x90'                           # nop  (el qword original ocupaba un byte mas)
    + bytes.fromhex('33db')             # xor  ebx, ebx   (los otros presets lo usan a 0)
    + bytes.fromhex('66c745fb') + _flip_orig   # mov word [rbp-0x05], flip  <- MISMO offset
    + bytes.fromhex('c745f7') + _hit    # mov dword [rbp-0x09], hit = 1
    + b'\x90'                           # nop
)
if len(_nuevo_sc) != 24:
    raise SystemExit(f' [ERROR] El bloque nuevo mide {len(_nuevo_sc)} bytes y tienen que ser 24.')
escribir_text(SCANIA_VA, _nuevo_sc, 'preset scania: bloque de 24 bytes')
print(f' [OK] Multimedia Compacta: misma configuracion que el GPS Parabrisas (hit 1)')

# NO se toca la comparacion del hit index de 0x1800c2256 (el `je`). Es codigo
# COMPARTIDO por los cuatro presets: cambiarlo a `jge` alteraria tambien el
# comportamiento de la Multimedia Central, el GPS Parabrisas y el GPS Movil, y
# aqui solo hay que corregir la Multimedia Compacta. El unico cambio de este
# paso es el valor por defecto de SU preset, que es un dato suyo y de nadie mas.

# ------------------------------------------------------------------------------
# 8. Orientacion de las pantallas (V-flip)
# ------------------------------------------------------------------------------
# Cada preset de pantalla guarda dos banderas: flip (invierte la textura en
# vertical al pintarla sobre el mesh del camion) y flip_split (fuerza el reparto
# vertical en pantalla dividida).
#
# 2026-08-30: la Multimidia Compacta salia BOCA ABAJO con el V-flip activado, asi
# que este preset pasa a (0, 0) como los otros tres. El historial de este valor
# es accidentado -estuvo en (0,0) el 28/08, se subio a (1,1) el 29/08 porque
# entonces salia al reves, y ahora vuelve a (0,0)-, y la razon de fondo es que el
# flip va por HASH DE RENDER TARGET, no por camion: 256x256 es un tamano
# generico, asi que mallas de cabinas distintas caen en el mismo preset con las
# UV en sentidos opuestos y una sola bandera no puede servir a las dos. Si
# alguna vez vuelve a verse invertida, se cambia sin recompilar con:
#     python fix_flip_pantalla.py --preset scania --flip on
#
# OJO AL CURSOR: el cursor del modo F8 no pasa por el shader del contenido, se
# graba directo en el render target, asi que en un preset con flip=1 sale
# espejado y hace falta compensarlo dentro de roadworks_cursor.hlsl. Con (0,0)
# NO hay que compensar nada, y el roadworks_cursor.hlsl de este repo no lleva
# compensacion: los dos valores son coherentes tal y como estan. Si se vuelve a
# poner flip=1 hay que reponer tambien esa linea en el .hlsl.
# ESTE VALOR SE HA IDO Y HA VUELTO TRES VECES (28/08 -> 29/08 -> 30/08). Antes de
# volver a cambiarlo, leer el bloque de invariantes que hay justo debajo del
# bucle: el flip y la compensacion del cursor van EN PAREJA y cambiar uno solo
# deja el cursor espejado sin que nada avise. Para probar el otro valor no hace
# falta recompilar:
#     python fix_flip_pantalla.py --preset scania --flip on --dll <juego>\dxgi.dll
ORIENTACION = {
    "scania":  (0, 0),   # UV estandar en la malla de este camion
    "central": (0, 0),
    "vidrio":  (0, 0),
    "celular": (0, 0),
}

# Presets cuyo render target es CUADRADO (256x256). Es el discriminante que usa
# la compensacion del cursor dentro del .hlsl, porque el shader no recibe la
# bandera de flip y de los cuatro presets solo el del Scania es cuadrado.
PRESETS_CUADRADOS = {"scania"}

# La linea que compensa el espejado del cursor cuando el preset va con flip=1.
COMPENSACION_CURSOR = 'rtData.x-rtData.y'

import fix_flip_pantalla as flip

_dll_flip = bytes(dll)
for _clave, _preset in flip.PRESETS.items():
    _antes = flip.leer_estado(_dll_flip, _preset)
    if _antes is None:
        raise SystemExit(f" [ERROR] Preset de pantalla '{_clave}' no reconocido en la DLL base.")
    _quiero = ORIENTACION[_clave]
    if _antes != _quiero:
        _dll_flip = flip.aplicar(_dll_flip, _preset, *_quiero)
        REGISTRO_TEXT.append((_preset['offset'], 8, f"V-flip '{_clave}'", 0))
        print(f" [OK] V-flip {_antes} -> {_quiero} en '{_clave}' ({_preset['titulo']})")
    else:
        REGISTRO_TEXT.append((_preset['offset'], 8, f"V-flip '{_clave}'", 0))
        print(f" [OK] V-flip ya correcto {_quiero} en '{_clave}' ({_preset['titulo']})")
dll = bytearray(_dll_flip)

# INVARIANTE FLIP <-> CURSOR
# ------------------------------------------------------------------------------
# El cursor del modo F8 no pasa por el shader del contenido: se graba directo en
# el render target. En un preset con flip=1 sale espejado y hay que compensarlo
# dentro de roadworks_cursor.hlsl. Las dos cosas tienen que moverse a la vez.
#
# Historial de este par: (0,0) el 28/08, (1,1) el 29/08 tras verlo boca abajo en
# el juego, (0,0) otra vez el 30/08 tras volver a verlo boca abajo. Cada vuelta
# tocaba solo uno de los dos lados. Esta comprobacion existe para que no se pueda
# repetir: si alguien cambia ORIENTACION y se olvida del .hlsl, la compilacion se
# para en vez de dejar el cursor invertido en silencio.
_con_flip = {c for c, (f, _) in ORIENTACION.items() if f}
if _con_flip - PRESETS_CUADRADOS:
    raise SystemExit(
        f' [ERROR] Presets no cuadrados con flip=1: {sorted(_con_flip - PRESETS_CUADRADOS)}.\n'
        f'         La compensacion del cursor discrimina por RT cuadrado, asi que\n'
        f'         un preset no cuadrado con flip deja el cursor espejado.')

_tiene_compensacion = COMPENSACION_CURSOR in _hlsl.decode('utf-8')
if bool(_con_flip) != _tiene_compensacion:
    raise SystemExit(
        f" [ERROR] V-flip y cursor descuadrados.\n"
        f"         Presets con flip=1: {sorted(_con_flip) or 'ninguno'}\n"
        f"         roadworks_cursor.hlsl compensa el espejado: "
        f"{'si' if _tiene_compensacion else 'no'}\n"
        f"         Si pones flip=1 hay que anadir al .hlsl, tras calcular p:\n"
        f"             if (abs(rtData.x-rtData.y)<0.5) p.y = rtData.y-p.y;\n"
        f"         y si lo quitas hay que quitarla.")
print(f" [OK] V-flip y compensacion del cursor coherentes "
      f"(presets con flip: {sorted(_con_flip) or 'ninguno'})")

# ------------------------------------------------------------------------------
# 9. Calidad de imagen: quitar --disable-gpu de los argumentos del WebView2
# ------------------------------------------------------------------------------
# La DLL llama a SetEnvironmentVariableW(L"WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS")
# con una cadena UTF-16 que traia --disable-gpu. Ese flag mete a Chromium ENTERO
# en rasterizacion por software: el texto sale emborronado, los degradados con
# bandas y el video a tirones, porque cada pixel de la pagina lo compone la CPU.
# Es la causa de que la multimedia se viera de baja calidad.
#
# Los otros tres flags SI hacen falta y se conservan: la ventana anfitriona del
# WebView2 esta oculta, y sin ellos Chromium considera que la pestana no se ve y
# la estrangula a ~1 fps.
#
# La cadena es NUL-terminated y sin longitud fija en ningun sitio, asi que basta
# con reescribirla mas corta y rellenar con ceros.
ARGS_VA = 0x180169840
FLAG_FUERA = ' --disable-gpu'

_off_args = va_to_offset(ARGS_VA)
_fin_args = _off_args
while dll[_fin_args:_fin_args + 2] != b'\x00\x00':
    _fin_args += 2
_args = bytes(dll[_off_args:_fin_args]).decode('utf-16-le')

if FLAG_FUERA not in _args:
    print(f' [OK] Argumentos del WebView2: {FLAG_FUERA.strip()} ya no estaba')
else:
    _args_nuevo = _args.replace(FLAG_FUERA, '')
    _cod = _args_nuevo.encode('utf-16-le')
    if len(_cod) > _fin_args - _off_args:
        raise SystemExit(' [ERROR] Los argumentos nuevos del WebView2 no caben.')
    dll[_off_args:_fin_args] = _cod + bytes(_fin_args - _off_args - len(_cod))
    print(f' [OK] Calidad: quitado {FLAG_FUERA.strip()} de los argumentos del WebView2 '
          f'(se acabo la rasterizacion por software)')

# ------------------------------------------------------------------------------
# 10. Tamano del lienzo del WebView2 (el mayor coste por frame de la multimedia)
# ------------------------------------------------------------------------------
# QUE ES ESTE NUMERO EN REALIDAD
# ------------------------------------------------------------------------------
# Durante mucho tiempo se documento como "limite maximo de la textura". No lo es.
# Desensamblando las dos rutinas que lo usan (0x1800ce4ce y 0x1800c237e) se ve
# que es el LADO LARGO FIJO del lienzo del WebView2, y que el lado corto sale de
# la proporcion del render target:
#
#     cmp  esi, edi                 ; ancho_RT vs alto_RT
#     jae  ...                      ; el lado mayor se fija al valor de abajo
#     imul rax, r8, 0x320           ; el otro = otro_lado * VALOR / lado_mayor
#     div  rcx
#
# O sea que NO topa nada: multiplica. El area del lienzo crece con el CUADRADO
# de este numero, y cada pixel de ese lienzo lo paga tres veces por frame:
# Chromium lo compone, la captura lo lee (WGC por GPU o, si WGC no esta
# disponible, PrintWindow por CPU) y se sube a una textura D3D11.
#
# POR QUE 1024
# ------------------------------------------------------------------------------
# El destino real son los render targets de la cabina, y son diminutos:
#
#     preset                 RT         lienzo con 800   con 1920    con 1024
#     Multimidia Compacta   256x256      800x800  0,64MP  3,69MP     1,05MP
#     Multimedia Central    512x256      800x400  0,32MP  1,84MP     0,52MP
#     el mayor de los 4    1024x512      800x400  0,32MP  1,84MP     0,52MP
#
# Con 800 de fabrica la pantalla mas grande salia SUB-MUESTREADA (800 para un RT
# de 1024 de ancho = 0,78 pixeles por pixel): esa, y no otra, era la causa de que
# se viera borrosa, y de ahi vino el parche que subio esto a 3840.
#
# Pero 3840 y 1920 se pasaron al otro lado. El propio mod lo deja escrito:
#
#     [WV2] fit main viewport 3840x1920 p/ RT 512x256
#
# 7,4 millones de pixeles calculados para volcarlos en 131 mil. Y encima esa
# textura acaba dibujada en el monitor a unos 200-300 px de ancho, que es lo que
# ocupa la tablet del camion en pantalla.
#
# 1024 es el ancho del render target mas grande de los cuatro presets, asi que
# es el numero mas pequeno con el que NINGUNA pantalla queda sub-muestreada:
#
#     - la mayor (1024x512) va 1:1, sin perdida
#     - la Central (512x256) va a x2 lineal
#     - la Compacta (256x256) va a x4 lineal
#
# y cuesta 3,5 VECES MENOS que 1920 en las tres. Si algun dia un mod trae una
# pantalla mayor de 1024 px de lado, este es el unico numero que hay que subir.
#
# COMO COMPROBARLO EN JUEGO
# ------------------------------------------------------------------------------
# Con EnableLogging=1, lucidgfx.log trae dos lineas que lo dicen todo:
#     [WV2] fit main viewport {}x{} p/ RT {}x{}   <- el lienzo que se esta usando
#     [MM-FPS] PrintWindow={}ms intervalo={}ms    <- SOLO sale si la captura va
#                                                   por CPU. Si aparece, cada
#                                                   frame paga esos ms enteros.
# Si en su lugar sale "[MM-FPS] captura GPU-side (WGC) ATIVA", la captura no
# toca la CPU y el coste que queda es el de componer el lienzo.
LADO_CANVAS = 1024

_res_bytes = struct.pack('<I', LADO_CANVAS)
_res_orig = struct.pack('<I', 0x320)

_patches_lienzo = [
    (0x1800c237e + 1, 'ancho D3D11'),
    (0x1800c2383 + 3, 'alto D3D11'),
    (0x1800c2394 + 2, 'alto D3D11'),
    (0x1800c239a + 3, 'ancho D3D11'),
    (0x1800ce4d5 + 3, 'ancho WebView2'),
    (0x1800ce4e9 + 1, 'alto WebView2'),
    (0x1800ce505 + 2, 'ancho WebView2'),
    (0x1800ce50b + 3, 'alto WebView2'),
]

for _va, _tag in _patches_lienzo:
    _off = va_to_offset(_va)
    REGISTRO_TEXT.append((_off, 4, f'lado del lienzo WebView2 ({_tag})', _va))
    if bytes(dll[_off:_off+4]) == _res_orig:
        dll[_off:_off+4] = _res_bytes
        print(f' [OK] Lienzo WebView2: {_tag} -> {LADO_CANVAS} px')
    elif bytes(dll[_off:_off+4]) == _res_bytes:
        print(f' [OK] Lienzo WebView2: {_tag} ya en {LADO_CANVAS} px')
    else:
        print(f' [AVISO] Patron en {_va:#x} ({_tag}) no coincidio: {bytes(dll[_off:_off+4]).hex()}')

# ------------------------------------------------------------------------------
# 11. Cierre del juego: se REPONE la guarda original de DllMain
# ------------------------------------------------------------------------------
# La compilacion anterior escribia aqui un 'jmp' (EB 58) sobre el arranque de la
# rama DLL_PROCESS_DETACH, con la idea de saltarse la limpieza y evitar el
# 0xC0000005 al salir. Desensamblando la DLL base se ve que ese parche no podia
# arreglar nada, porque la guarda que buscaba YA ESTABA:
#
#     0x18001e762  test edx, edx          ; edx = lpReserved
#     0x18001e764  jne  0x18001e7bc       ; proceso terminando -> saltar limpieza
#     0x18001e766  ...  log + SetWindowLongPtrW(GWLP_WNDPROC, original)
#     0x18001e795  ...  Config::shutdown / X::shutdown / Logger::shutdown
#     0x18001e7bc  mov eax, 1 ; add rsp, 0x30 ; pop rbx ; ret
#
# Windows pasa lpReserved != NULL cuando el proceso se esta cerrando, que es
# exactamente el caso "se cierra ATS": el 'jne' ya se tomaba y la limpieza ya se
# saltaba. Convertirlo en 'jmp' incondicional NO cambia nada en esa ruta.
#
# Lo que si cambia es la OTRA ruta, la de FreeLibrary (lpReserved == NULL): con
# el 'jmp' la DLL se descarga SIN devolver el WndProc de la ventana del juego a
# su valor original. El puntero del WndProc sigue apuntando a codigo que acaba de
# desaparecer del mapa de memoria, y el siguiente mensaje que reciba la ventana
# entra por ahi: eso si es un 0xC0000005 garantizado, y ademas quedan sin cerrar
# la configuracion y el log.
#
# Es el mismo patron de "saltarse destructores" que ya rompio el mod dos veces.
# Se repone el 'test edx, edx' y la limpieza vuelve a ser correcta en las dos
# rutas. Los WebView2 que el juego deja sueltos al morir NO se recogen desde
# aqui -en DLL_PROCESS_DETACH ya no se puede hacer nada fiable-, los recoge
# RecolectorWebView dentro de mmats_audio_inmersivo.exe, que vive fuera del
# proceso del juego y puede esperar a que ATS haya desaparecido del todo.
parchear_variantes(0x18001e762,
                   [bytes.fromhex('85d2'), bytes.fromhex('eb58')],
                   bytes.fromhex('85d2'),
                   'guarda lpReserved de DLL_PROCESS_DETACH')
print(" [OK] DllMain: guarda original de DLL_PROCESS_DETACH intacta "
      "(sin saltos que dejen el WndProc colgado)")

# ------------------------------------------------------------------------------
# 12. Auditoria: en .text no puede haber ni un byte cambiado fuera de lo previsto
# ------------------------------------------------------------------------------
# Los sustos de este mod siempre han venido de escrituras en .text: un salto que
# se come destructores, un code cave que cuelga el juego, una tabla de presets
# reescrita a ojo. Aqui se compara la DLL base con la generada byte a byte y se
# aborta si aparece un cambio en .text que ningun paso haya declarado.
with open('BACKUP_MULTIMEDIAATS_SEGURIDAD/dxgi.dll', 'rb') as f:
    _base = f.read()

_permitido = set()
for _off, _n, _etq, _va in REGISTRO_TEXT:
    _permitido.update(range(_off, _off + _n))

_secs = {s.Name.rstrip(b'\x00').decode(): (s.PointerToRawData,
                                           s.PointerToRawData + s.SizeOfRawData)
         for s in pe.sections}
_ini_text, _fin_text = _secs['.text']

_intrusos = [i for i in range(_ini_text, _fin_text)
             if _base[i] != dll[i] and i not in _permitido]

_por_seccion = {}
for _nombre, (_a, _b) in _secs.items():
    _n = sum(1 for i in range(_a, _b) if _base[i] != dll[i])
    if _n:
        _por_seccion[_nombre] = _n

print("-" * 80)
print(" [AUDIT] Bytes cambiados respecto a la DLL base, por seccion:")
for _nombre, _n in sorted(_por_seccion.items()):
    print(f"         {_nombre:<10} {_n:>8} bytes")
print(f" [AUDIT] Sitios declarados en .text: {len(REGISTRO_TEXT)} "
      f"({len(_permitido)} bytes cubiertos)")

if _intrusos:
    print("!" * 80)
    print(f"ABORTADO: {len(_intrusos)} bytes de .text cambiados fuera de los sitios")
    print("declarados. Primeros offsets:", [hex(i) for i in _intrusos[:16]])
    print("!" * 80)
    raise SystemExit(1)
print(" [AUDIT] OK: .text solo cambia en los sitios declarados.")

pe.close()
del pe
gc.collect()

with open('dxgi.dll', 'wb') as f:
    f.write(dll)

print("=" * 80)
print(">>> dxgi.dll generado y verificado con exito.")
print("=" * 80)

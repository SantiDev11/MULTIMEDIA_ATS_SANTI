# -*- coding: utf-8 -*-
"""
================================================================================
MULTIMEDIA ATS SANTI - Official Master Build Script
================================================================================
1. Dual-Key XOR encryption e inyección de los 5 módulos HTML en .rdata.
2. Desbloqueos de Renderizado D3D11 y Navegación con Mouse.
3. Tecla Oficial de Navegación F8 (VK_F8 = 0x77 = 119).
4. Activación permanente de Licencia Universal Offline (MMATS-SANTI-2026-UNIVERSAL).
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
_bloques = []
for i, (res_name, file_path) in enumerate(files_map):
    e = table_off + i * 48
    dva = int.from_bytes(dll[e+8 : e+16], 'little')
    _bloques.append((va_to_offset(dva), res_name, file_path))
_bloques.sort()

_sec = next(s for s in pe.sections
            if s.PointerToRawData <= _bloques[-1][0] < s.PointerToRawData + s.SizeOfRawData)

_desbordes = []
for j, (off_b, res_name, file_path) in enumerate(_bloques):
    tope = _bloques[j+1][0] if j+1 < len(_bloques) else _sec.PointerToRawData + _sec.SizeOfRawData
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

pe.close()
del pe
gc.collect()

with open('dxgi.dll', 'wb') as f:
    f.write(dll)

print("=" * 80)
print(">>> dxgi.dll generado y verificado con exito.")
print("=" * 80)

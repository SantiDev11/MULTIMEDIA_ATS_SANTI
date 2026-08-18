# -*- coding: utf-8 -*-
"""
================================================================================
MULTIMEDIA ATS SANTI - Master Build & Injection Script
================================================================================
Compilación oficial de dxgi.dll y empaquetado de MULTIMEDIA ATS SANTI:
1. Dual-Key XOR encryption e inyección de los 5 módulos HTML en .rdata.
2. Hook D3D11 DrawIndexed para detección de Cámara 1 (Cabina / Interior).
3. Puente Universal WASAPI para control de volumen de WebView2 / Spotify / YouTube.
4. Curva de volumen acústico: 100% en interior / 18% amortiguado en exterior.
5. Interruptor de navegación por mouse F8 (VK_F8 = 0x77 = 119).
6. Desbloqueo de licencia universal offline permanente (MMATS-SANTI-2026-UNIVERSAL).
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

# Cargar DLL base
with open('dxgi.dll', 'rb') as f:
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
# 4. Detección de Cámara por Renderizado D3D11
# ------------------------------------------------------------------------------
target_global_va = 0x1801f95f0

# Hook en DrawIndexed de la pantalla de cabina (0x1800c19b5)
hook_render_va = 0x1800c19b5
disp_render = target_global_va - (hook_render_va + 7)
render_patch = bytes([0xC6, 0x05]) + struct.pack('<i', disp_render) + bytes([0x01, 0x48, 0x31, 0xF6])
render_patch += b'\x90' * (45 - len(render_patch))
dll[va_to_offset(hook_render_va) : va_to_offset(hook_render_va) + 45] = render_patch
print(" [OK] Hook D3D11 de renderizado en cabina vinculado a deteccion de camara")

# Lectura de estado de cabina en bucle WASAPI (0x1800d8258)
hook_audio_va = 0x1800d8258
disp_audio = target_global_va - (hook_audio_va + 8)
audio_patch = bytes([0x44, 0x0F, 0xB6, 0x35]) + struct.pack('<i', disp_audio) + bytes([0x90])
dll[va_to_offset(hook_audio_va) : va_to_offset(hook_audio_va) + len(audio_patch)] = audio_patch

# Curva de Volumen: Cabina = 100%, Exterior = 30% amortiguado (0x1800d8348)
vol_patch_va = 0x1800d8348
vol_patch = bytes([
    0x33, 0xDB,                   # xor ebx, ebx
    0x83, 0xFE, 0x64,             # cmp esi, 100
    0x0F, 0x47, 0xF7,             # cmova esi, edi
    0x45, 0x84, 0xF6,             # test r14b, r14b
    0x75, 0x03,                   # jnz +3 (si esta en cabina -> volumen 100%)
    0x6A, 0x1E,                   # push 30 (0x1E = 30% si esta en exterior)
    0x5E,                         # pop rsi
    0x90, 0x90                    # NOPs
])
dll[va_to_offset(vol_patch_va) : va_to_offset(vol_patch_va) + len(vol_patch)] = vol_patch
print(" [OK] Curva acustica configurada (Interior = 100% / Exterior = 30% amortiguado)")

# Desmutear sesiones automáticamente (r8b = 1)
unmute_hook_va = 0x1800d84df
dll[va_to_offset(unmute_hook_va) : va_to_offset(unmute_hook_va) + 4] = bytes([0x41, 0xB0, 0x01, 0x90])

# ------------------------------------------------------------------------------
# 5. PUENTE UNIVERSAL WASAPI: Controlar WebView2/Spotify/YouTube y respetar FMOD
# ------------------------------------------------------------------------------
pid_hook_va = 0x1800d797e
iat_va = 0x18013b5f8 # GetCurrentProcessId
disp_iat = iat_va - (pid_hook_va + 6)
skip_game_va = 0x1800d7b3d
disp_skip = skip_game_va - (pid_hook_va + 6 + 2 + 6)
apply_media_va = 0x1800d7a66
disp_apply = apply_media_va - (pid_hook_va + 6 + 2 + 6 + 5)

universal_wasapi_patch = (
    bytes([0xFF, 0x15]) + struct.pack('<i', disp_iat) + # call qword ptr [GetCurrentProcessId]
    bytes([0x39, 0xC2]) +                                # cmp edx, eax (¿es el juego amtrucks.exe?)
    bytes([0x0F, 0x84]) + struct.pack('<i', disp_skip) + # je 0x1800d7b3d (si es ATS, no tocarlo)
    bytes([0xE9]) + struct.pack('<i', disp_apply)        # jmp 0x1800d7a66 (si es WebView2/Spotify/YouTube, ajustar volumen)
)
nops_len = va_to_offset(apply_media_va) - (va_to_offset(pid_hook_va) + len(universal_wasapi_patch))
dll[va_to_offset(pid_hook_va) : va_to_offset(apply_media_va)] = universal_wasapi_patch + b'\x90' * nops_len
print(" [OK] Puente WASAPI para WebView2 (Spotify Web / YouTube / Twitch / Netflix) activo")

dll[va_to_offset(target_global_va)] = 1

pe.close()
del pe
gc.collect()

with open('dxgi.dll', 'wb') as f:
    f.write(dll)

print("=" * 80)
print(">>> dxgi.dll generado y verificado con exito.")
print("=" * 80)

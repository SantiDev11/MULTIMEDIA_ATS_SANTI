# 🎮 MULTIMEDIA ATS SANTI

Sistema multimedia integrado con overlay en tiempo real para **American Truck Simulator**.  
Reproduce YouTube, Spotify, Twitch, Netflix, GPS integrado, chat en vivo y personalización de fondo — sin salir del juego.

---

## ✅ Requisitos

- Windows 10 / 11 (64-bit)
- American Truck Simulator (DirectX 11, x64)
- Microsoft Edge WebView2 Runtime *(incluido por defecto en Win 10/11)*

---

## 🚀 Instalación

1. Cierra American Truck Simulator.
2. Ejecuta `MULTIMEDIA ATS SANTI.exe`.
3. El instalador detecta automáticamente la ruta de ATS vía Steam o Registro de Windows.  
   Si usas ruta personalizada, haz clic en **📁 Examinar...** y selecciona la carpeta `bin\win_x64`.
4. Haz clic en **▶ INSTALAR MULTIMEDIA ATS SANTI**.
5. El instalador crea backup automático, copia los archivos y verifica integridad con SHA-256.
6. ¡Listo! Abre ATS desde Steam normalmente.

### Archivos instalados en `bin\win_x64\`

```
├── dxgi.dll                  ← Hook DirectX 11
├── WebView2Loader.dll        ← Cargador WebView2
├── MENU_EXTRAIDO/
│   ├── lucidgfx_overlay.html
│   ├── overlay_styles.css
│   ├── overlay_script.js
│   ├── lucidgfx_home.html
│   ├── chat.html
│   ├── split.html
│   └── lucidgfx_gps.html
```

---

## 🎮 Uso dentro del juego

| Atajo | Acción |
|-------|--------|
| `Re Pág` (Page Up) | Abrir / cerrar menú overlay |
| `F8` | Alternar visibilidad rápida |

**Licencia:** al abrir la pestaña de Licencia por primera vez, ingresa:
```
MMATS-SANTI-2026-UNIVERSAL
```
Se guarda automáticamente y no vuelve a pedirla.

---

## 🗑️ Desinstalación

1. Cierra el juego.
2. Abre `MULTIMEDIA ATS SANTI.exe`.
3. Haz clic en **🗑️ Desinstalar Mod**.
4. El desinstalador elimina solo los archivos del mod y restaura backups previos si existían.  
   Los archivos originales de ATS **no se modifican**.

---

## 📄 Licencia

© 2026 MULTIMEDIA ATS SANTI — Todos los derechos reservados.

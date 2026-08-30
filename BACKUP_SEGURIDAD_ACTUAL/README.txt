================================================================================
MULTIMEDIA ATS SANTI - MANUAL DE INSTALACIÓN Y USO OFICIAL v2.0
================================================================================
American Truck Simulator (ATS) • DirectX 11 • x64 • Microsoft Edge WebView2
================================================================================

1. DESCRIPCIÓN DEL PROYECTO
--------------------------------------------------------------------------------
MULTIMEDIA ATS SANTI es un sistema multimedia integrado y overlay en tiempo real
para American Truck Simulator. Permite reproducir YouTube, Spotify, Twitch,
Netflix, visualizar mapas GPS integrados, usar Chat en vivo y personalizar el
fondo del sistema dentro del juego sin necesidad de salir al escritorio.

- Archivo Instalador Autónomo: "MULTIMEDIA ATS SANTI.exe"
- Clave de Licencia Offline Universal: MMATS-SANTI-2026-UNIVERSAL
- Idioma: 100% Español


================================================================================
2. CÓMO INSTALAR EL MOD (INSTALACIÓN AUTOMÁTICA)
================================================================================
El instalador se encarga de todo el proceso de forma segura:

PASO 1:
Asegúrate de que American Truck Simulator esté cerrado.

PASO 2:
Ejecuta el archivo:
`MULTIMEDIA ATS SANTI.exe`

PASO 3:
El instalador detectará automáticamente la carpeta de instalación de American
Truck Simulator (a través de Steam o el Registro de Windows).
- Si tienes el juego en una ruta personalizada, haz clic en "📁 Examinar..." y
  selecciona la carpeta de American Truck Simulator o directamente 'bin\win_x64'.

PASO 4:
Haz clic en el botón verde:
"▶ INSTALAR MULTIMEDIA ATS SANTI"

PASO 5:
El instalador creará una copia de seguridad automática de cualquier archivo previo,
copiará 'dxgi.dll', 'WebView2Loader.dll' y toda la carpeta 'MENU_EXTRAIDO',
verificará la integridad de los archivos con hashes SHA-256 y mostrará un mensaje
de confirmación.

PASO 6:
¡Listo! Abre American Truck Simulator como de costumbre desde Steam o tu acceso directo.


================================================================================
3. DÓNDE SE INSTALAN LOS ARCHIVOS
================================================================================
Los archivos se colocan en la carpeta oficial del ejecutable del juego de 64 bits:

Ruta típica de Steam:
C:\Program Files (x86)\Steam\steamapps\common\American Truck Simulator\bin\win_x64\

Estructura desplegada dentro de 'bin\win_x64\':
├── amtrucks.exe                       <-- Ejecutable original del juego (NO SE MODIFICA)
├── dxgi.dll                           <-- Hook DirectX 11 oficial de MULTIMEDIA ATS SANTI (x64)
├── WebView2Loader.dll                 <-- Cargador oficial de Microsoft WebView2 (x64)
├── MULTIMEDIA_ATS_SANTI_INSTALL.log   <-- Registro detallado con rutas y firmas SHA-256
├── MULTIMEDIA_ATS_SANTI_MANIFEST.json <-- Manifiesto de control de versiones e integridad
└── MENU_EXTRAIDO/                     <-- Interfaz web y módulos del sistema
    ├── lucidgfx_overlay.html          <-- Menú principal Overlay SPA
    ├── overlay_styles.css             <-- Estilos visuales Dark Mode & Glassmorphism
    ├── overlay_script.js              <-- Control de sliders, volumen y pestañas
    ├── lucidgfx_home.html             <-- Pantalla multimedia de la tablet en cabina
    ├── home_styles.css                <-- Estilos de la tablet multimedia
    ├── home_script.js                 <-- Scripts de la tablet multimedia
    ├── chat.html                      <-- Módulo de chat / streaming en vivo
    ├── split.html                     <-- Módulo de pantalla dividida (GPS + Video)
    ├── lucidgfx_gps.html              <-- Módulo de navegación GPS
    ├── ANALISIS.txt                   <-- Documentación técnica de extracción
    ├── CAMBIOS_MULTIMEDIAATS.txt      <-- Registro de personalización y licencia
    └── DLL_UPDATE_REPORT.txt          <-- Informe oficial de metadatos PE x64


================================================================================
4. CÓMO USAR EL MOD DENTRO DEL JUEGO
================================================================================
1. Inicia American Truck Simulator.
2. Atajos de teclado por defecto:
   - [Re Pág] (Page Up): Abre / Cierra el Menú Overlay principal.
   - [F8]: Alterna la visibilidad rápida del overlay.
3. Activación de Licencia:
   - Al abrir por primera vez la pestaña de Licencia, introduce la clave universal:
     `MMATS-SANTI-2026-UNIVERSAL`
   - Haz clic en "Activar". Se guardará automáticamente y no volverá a pedirla.
4. Ajustes:
   - Puedes regular el nivel de zoom y volumen mediante los sliders interactivos.
   - Puedes cambiar el fondo subiendo cualquier imagen (JPG, PNG, WEBP).


================================================================================
5. CÓMO DESINSTALAR EL MOD
================================================================================
Si deseas remover el mod en cualquier momento:

1. Asegúrate de que el juego esté cerrado.
2. Abre de nuevo: `MULTIMEDIA ATS SANTI.exe`.
3. Haz clic en el botón rojo: "🗑️ Desinstalar Mod".
4. El desinstalador:
   - Eliminará únicamente los archivos instalados por el mod ('dxgi.dll',
     'WebView2Loader.dll', 'MENU_EXTRAIDO', logs y manifiestos).
   - Restaurará automáticamente cualquier copia de seguridad previa si existía.
   - No modificará ningún archivo original de American Truck Simulator.


================================================================================
6. REQUISITOS DEL SISTEMA Y COMPATIBILIDAD
================================================================================
- Sistema Operativo: Windows 10 (64-bit) o Windows 11 (64-bit).
- Juego: American Truck Simulator (versión x64 con DirectX 11).
- Componente: Microsoft Edge WebView2 Runtime (incluido por defecto en Windows 10/11).
- Arquitectura: x86_64 / AMD64.

================================================================================
MULTIMEDIA ATS SANTI (c) 2026 • Todos los derechos reservados
================================================================================

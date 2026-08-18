# Explicación del Menú GFXMods (LucidGFX v1.1.2) en dxgi.dll

## ¿Por qué las carpetas Imagenes o Recursos no tienen el diseño del menú?

En Windows existen dos formas de crear interfaces en DLLs:

1. **Recursos Tradicionales / Web**: Archivos `.png`, `.ico`, `.html` guardados en la tabla de recursos PE (`.rsrc`).
2. **Código Nativo Direct3D (Dear ImGui)**: La interfaz **NO es un archivo externo ni una imagen**. Es código C++ compilado directamente a lenguaje máquina (x64) que dibuja botones, pestañas, sliders y colores vectorialmente mediante DirectX 11.

El menú **GFXMods** que ves en pantalla pertenece al **segundo tipo**.

---

## 📍 ¿Dónde está cada parte del menú en la carpeta EXTRAIDO?

| Elemento | Archivo en `EXTRAIDO/dxgi/` | Descripción |
|---|---|---|
| **Textos del Menú** | `Strings/strings_ascii.txt` (líneas 19440-19750) | Contiene todas las etiquetas (`Multimídia`, `INICIAR`, `Parado`, `Zoom`, `Instagram`, `Discord`, etc.) |
| **Configuraciones** | `Strings/strings_ascii.txt` (líneas 19650-19690) | Parámetros del archivo `lucidgfx_settings.ini` |
| **Código Máquina Compilado** | `Secciones/_text.bin` | Funciones en ensamblador x64 que ejecutan el bucle de `ImGui::Render()` |
| **Datos Estáticos** | `Secciones/_rdata.bin` | Tablas de funciones, matrices de proyección y shaders DX11 |

---

## 🛠️ Estructura del Código C++ del Menú (Reconstruido)

El menú fue programado originalmente con esta estructura en C++:

```cpp
// Backend: Dear ImGui v1.90.4 + DirectX 11 Overlay
void RenderGFXModsMenu() {
    ImGui::Begin("GFXMods v1.1.2", &overlay_visible);
    
    // Banner de actualización
    ImGui::TextColored(ImVec4(1.0f, 0.8f, 0.2f, 1.0f), "⚠ Nova versão disponível — v2.0.1 - toque para atualizar");
    
    // Pestañas principales
    if (ImGui::BeginTabBar("MainTabs")) {
        if (ImGui::BeginTabItem("Multimídia")) {
            ImGui::Text("COMUNIDADE");
            // Botones Instagram (@ggfxmods) y Discord
            
            ImGui::Text("CONTROLE");
            if (ImGui::Button(multimedia_active ? "PARAR" : "▶ INICIAR")) {
                ToggleMultimedia();
            }
            
            ImGui::Text("STATUS");
            ImGui::Text(multimedia_active ? "Em execução" : "⏸ Parado");
            
            ImGui::Text("ZOOM DO BROWSER");
            ImGui::SliderInt("Zoom", &mm_zoom, 50, 300);
            
            ImGui::Text("VOLUME DA MULTIMÍDIA");
            ImGui::SliderInt("Volume", &mm_volume, 0, 100);
            
            ImGui::EndTabItem();
        }
        
        if (ImGui::BeginTabItem("Config")) {
            // Ajustes FSR, Upscaler, Hotkeys
            ImGui::EndTabItem();
        }
        
        if (ImGui::BeginTabItem("Licença")) {
            // Activación HWID / Key
            ImGui::EndTabItem();
        }
        
        if (ImGui::BeginTabItem("Links")) {
            // Redes sociales
            ImGui::EndTabItem();
        }
        ImGui::EndTabBar();
    }
    ImGui::End();
}
```

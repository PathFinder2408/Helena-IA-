# CONTEXT — Helena (Workspace `C:\Jarvis`)

## Propósito
Asistente personal local de ingeniería de software para Windows 11 con memoria estructurada, 9 skills de desarrollo/automatización, 3 MCP servers, arranque automático, puente de voz con herramientas reales (CUDA RTX 4060 + Ollama/Gemini/`agy`) y avatar flotante HiDPI estilo OOOOO (*Elio*).

## Stack y Entorno
- **Stack objetivo:** JavaScript fullstack, Django, Python (ciudad y rutas configurables en `.env`).
- **Host:** Windows 11 Home 26H2, PowerShell 5.1, Python 3.12.10 (`C:\Jarvis\.venv`), Node v24.16.0, Git 2.52, NVIDIA RTX 4060 Laptop (8 GB VRAM, CUDA 12/13), Antigravity 2.34.
- **Voz / IA / UI:** `faster-whisper` (CUDA `float16`), `edge-tts` (`fr-FR-VivienneMultilingualNeural` #3 default + `es-US-PalomaNeural` #4 alternable por voz con `"cambia de voz"`) + Gemini TTS opcional + fallback SAPI5, `PyQt6`, `google-genai`, Ollama 0.40.16 (`helena` sobre `qwen2.5:7b`).

## Mapa de Archivos
- `AGENTS.md` — Reglas operativas globales de Helena (~390 palabras).
- `CONTEXT.md` — Este mapa vivo del proyecto, decisiones, estado y comandos.
- `CHANGELOG.md` — Historial de cambios (fecha, qué, por qué).
- `.helena/index.json` — Índice estructurado de módulos, exports y fechas.
- `.helena/lessons.md` — Errores corregidos y reglas aprendidas (leer al iniciar).
- `dashboard.html` — Panel visual HUD interactivo (diagnóstico, perfil, checklist, progreso).
- `Encender_Helena.bat` — Lanzador 1 clic: elimina `HELENA_OFF`/`JARVIS_OFF` y arranca Helena.
- `requirements-voice.txt` — Dependencias Python de `.venv` (voz, PyQt6, CUDA).
- `.env.example` / `.gitignore` / `.antigravityignore` — Plantilla de secretos y exclusiones.
- `memory/{context,inbox,TODO,progress}.md` — Perfil personal, notas rápidas, tareas y log histórico.
- `scripts/voice_bridge.py` — Motor de voz v3: activación manos libres por Whisper CUDA (`Helena`/`Elena`/`Oye Helena`/`Despierta Helena`/`Jarvis`, modo 1 frase y 2 pasos), PTT, cerebro híbrido y TTS en RAM.
- `scripts/task_runner.py` — Motor asíncrono de ingeniería sobre proyectos (`project_status`, chequeos en segundo plano, delegación a Antigravity `agy`/IDE + `init_helena_memory`).
- `scripts/voice_tools.py` — 24 herramientas reales de PC e ingeniería (proyectos, Antigravity, chequeos async, carpetas/archivos, multimedia, YouTube/Google, memoria y aprendizaje continuo).
- `Modelfile.helena` — Modelo Ollama personalizado `helena` (sobre `qwen2.5:7b`) con personalidad natural, rutas reales del PC, delegación a Antigravity y reglas anti-alucinación.
- `scripts/voice_profile.py` — Huella biométrica vocal (56-dim) y clasificador wake word ONNX.
- `scripts/train_voice.py` — Entrenador interactivo (~60 s) con tu voz (guarda solo vectores en `memory/voice_profile.pkl`).
- `scripts/context_monitor.py` — Monitor Win32 de ventana activa (`fullscreen`/`meeting`/`focus`/`casual`) para auto-ocultado y modo discreto.
- `scripts/soul_avatar.py` — Avatar flotante HiDPI estilo OOOOO (*Elio*) v2 en PyQt6 (60 FPS, circuitos, física líquida, bandeja del sistema e inteligencia contextual).
- `scripts/start_helena.ps1` — Arranque automático en segundo plano (Ollama serve + `pythonw` voz/avatar; respeta `HELENA_OFF`).
- `scripts/mcp_powershell.mjs` — Servidor MCP stdio para PowerShell con lista blanca y confirmación.
- `scripts/test_mcps.mjs` — Validador stdio de los 3 servidores MCP.
- `.agents/skills/*` — 9 skills: `daily-briefing`, `pc-operator`, `dev-copilot`, `memory-manager`, `git-workflow`, `code-review-qa`, `api-db-inspector`, `automation-builder`, `career-docs-engineer`.

## Decisiones y Razón
- **Carpeta técnica `C:\Jarvis` + identidad visible 100% Helena:** evita recrear `.venv` y romper paths MCP/tarea programada con costo cero.
- **PyQt6 en hilo principal + worker de audio:** elimina `Tcl_AsyncDelete` de Tkinter y habilita anti-aliasing + transparencia alfa real por píxel.
- **Audio 100% en RAM (`sounddevice` + `PyAV` + `io.BytesIO`):** privacidad total; cero archivos `.wav`/`.mp3` en disco salvo `--save-audio`.
- **Cerebro híbrido (`agy` → Gemini API → Ollama RTX 4060) + enrutador instantáneo:** velocidad <0.5 s offline en acciones frecuentes y respaldo local sin costo.
- **`ollama.exe serve` en vez de `ollama app.exe`:** la app GUI falla en sesiones no interactivas; el servidor puro corre estable y detecta la RTX 4060 (6.9 GiB VRAM).

## Convenciones
- Scripts PowerShell con `-Help` y `-DryRun`; scripts Python con `--help` y `--self-test`/`--dry-run`.
- Confirmación obligatoria antes de acciones destructivas, `git push`, deploys o cambios fuera de `C:\Jarvis`.
- Secretos solo en `C:\Jarvis\.env` (ignorado por git) o variables de entorno de usuario.

## Estado
- ✅ Estructura base, reglas, memoria, panel visual (`dashboard.html`) y 9 skills verificadas.
- ✅ MCPs (`filesystem` con `C:\Jarvis` + `proyectos web`, `powershell-safe`, `playwright`) configurados en `~/.gemini/config/mcp_config.json` y validados.
- ✅ Autostart Windows (`Helena-Autostart`, `AtLogOn`, 24/7 segundo plano con auto-reinicio) + `Encender_Helena.bat`.
- ✅ Avatar OOOOO v2 en PyQt6 HiDPI (circuitos, física líquida, bandeja e inteligencia contextual), Whisper `small` en RTX 4060 CUDA (`cuda_dlls=True`), Ollama `helena:latest`, 24 herramientas reales, voz Vivienne/Paloma y **Antigravity CLI (`agy` 1.5.14) instalado y autenticado**.
- ⏳ Completar URLs de GitHub/LinkedIn en `memory/context.md`.

## Deuda Técnica
- Ninguna crítica pendiente (primer commit base `976ee37` realizado y puente autónomo `agy` conectado).

---
name: daily-briefing
description: Genera un resumen diario con hora local, clima actual de la ciudad configurada en .env, pendientes de memory/TODO.md y estado de repositorios git. Usar al iniciar sesión o cuando el usuario pida "briefing", "resumen del día" o "qué hay hoy".
---

# Daily Briefing — Helena

## Procedimiento
1. Ejecutar `powershell -NoProfile -ExecutionPolicy Bypass -File .agents\skills\daily-briefing\scripts\briefing.ps1`.
2. Para ver opciones sin leer el script: añadir `-Help`.
3. Responder con **máximo 10 líneas** totales:
   - Fecha/hora local y clima de la ciudad configurada (`CITY` en `.env`).
   - Estado resumido de repos git (rama y archivos pendientes).
   - **Las 3 prioridades del día** extraídas de `memory/TODO.md`.

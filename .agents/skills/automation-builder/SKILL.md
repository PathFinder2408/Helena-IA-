---
name: automation-builder
description: Diseña y genera automatizaciones idempotentes en PowerShell, Python, Playwright o GitHub Actions con modo dry-run, logging y manejo seguro de secretos. Usar cuando el usuario pida automatizar tareas repetitivas, crear bots, cron jobs o pipelines CI/CD.
---

# Automation Builder — Helena

## Procedimiento
1. Definir en 3 líneas: **disparador** (manual, cron/tarea programada, webhook, evento git), **entradas/salidas** y **riesgos**.
2. Generar plantilla base con:
   `powershell -NoProfile -ExecutionPolicy Bypass -File C:\Jarvis\.agents\skills\automation-builder\scripts\auto_scaffold.ps1 -Name "<nombre>" -Kind ps1|py|gh-action` (`-Help` para opciones).
3. Requisitos obligatorios en toda automatización:
   - **Idempotente** (re-ejecutable sin duplicar ni romper nada).
   - **Flag `-DryRun` / `--dry-run`** para probar antes de ejecutar acciones reales.
   - **Logs** en `C:\Jarvis\logs\` y secretos solo desde `.env` o variables de entorno.
4. **Confirmación obligatoria** antes de: registrar tareas programadas/crons, enviar mensajes/emails externos, operar en cloud/EC2 o ejecutar acciones de escritura masiva.

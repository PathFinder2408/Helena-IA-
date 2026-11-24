---
name: pc-operator
description: Monitorea CPU, RAM, disco, red y procesos pesados en Windows 11, y abre aplicaciones locales de forma segura. Usar cuando el usuario pida estado del PC, abrir una app o diagnosticar rendimiento.
---

# PC Operator — Helena

## Lista blanca (ejecución directa sin confirmar)
- Diagnóstico solo lectura: `powershell -NoProfile -File C:\Jarvis\.agents\skills\pc-operator\scripts\pc_status.ps1` (`-Help` para opciones).
- Abrir apps de usuario comunes: `notepad`, `calc`, `explorer`, `code`, navegador (`msedge`/`chrome`), `C:\Jarvis\dashboard.html`.

## Requiere confirmación explícita (mostrar comando exacto antes)
- Matar procesos (`Stop-Process` / `taskkill`).
- Reiniciar servicios, cambiar red/firewall, borrar archivos o modificar registro/políticas.

---
name: memory-manager
description: Lee memory/context.md al iniciar sesión y guarda notas o datos persistentes en memory/context.md o memory/inbox.md con fecha y sin duplicar. Usar cuando el usuario diga "recuerda que...", "anota...", "guarda esto" o pida consultar su memoria.
---

# Memory Manager — Helena

## Procedimiento
1. **Inicio de sesión:** leer `C:\Jarvis\memory\context.md`.
2. **Guardar nota o dato:** usar `powershell -NoProfile -File C:\Jarvis\.agents\skills\memory-manager\scripts\mem_append.ps1 -Target inbox|context -Text "<texto>"` (`-Help` para opciones).
   - `inbox`: ideas, recordatorios rápidos o tareas sueltas (`memory/inbox.md`).
   - `context`: datos duraderos de perfil, rutas de repos, stack o preferencias (`memory/context.md`).
3. **Reglas:** siempre incluir fecha `YYYY-MM-DD`, nunca duplicar entradas idénticas, nunca borrar contenido previo sin confirmación.

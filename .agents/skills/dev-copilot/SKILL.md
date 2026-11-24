---
name: dev-copilot
description: Inspecciona proyectos locales, levanta entornos de desarrollo (venv, runserver, npm/docker), ejecuta tests y revisa logs. Usar cuando el usuario pida arrancar un proyecto, correr pruebas, revisar errores o preparar un deploy.
---

# Dev Copilot — Helena

## Procedimiento
1. Inspeccionar proyecto con `powershell -NoProfile -File C:\Jarvis\.agents\skills\dev-copilot\scripts\dev_check.ps1 -RepoPath "<ruta>"` (`-Help` para opciones).
2. Acciones locales seguras (ejecución directa): activar `.venv`, `pytest`, `npm test`, `python manage.py check`, leer logs locales, `git status/diff/log`.
3. **Confirmación obligatoria** (mostrar comando exacto antes): `git push`, migraciones destructivas, `docker system prune`, deploys y **cualquier comando en EC2 / SSH / servidores remotos**.

---
name: git-workflow
description: Audita cambios git, redacta commits con Conventional Commits, prepara descripciones de Pull Requests y detecta secretos o archivos grandes antes de subir código. Usar cuando el usuario pida preparar un commit, PR, revisar rama o limpiar historial git.
---

# Git Workflow — Helena

## Procedimiento
1. Ejecutar `powershell -NoProfile -ExecutionPolicy Bypass -File C:\Jarvis\.agents\skills\git-workflow\scripts\git_audit.ps1 -RepoPath "<ruta>"` (`-Help` para opciones).
2. Si detecta posibles secretos (`.env`, tokens, llaves privadas) en cambios pendientes, **detener y alertar** antes de commitear.
3. Proponer mensaje en formato **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`) y, si aplica, resumen de PR (Qué cambia / Por qué / Cómo probar).
4. **Confirmación obligatoria** (mostrar comando exacto antes): `git push`, `git push --force`, `git reset --hard`, `git rebase`, borrar ramas o tags.

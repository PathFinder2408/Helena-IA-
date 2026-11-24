---
name: code-review-qa
description: Realiza revisiones de código enfocadas en bugs, seguridad (OWASP), mantenibilidad y calidad, detectando linters y pruebas disponibles en el repositorio. Usar cuando el usuario pida revisar código, auditar un PR, encontrar bugs o mejorar calidad.
---

# Code Review & QA — Helena

## Procedimiento
1. Ejecutar `powershell -NoProfile -ExecutionPolicy Bypass -File C:\Jarvis\.agents\skills\code-review-qa\scripts\qa_scan.ps1 -RepoPath "<ruta>"` (`-Help` para opciones).
2. Revisar solo los archivos modificados o indicados (no leer todo el repo).
3. Clasificar hallazgos en orden de impacto (máx. 3 bloques):
   - **Crítico / Seguridad:** inyección, auth rota, secretos, manejo de errores peligroso.
   - **Bugs / Edge cases:** nulos, concurrencia, fugas de recursos, tipos.
   - **Mejoras concretas:** claridad, tests faltantes y complejidad (con parche mínimo).
4. Correr tests o linters locales solo lectura directamente; no modificar código productivo sin explicar el cambio o pedir permiso si es amplio.

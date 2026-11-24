---
name: api-db-inspector
description: Prueba endpoints HTTP/REST/GraphQL midiendo latencia y respuesta JSON, e inspecciona puertos locales de desarrollo y servicios de bases de datos. Usar cuando el usuario pida probar una API, revisar puertos ocupados o depurar conectividad local.
---

# API & DB Inspector — Helena

## Procedimiento
1. Para probar un endpoint GET o listar puertos locales de desarrollo:
   `powershell -NoProfile -ExecutionPolicy Bypass -File C:\Jarvis\.agents\skills\api-db-inspector\scripts\api_probe.ps1 [-Url "<url>"] [-Ports]` (`-Help` para opciones).
2. **Solo lectura directa:** peticiones `GET`/`HEAD` y consultas `SELECT` locales o inspección de puertos.
3. **Confirmación obligatoria** (mostrar comando/request exacto antes): peticiones `POST`/`PUT`/`PATCH`/`DELETE` contra entornos staging/producción, migraciones o queries SQL de escritura (`INSERT`/`UPDATE`/`DELETE`/`DROP`).
4. Nunca imprimir tokens `Authorization` ni cadenas de conexión con contraseñas en texto plano.

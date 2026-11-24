#!/usr/bin/env node
// Servidor MCP Stdio mínimo para PowerShell con lista blanca y confirmación para comandos riesgosos.
import { execFile } from "node:child_process";
import readline from "node:readline";

const SAFE_PREFIXES = [
  /^Get-Date\b/i,
  /^Get-Location\b/i,
  /^Get-ChildItem\b/i,
  /^Get-Process\b/i,
  /^Get-Service\b/i,
  /^git\s+(status|log|branch|diff)\b/i,
  /^(python|node|git)\s+--version\b/i,
  /^powershell\s+-NoProfile\s+(-ExecutionPolicy\s+Bypass\s+)?-File\s+["']?C:\\Jarvis\\\.agents\\skills\\/i
];

const DANGEROUS = /(Remove-Item|\brm\b|\bdel\b|Stop-Process|taskkill|git\s+push|\bssh\b|Set-ExecutionPolicy|Format-|Invoke-Expression|\biex\b|;\s*|&&|\|\|)/i;

function isSafe(cmd) {
  const c = cmd.trim();
  if (DANGEROUS.test(c)) return false;
  return SAFE_PREFIXES.some((rx) => rx.test(c));
}

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function runPs(command) {
  return new Promise((resolve) => {
    execFile(
      "powershell.exe",
      ["-NoProfile", "-Command", command],
      { timeout: 15000, maxBuffer: 512 * 1024 },
      (err, stdout, stderr) => {
        const out = [stdout, stderr].filter(Boolean).join("\n").trim();
        resolve({ ok: !err, output: out || (err ? err.message : "(sin salida)") });
      }
    );
  });
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on("line", async (line) => {
  if (!line.trim()) return;
  let req;
  try { req = JSON.parse(line); } catch { return; }
  const { id, method, params } = req;

  if (method === "initialize") {
    send({
      jsonrpc: "2.0", id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "jarvis-powershell-safe", version: "1.0.0" }
      }
    });
  } else if (method === "notifications/initialized") {
    return;
  } else if (method === "tools/list") {
    send({
      jsonrpc: "2.0", id,
      result: {
        tools: [{
          name: "run_powershell",
          description: "Ejecuta un comando PowerShell en Windows. Comandos fuera de la lista blanca segura requieren confirmed=true tras aprobación explícita del usuario.",
          inputSchema: {
            type: "object",
            properties: {
              command: { type: "string", description: "Comando PowerShell a ejecutar" },
              confirmed: { type: "boolean", description: "Debe ser true solo tras confirmación explícita del usuario para comandos riesgosos", default: false }
            },
            required: ["command"]
          }
        }]
      }
    });
  } else if (method === "tools/call") {
    const tool = params?.name;
    const args = params?.arguments || {};
    if (tool !== "run_powershell") {
      send({ jsonrpc: "2.0", id, error: { code: -32601, message: "Tool desconocida" } });
      return;
    }
    const cmd = String(args.command || "").trim();
    if (!cmd) {
      send({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text: "Error: comando vacío." }], isError: true } });
      return;
    }
    if (!isSafe(cmd) && args.confirmed !== true) {
      send({
        jsonrpc: "2.0", id,
        result: {
          content: [{ type: "text", text: `CONFIRMACIÓN REQUERIDA: El comando no está en la lista blanca segura. Muestra al usuario el comando exacto y pide su aprobación antes de reintentar con confirmed=true:\n${cmd}` }],
          isError: true
        }
      });
      return;
    }
    const res = await runPs(cmd);
    send({
      jsonrpc: "2.0", id,
      result: { content: [{ type: "text", text: res.output }], isError: !res.ok }
    });
  } else if (id !== undefined) {
    send({ jsonrpc: "2.0", id, error: { code: -32601, message: `Método no soportado: ${method}` } });
  }
});

// Valida los 3 servidores MCP con handshake initialize + tools/list (+ llamada inocua en powershell-safe)
import { spawn } from "node:child_process";

const servers = [
  {
    name: "powershell-safe",
    cmd: "node",
    args: ["C:\\Jarvis\\scripts\\mcp_powershell.mjs"],
    extraCall: { name: "run_powershell", arguments: { command: "Get-Date -Format yyyy-MM-dd" } }
  },
  {
    name: "filesystem",
    cmd: "cmd.exe",
    args: ["/c", "npx", "-y", "@modelcontextprotocol/server-filesystem", "C:\\Jarvis"]
  },
  {
    name: "playwright",
    cmd: "cmd.exe",
    args: ["/c", "npx", "-y", "@playwright/mcp@latest"]
  }
];

function testServer(s) {
  return new Promise((resolve) => {
    const child = spawn(s.cmd, s.args, { stdio: ["pipe", "pipe", "pipe"], shell: false });
    let buf = "";
    let initOk = false;
    let tools = [];
    let callResult = null;
    let errLog = "";

    const timer = setTimeout(() => {
      child.kill();
      resolve({ name: s.name, ok: false, reason: "timeout", err: errLog.slice(0, 200) });
    }, 25000);

    child.stderr.on("data", (d) => { errLog += d.toString(); });
    child.stdout.on("data", (d) => {
      buf += d.toString();
      const lines = buf.split(/\r?\n/);
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim().startsWith("{")) continue;
        try {
          const msg = JSON.parse(line);
          if (msg.id === 1 && msg.result) {
            initOk = true;
            child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");
            child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} }) + "\n");
          } else if (msg.id === 2 && msg.result) {
            tools = (msg.result.tools || []).map((t) => t.name);
            if (s.extraCall) {
              child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 3, method: "tools/call", params: s.extraCall }) + "\n");
            } else {
              clearTimeout(timer);
              child.kill();
              resolve({ name: s.name, ok: initOk && tools.length > 0, toolsCount: tools.length, sample: tools.slice(0, 3) });
            }
          } else if (msg.id === 3 && msg.result) {
            callResult = msg.result.content?.[0]?.text?.trim();
            clearTimeout(timer);
            child.kill();
            resolve({ name: s.name, ok: initOk && tools.length > 0 && !msg.result.isError, toolsCount: tools.length, callResult });
          }
        } catch {}
      }
    });

    child.on("error", (e) => {
      clearTimeout(timer);
      resolve({ name: s.name, ok: false, reason: e.message });
    });

    child.stdin.write(JSON.stringify({
      jsonrpc: "2.0", id: 1, method: "initialize",
      params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "jarvis-test", version: "1.0" } }
    }) + "\n");
  });
}

for (const s of servers) {
  const res = await testServer(s);
  console.log(JSON.stringify(res));
}

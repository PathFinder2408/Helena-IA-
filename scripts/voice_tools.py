#!/usr/bin/env python3
"""
Helena — Herramientas reales ejecutables desde la voz (Function Calling + Enrutador Instantáneo).
Seguridad: lista blanca estricta; CERO acciones destructivas (borrar, matar procesos, push, deploy, SSH).
"""
from __future__ import annotations

import ctypes
from datetime import datetime
from difflib import get_close_matches
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata
from urllib.parse import quote_plus
import webbrowser

ROOT = Path(r"C:\Jarvis")
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import task_runner as trunner

SKILLS = ROOT / ".agents" / "skills"
TODO_MD = ROOT / "memory" / "TODO.md"
TRAINING_MD = ROOT / "memory" / "helena_training.md"


def _real_known_dirs() -> dict[str, Path]:
    home = Path.home()
    desktop = home / "OneDrive" / "Desktop"
    if not desktop.exists():
        desktop = home / "Desktop"
    docs = home / "OneDrive" / "Documents"
    if not docs.exists():
        docs = home / "Documents"
    env_proj = os.getenv("HELENA_PROJECTS_DIR", "").strip()
    if env_proj and Path(env_proj).exists():
        projects = Path(env_proj)
    elif (home / "Projects").exists():
        projects = home / "Projects"
    else:
        projects = desktop
    return {
        "escritorio": desktop,
        "desktop": desktop,
        "documentos": docs,
        "documents": docs,
        "descargas": home / "Downloads",
        "downloads": home / "Downloads",
        "proyectos": projects,
        "helena": ROOT,
        "usuario": home,
    }

# Lista blanca estricta de aplicaciones / enlaces seguros
SAFE_APPS: dict[str, tuple[str, list[str]]] = {
    "dashboard": ("url", [str(ROOT / "dashboard.html")]),
    "panel": ("url", [str(ROOT / "dashboard.html")]),
    "calculadora": ("exe", ["calc.exe"]),
    "calc": ("exe", ["calc.exe"]),
    "notas": ("exe", ["notepad.exe"]),
    "bloc de notas": ("exe", ["notepad.exe"]),
    "explorador": ("exe", ["explorer.exe", str(ROOT)]),
    "archivos": ("exe", ["explorer.exe", str(ROOT)]),
    "vscode": ("cmd", ["code"]),
    "visual studio code": ("cmd", ["code"]),
    "code": ("cmd", ["code"]),
    "terminal": ("exe", ["powershell.exe"]),
    "powershell": ("exe", ["powershell.exe"]),
    "navegador": ("url", ["https://www.google.com"]),
    "chrome": ("url", ["https://www.google.com"]),
    "edge": ("url", ["https://www.google.com"]),
    "youtube": ("url", ["https://www.youtube.com"]),
    "spotify": ("url", ["https://open.spotify.com"]),
    "steam": ("url", ["steam://open/main"]),
    "whatsapp": ("url", ["https://web.whatsapp.com"]),
    "gmail": ("url", ["https://mail.google.com"]),
    "github": ("url", ["https://github.com"]),
    "linkedin": ("url", ["https://www.linkedin.com"]),
}

SAFE_WEB_DOMAINS = (
    "youtube.com", "www.youtube.com", "youtu.be", "music.youtube.com",
    "github.com", "www.github.com", "linkedin.com", "www.linkedin.com",
    "google.com", "www.google.com", "stackoverflow.com",
    "docs.python.org", "docs.djangoproject.com", "developer.mozilla.org",
    "open.spotify.com", "localhost", "127.0.0.1",
)


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s\.\-:/_]", " ", clean).strip()


def _run_ps_script(rel_path: str, extra_args: list[str] | None = None, timeout: int = 12) -> str:
    script = SKILLS / rel_path
    if not script.exists():
        return f"Script no encontrado: {script}"
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    if extra_args:
        cmd.extend(extra_args)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return out[:900] if out else "Ejecutado sin salida."
    except Exception as e:
        return f"Error ejecutando {script.name}: {e}"


# ---- Funciones públicas (usadas por Gemini Function Calling, Ollama Tools y enrutador instantáneo) ----

def daily_briefing() -> str:
    """Obtiene hora actual, clima configurado en .env, pendientes y estado git de repositorios."""
    return _run_ps_script(r"daily-briefing\scripts\briefing.ps1")


def pc_status() -> str:
    """Obtiene uso de CPU, memoria RAM, espacio en disco y los procesos más pesados del PC."""
    return _run_ps_script(r"pc-operator\scripts\pc_status.ps1", ["-Top", "3"])


def remember_note(text: str, target: str = "inbox") -> str:
    """Guarda una nota rápida en memory/inbox.md (target='inbox') o un dato permanente en memory/context.md (target='context')."""
    tgt = "context" if str(target).lower().strip() == "context" else "inbox"
    clean = str(text).strip()
    if not clean:
        return "No recibí texto para guardar."
    return _run_ps_script(r"memory-manager\scripts\mem_append.ps1", ["-Target", tgt, "-Text", clean])


def list_todos() -> str:
    """Lista las tareas pendientes actuales en memory/TODO.md."""
    if not TODO_MD.exists():
        return "No existe memory/TODO.md."
    lines = [ln.strip() for ln in TODO_MD.read_text(encoding="utf-8").splitlines() if re.match(r"^\s*-\s*\[\s*\]", ln)]
    if not lines:
        return "No tienes tareas pendientes en TODO.md."
    top = [re.sub(r"^\s*-\s*\[\s*\]\s*", "", ln) for ln in lines[:5]]
    return f"Tienes {len(lines)} pendientes. Primeros: " + "; ".join(top) + "."


def add_todo(task: str) -> str:
    """Agrega una nueva tarea pendiente al archivo memory/TODO.md sin borrar las existentes."""
    clean = str(task).strip()
    if not clean:
        return "No indicaste el texto de la tarea."
    existing = TODO_MD.read_text(encoding="utf-8") if TODO_MD.exists() else "# TODO — Helena\n"
    if clean.lower() in existing.lower():
        return "Esa tarea ya estaba en tu lista."
    with TODO_MD.open("a", encoding="utf-8") as f:
        f.write(f"- [ ] {clean}\n")
    return f"Agregué a tus pendientes: {clean}."


def git_audit(repo_path: str = r"C:\Jarvis") -> str:
    """Audita rama actual, cambios pendientes y escanea posibles secretos en un repositorio git local."""
    p = str(repo_path or ROOT).strip()
    return _run_ps_script(r"git-workflow\scripts\git_audit.ps1", ["-RepoPath", p])


def check_ports() -> str:
    """Lista los puertos locales de desarrollo activos (3000, 5173, 5432, 6379, 8000, 8080, etc.)."""
    return _run_ps_script(r"api-db-inspector\scripts\api_probe.ps1", ["-Ports"])


def probe_api(url: str) -> str:
    """Prueba un endpoint HTTP GET midiendo código de estado y latencia en milisegundos."""
    u = str(url).strip()
    if not re.match(r"^https?://", u, re.I):
        return "URL inválida: debe empezar con http:// o https://"
    return _run_ps_script(r"api-db-inspector\scripts\api_probe.ps1", ["-Url", u])


def play_youtube(query: str = "musica para programar") -> str:
    """Busca y reproduce directamente un video en YouTube en el navegador del usuario."""
    q = str(query or "musica para programar").strip()
    search_url = f"https://www.youtube.com/results?search_query={quote_plus(q)}"
    target_url = search_url
    try:
        import requests
        r = requests.get(
            search_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=5,
        )
        m = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
        if m:
            target_url = f"https://www.youtube.com/watch?v={m.group(1)}"
    except Exception:
        pass
    webbrowser.open(target_url)
    return f"Abriendo en YouTube: {q}."


def web_search(query: str) -> str:
    """Abre una búsqueda en Google en el navegador por defecto."""
    q = str(query or "").strip()
    if not q:
        return "No indicaste qué buscar."
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(q)}")
    return f"Buscando en Google: {q}."


def open_app(app_name: str) -> str:
    """Abre una aplicación, URL confiable o sitio de la lista blanca segura (youtube, spotify, dashboard, vscode, navegador, github, linkedin, calculadora, explorador, terminal, notas)."""
    raw = str(app_name or "").strip()
    if re.match(r"^https?://", raw, re.I):
        from urllib.parse import urlparse
        host = (urlparse(raw).hostname or "").lower()
        if any(host == d or host.endswith("." + d) for d in SAFE_WEB_DOMAINS):
            webbrowser.open(raw)
            return f"Abrí {host} en tu navegador."
        return f"Dominio no permitido por seguridad: {host}."

    key = _norm(raw)
    matched = None
    for k, val in SAFE_APPS.items():
        if k in key or key in k:
            matched = (k, val)
            break
    if not matched:
        return f"'{app_name}' no está en la lista blanca. Permitidas: youtube, spotify, dashboard, vscode, navegador, github, linkedin, calculadora, explorador, terminal, notas."
    name, (kind, args) = matched
    try:
        if kind == "url":
            webbrowser.open(args[0])
        elif kind == "cmd":
            subprocess.Popen(["cmd.exe", "/c", "start", "", *args])
        else:
            subprocess.Popen(args)
        return f"Abrí {name}."
    except Exception as e:
        return f"No pude abrir {name}: {e}"


def create_automation(name: str, kind: str = "py") -> str:
    """Crea una plantilla de automatización idempotente con --dry-run y logging (kind: 'py', 'ps1' o 'gh-action')."""
    k = kind if kind in ("py", "ps1", "gh-action") else "py"
    return _run_ps_script(r"automation-builder\scripts\auto_scaffold.ps1", ["-Name", name, "-Kind", k])


def _resolve_base_dir(location: str) -> Path:
    dirs = _real_known_dirs()
    loc = _norm(location or "escritorio")
    for k, p in dirs.items():
        if k in loc:
            return p
    # Si pasaron una ruta absoluta dentro del perfil de usuario o C:\Jarvis
    raw = Path(str(location).strip())
    if raw.is_absolute() and (str(raw).lower().startswith(str(Path.home()).lower()) or str(raw).lower().startswith(str(ROOT).lower())):
        return raw
    return dirs["escritorio"]


def _sanitize_name(name: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*]+', "", str(name or "").strip()).strip(". ")
    return clean[:80]


def create_folder(name: str, location: str = "escritorio", open_after: bool = True) -> str:
    """Crea una carpeta real en el PC (escritorio, proyectos, documentos, descargas o ruta de usuario) y la abre en el Explorador."""
    folder_name = _sanitize_name(name)
    if not folder_name:
        return "No entendí el nombre de la carpeta que quieres crear."
    base = _resolve_base_dir(location)
    target = base / folder_name
    try:
        existed = target.exists()
        target.mkdir(parents=True, exist_ok=True)
        if open_after:
            subprocess.Popen(["explorer.exe", str(target)])
        if existed:
            return f"La carpeta {folder_name} ya existía en {base.name}, te la acabo de abrir."
        return f"Listo, creé la carpeta {folder_name} en {base.name} y la abrí en pantalla."
    except Exception as e:
        return f"No pude crear la carpeta {folder_name}: {e}"


def open_folder(name_or_path: str) -> str:
    """Abre en el Explorador de Windows una carpeta real por nombre aproximado o ubicación (escritorio, proyectos, descargas, o una carpeta específica)."""
    raw = str(name_or_path or "").strip()
    dirs = _real_known_dirs()
    norm = _norm(raw)

    # 1) Ubicación conocida exacta
    for k, p in dirs.items():
        if norm == k or norm == f"el {k}" or norm == f"la {k}":
            subprocess.Popen(["explorer.exe", str(p)])
            return f"Abrí {k}."

    # 2) Ruta absoluta existente
    cand = Path(raw)
    if cand.is_absolute() and cand.exists():
        subprocess.Popen(["explorer.exe", str(cand)])
        return f"Abrí la carpeta {cand.name}."

    # 3) Buscar por nombre (exacto o aproximado) en Escritorio, proyectos web, Documentos y Descargas
    search_roots = [dirs["escritorio"], dirs["proyectos"], dirs["documentos"], dirs["descargas"], ROOT]
    found_map: dict[str, Path] = {}
    for sr in search_roots:
        if sr.exists():
            try:
                for item in sr.iterdir():
                    if item.is_dir():
                        found_map[_norm(item.name)] = item
            except Exception:
                pass

    for k, p in found_map.items():
        if norm and (norm in k or k in norm):
            subprocess.Popen(["explorer.exe", str(p)])
            return f"Abrí la carpeta {p.name}."

    matches = get_close_matches(norm, list(found_map.keys()), n=1, cutoff=0.55)
    if matches:
        p = found_map[matches[0]]
        subprocess.Popen(["explorer.exe", str(p)])
        return f"Abrí la carpeta {p.name}."

    return f"No encontré ninguna carpeta llamada {raw} en tu Escritorio ni en proyectos."


def list_projects() -> str:
    """Lista las carpetas de proyectos disponibles en tu carpeta proyectos web y Escritorio."""
    dirs = _real_known_dirs()
    projs = []
    if dirs["proyectos"].exists():
        projs = [p.name for p in sorted(dirs["proyectos"].iterdir()) if p.is_dir()]
    if not projs:
        return "No encontré subcarpetas en tu carpeta de proyectos."
    return "Tus proyectos actuales son: " + ", ".join(projs[:8]) + "."


def open_project(name: str, editor: str = "vscode") -> str:
    """Busca uno de tus proyectos locales por nombre aproximado y lo abre en VS Code, Antigravity o el Explorador."""
    dirs = _real_known_dirs()
    norm = _norm(name)
    candidates: dict[str, Path] = {}
    for root in (dirs["proyectos"], dirs["escritorio"]):
        if root.exists():
            for item in root.iterdir():
                if item.is_dir():
                    candidates[_norm(item.name)] = item

    target = None
    for k, p in candidates.items():
        if norm and (norm in k or k in norm):
            target = p
            break
    if target is None:
        m = get_close_matches(norm, list(candidates.keys()), n=1, cutoff=0.48)
        if m:
            target = candidates[m[0]]
    if target is None:
        return f"No encontré el proyecto {name}. " + list_projects()

    ed = _norm(editor)
    try:
        if "explor" in ed or "carpeta" in ed:
            subprocess.Popen(["explorer.exe", str(target)])
            return f"Abrí el proyecto {target.name} en el Explorador."
        if "anti" in ed:
            ag = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity" / "Antigravity.exe"
            if ag.exists():
                subprocess.Popen([str(ag), str(target)])
                return f"Abrí {target.name} en Antigravity."
        subprocess.Popen(["cmd.exe", "/c", "start", "", "code", str(target)])
        return f"Abrí el proyecto {target.name} en Visual Studio Code."
    except Exception as e:
        return f"No pude abrir {target.name}: {e}"


def create_file(filename: str, content: str = "", location: str = "escritorio") -> str:
    """Crea un archivo de texto o código en una carpeta segura del usuario sin sobrescribir archivos existentes."""
    safe = _sanitize_name(filename)
    if not safe:
        return "No indicaste el nombre del archivo."
    if "." not in safe:
        safe += ".txt"
    base = _resolve_base_dir(location)
    base.mkdir(parents=True, exist_ok=True)
    target = base / safe
    if target.exists():
        return f"El archivo {safe} ya existe en {base.name}; no lo sobrescribí por seguridad."
    target.write_text(str(content or ""), encoding="utf-8")
    return f"Listo, creé {safe} en {base.name}."


def media_control(action: str) -> str:
    """Controla multimedia y ventana activa en Windows: pausar, reproducir, siguiente, anterior, subir_volumen, bajar_volumen, silenciar o cerrar_pestana."""
    act = _norm(action)
    u32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002

    def tap(vk: int, times: int = 1) -> None:
        for _ in range(times):
            u32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.02)
            u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)

    if any(w in act for w in ("pausa", "play", "reproduc", "deten")):
        tap(0xB3)  # VK_MEDIA_PLAY_PAUSE
        return "Listo, pausé o reanudé la reproducción."
    if any(w in act for w in ("siguien", "adelant", "next")):
        tap(0xB0)  # VK_MEDIA_NEXT_TRACK
        return "Pasé a la siguiente pista."
    if any(w in act for w in ("anteri", "atras", "prev")):
        tap(0xB1)  # VK_MEDIA_PREV_TRACK
        return "Volví a la pista anterior."
    if "sub" in act and "vol" in act:
        tap(0xAF, 5)  # VK_VOLUME_UP
        return "Subí el volumen."
    if "baj" in act and "vol" in act:
        tap(0xAE, 5)  # VK_VOLUME_DOWN
        return "Bajé el volumen."
    if any(w in act for w in ("silenc", "mute", "calla")):
        tap(0xAD)  # VK_VOLUME_MUTE
        return "Cambié el silencio del sistema."
    if "pestana" in act or "pestaña" in act or "video" in act or "cerrar" in act:
        # Ctrl+W seguro para cerrar la pestaña activa del navegador
        u32.keybd_event(0x11, 0, 0, 0)  # CTRL
        u32.keybd_event(0x57, 0, 0, 0)  # W
        time.sleep(0.02)
        u32.keybd_event(0x57, 0, KEYEVENTF_KEYUP, 0)
        u32.keybd_event(0x11, 0, KEYEVENTF_KEYUP, 0)
        return "Cerré la pestaña activa."
    return "Acciones multimedia disponibles: pausar, siguiente, anterior, subir volumen, bajar volumen, silenciar o cerrar pestaña."


def teach_helena(rule: str) -> str:
    """Guarda una regla, preferencia o conocimiento nuevo en memory/helena_training.md para que Helena lo aplique siempre."""
    clean = str(rule or "").strip()
    if len(clean) < 4:
        return "Dime con más detalle qué quieres que aprenda."
    TRAINING_MD.parent.mkdir(parents=True, exist_ok=True)
    if not TRAINING_MD.exists():
        TRAINING_MD.write_text("# Entrenamiento y Preferencias de Helena\n\n", encoding="utf-8")
    existing = TRAINING_MD.read_text(encoding="utf-8")
    if clean.lower() in existing.lower():
        return "Eso ya lo tenía aprendido."
    with TRAINING_MD.open("a", encoding="utf-8") as f:
        f.write(f"- **{datetime.now().strftime('%Y-%m-%d')}:** {clean}\n")
    return f"Aprendido y guardado: {clean}."


def project_status(project: str) -> str:
    """Inspecciona stack (Django/Node/Python), rama git, cambios sin commit y memoria CONTEXT.md de un proyecto local."""
    return trunner.get_project_status(project)


def run_project_checks(project: str) -> str:
    """Ejecuta chequeos seguros (Django check, pytest, tsc, git status) en segundo plano y avisa al terminar."""
    return trunner.TASK_MANAGER.run_checks_async(project)


def delegate_to_antigravity(project: str, task: str) -> str:
    """Delega una tarea compleja de desarrollo a Antigravity (vía agy CLI en segundo plano o abriendo Antigravity IDE con el prompt en portapapeles)."""
    return trunner.TASK_MANAGER.delegate_to_antigravity(project, task)


def task_status() -> str:
    """Reporta el estado de las tareas de ingeniería ejecutadas o delegadas en segundo plano."""
    return trunner.TASK_MANAGER.list_tasks()


def init_helena_in_project(project: str) -> str:
    """Inicializa el protocolo de memoria Helena (CONTEXT.md, .helena/index.json, CHANGELOG.md, lessons.md) en un proyecto sin sobrescribir archivos."""
    return trunner.init_helena_memory(project)


# Mapa ejecutable para Ollama y dispatcher genérico
TOOL_REGISTRY = {
    "daily_briefing": daily_briefing,
    "pc_status": pc_status,
    "remember_note": remember_note,
    "list_todos": list_todos,
    "add_todo": add_todo,
    "git_audit": git_audit,
    "check_ports": check_ports,
    "probe_api": probe_api,
    "play_youtube": play_youtube,
    "web_search": web_search,
    "open_app": open_app,
    "create_automation": create_automation,
    "create_folder": create_folder,
    "open_folder": open_folder,
    "list_projects": list_projects,
    "open_project": open_project,
    "create_file": create_file,
    "media_control": media_control,
    "teach_helena": teach_helena,
    "project_status": project_status,
    "run_project_checks": run_project_checks,
    "delegate_to_antigravity": delegate_to_antigravity,
    "task_status": task_status,
    "init_helena_in_project": init_helena_in_project,
}

# Lista directa de funciones Python para Gemini SDK (auto function calling)
GEMINI_TOOL_FUNCS = list(TOOL_REGISTRY.values())

# Esquema JSON para Ollama /api/chat (tool calling nativo en qwen2.5)
OLLAMA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "daily_briefing",
            "description": "Obtiene hora, clima actual configurado en .env, pendientes y estado git.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pc_status",
            "description": "Mide CPU, memoria RAM, espacio en disco y procesos más pesados del PC.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_note",
            "description": "Guarda una nota rápida en inbox o un dato persistente en context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Texto a recordar o anotar"},
                    "target": {"type": "string", "enum": ["inbox", "context"], "description": "inbox para notas rápidas, context para perfil permanente"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "Lee y lista las tareas pendientes del usuario en TODO.md.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": "Agrega una nueva tarea pendiente a TODO.md.",
            "parameters": {
                "type": "object",
                "properties": {"task": {"type": "string", "description": "Descripción de la tarea"}},
                "required": ["task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_audit",
            "description": "Audita rama git, archivos modificados y escanea secretos.",
            "parameters": {
                "type": "object",
                "properties": {"repo_path": {"type": "string", "description": "Ruta del repositorio (default C:\\Jarvis)"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_ports",
            "description": "Lista puertos locales de desarrollo activos (3000, 5173, 5432, 8000, 8080).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_api",
            "description": "Prueba un endpoint HTTP GET midiendo estado y latencia.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL completa http:// o https://"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play_youtube",
            "description": "Busca y abre/reproduce un video o música en YouTube en el navegador del usuario.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Qué buscar o reproducir en YouTube (ej. 'musica lofi para programar')"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Abre una búsqueda en Google en el navegador.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Consulta a buscar en Google"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Abre una app, URL segura o sitio: youtube, spotify, dashboard, vscode, navegador, github, linkedin, calculadora, explorador, terminal, notas.",
            "parameters": {
                "type": "object",
                "properties": {"app_name": {"type": "string", "description": "Nombre de la app o sitio"}},
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_automation",
            "description": "Genera una plantilla de automatización idempotente (py, ps1 o gh-action).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre corto de la automatización"},
                    "kind": {"type": "string", "enum": ["py", "ps1", "gh-action"]},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Crea una carpeta REAL en el PC (escritorio, proyectos, documentos o descargas) y la abre en el Explorador.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre exacto de la carpeta a crear"},
                    "location": {"type": "string", "description": "escritorio, proyectos, documentos o descargas (default: escritorio)"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder",
            "description": "Abre una carpeta real del PC en el Explorador de Windows por nombre o ubicación.",
            "parameters": {
                "type": "object",
                "properties": {"name_or_path": {"type": "string", "description": "Nombre de la carpeta (ej. 'ejemplo 1', 'escritorio', 'descargas', 'proyectos')"}},
                "required": ["name_or_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "Lista los proyectos de código reales del usuario en su carpeta de proyectos.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_project",
            "description": "Abre uno de los proyectos locales del usuario en VS Code, Antigravity o Explorador.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre aproximado del proyecto local"},
                    "editor": {"type": "string", "enum": ["vscode", "antigravity", "explorador"]},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Crea un archivo de texto o código real en el Escritorio, proyectos o documentos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nombre del archivo (ej. 'notas.md', 'app.py')"},
                    "content": {"type": "string", "description": "Contenido inicial opcional"},
                    "location": {"type": "string", "description": "escritorio, proyectos o documentos"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": "Controla reproducción y volumen del PC: pausar, siguiente, anterior, subir_volumen, bajar_volumen, silenciar o cerrar_pestana.",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string", "description": "Acción multimedia o cerrar_pestana"}},
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "teach_helena",
            "description": "Guarda una regla o preferencia nueva del usuario para entrenar y mejorar a Helena de forma permanente.",
            "parameters": {
                "type": "object",
                "properties": {"rule": {"type": "string", "description": "Regla, hábito o dato que Helena debe aprender"}},
                "required": ["rule"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_status",
            "description": "Revisa stack (Django/Node/Python), rama git, cambios pendientes y estado de un proyecto local.",
            "parameters": {
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Nombre del proyecto local"}},
                "required": ["project"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_project_checks",
            "description": "Corre chequeos locales seguros (manage.py check, pytest, tsc, git status) de un proyecto en segundo plano.",
            "parameters": {
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Nombre del proyecto"}},
                "required": ["project"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_antigravity",
            "description": "Delega una tarea compleja de desarrollo o código a Antigravity en la carpeta del proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string", "description": "Nombre del proyecto donde trabajar"},
                    "task": {"type": "string", "description": "Descripción clara de la tarea de código o ingeniería"},
                },
                "required": ["project", "task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_status",
            "description": "Consulta el estado de las tareas de ingeniería corriendo o terminadas en segundo plano.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "init_helena_in_project",
            "description": "Crea el protocolo de memoria CONTEXT.md, .helena/index.json, CHANGELOG.md y lessons.md dentro de un proyecto.",
            "parameters": {
                "type": "object",
                "properties": {"project": {"type": "string", "description": "Nombre del proyecto"}},
                "required": ["project"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict | None = None) -> str:
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return f"Herramienta desconocida: {name}"
    try:
        return str(fn(**(arguments or {})))
    except TypeError as e:
        return f"Argumentos inválidos para {name}: {e}"
    except Exception as e:
        return f"Error en {name}: {e}"


def _summarize_briefing(raw: str) -> str:
    hora = clima = ""
    pend = "0"
    for ln in raw.splitlines():
        if ln.startswith("HORA:"):
            hora = ln.split(":", 1)[1].strip()
        elif ln.startswith("CLIMA:"):
            clima = ln.split(":", 1)[1].strip()
        elif ln.startswith("PENDIENTES"):
            m = re.search(r"\((\d+)\)", ln)
            if m:
                pend = m.group(1)
    parts = []
    if hora:
        parts.append(f"Ahora es {hora}.")
    if clima:
        parts.append(f"Clima: {clima}.")
    parts.append(f"Tienes {pend} pendientes principales en tu lista.")
    return " ".join(parts)


def _summarize_pc(raw: str) -> str:
    cpu = ram = disco = ""
    for ln in raw.splitlines():
        if ln.startswith("CPU:"):
            cpu = ln.split(":", 1)[1].strip()
        elif ln.startswith("RAM:"):
            ram = ln.split(":", 1)[1].strip()
        elif ln.startswith("DISCO C:"):
            disco = ln.split(":", 1)[1].strip()
    parts = [p for p in (f"CPU al {cpu}" if cpu else "", f"RAM {ram}" if ram else "", f"Disco C con {disco}" if disco else "") if p]
    return ("Estado del PC: " + ", ".join(parts) + ".") if parts else raw[:220]


def try_instant_action(user_text: str) -> str | None:
    """
    Enrutador ultrarrápido de comandos reales (<0.5 s, 0 tokens, funciona 100% offline).
    Retorna respuesta hablada si la orden es un comando directo inequívoco; None para delegar al LLM.
    """
    norm = _norm(user_text)

    if re.search(r"\b(que hora es|dime la hora|hora actual)\b", norm):
        city = os.getenv("CITY", "").split(",")[0].strip()
        suffix = f" en {city}" if city else ""
        return f"Son las {datetime.now().strftime('%H:%M')}{suffix}."

    if re.search(r"\b(gracias|eso es todo|nada mas|listo helena|listo elena)\b", norm) and len(norm.split()) <= 5:
        return "De nada, aquí sigo en segundo plano si me necesitas."

    if re.search(r"\b(briefing|resumen del dia|como esta el clima|dime el clima)\b", norm):
        return _summarize_briefing(daily_briefing())

    if re.search(r"\b(estado del pc|estado del computador|cuanta ram|como esta mi pc|recursos del pc)\b", norm):
        return _summarize_pc(pc_status())

    if re.search(r"\b(cuales son mis pendientes|que tengo pendiente|mis tareas|lista de tareas)\b", norm):
        return list_todos()

    if re.search(r"\b(revisa.*puertos|que puertos|puertos activos|puertos abiertos)\b", norm):
        out = check_ports()
        return "Puertos de desarrollo: " + out.replace("PUERTOS_DEV_ACTIVOS:", "").replace("\n", ", ").strip()

    if re.search(r"\b(audita git|estado de git|revisa git)\b", norm):
        out = git_audit()
        lines = [ln.strip() for ln in out.splitlines()[:4]]
        return "Auditoría git: " + ". ".join(lines)

    # Anotar / recordar / agregar tarea
    m_note = re.search(r"\b(?:anota(?:me)?|apunta)\s+(?:que\s+)?(.+)$", user_text, re.I)
    if m_note and len(m_note.group(1).strip()) >= 3:
        note_txt = m_note.group(1).strip()
        remember_note(note_txt, target="inbox")
        return f"Listo, anoté en tu inbox: {note_txt}."

    m_rem = re.search(r"\brecuerda(?:me)?\s+(?:que\s+)?(.+)$", user_text, re.I)
    if m_rem and len(m_rem.group(1).strip()) >= 3:
        rem_txt = m_rem.group(1).strip()
        remember_note(rem_txt, target="context")
        return f"Guardado en mi memoria permanente: {rem_txt}."

    m_todo = re.search(r"\b(?:agrega|anade|añade)\s+(?:a\s+)?(?:mis\s+)?(?:tareas|pendientes)\s*:?\s*(.+)$", user_text, re.I)
    if m_todo and len(m_todo.group(1).strip()) >= 3:
        return add_todo(m_todo.group(1).strip())

    # Atajo configurable: búsqueda de empleos usando HELENA_CV_PROJECT / HELENA_CV_FILE en .env
    if re.search(r"\b(busca|buscar|encuentra|ofertas|vacantes)\b", norm) and re.search(r"\b(trabajo|trabajos|empleo|empleos|postulacion|postulaciones)\b", norm):
        cv_proj = os.getenv("HELENA_CV_PROJECT", "").strip()
        cv_file = os.getenv("HELENA_CV_FILE", "").strip()
        if cv_proj:
            today = datetime.now().strftime("%Y_%m_%d")
            city = os.getenv("CITY", "remoto").strip()
            stack = os.getenv("USER_STACK", "JavaScript fullstack, Django, Python").strip()
            src_hint = f"desde {cv_file} (o los CVs existentes)" if cv_file else "desde los CVs en esta carpeta"
            job_task = (
                f"Lee mi perfil y experiencia {src_hint} y busca en la web ofertas de empleo actuales ({city} o remoto) "
                f"acordes a mi stack ({stack}). Guarda una lista estructurada con empresa, cargo, requisitos y enlace "
                f"directo en postulaciones_{today}.md dentro de esta carpeta."
            )
            return delegate_to_antigravity(cv_proj, job_task)

    # Delegación directa a Antigravity / subagentes (ANTES de abrir carpetas o buscar en Google!)
    if re.search(r"\b(antigravity|anti gravity|subagente|sub a gente|sub agente|delega|delegar)\b", norm):
        # Intentar extraer proyecto mencionado (ej. "proyecto mi-app", "carpeta backend")
        proj = "helena"
        m_p = re.search(
            r"\b(?:proyecto|carpeta|repo(?:sitorio)?)\s+(?:de\s+)?([a-z0-9áéíóúñ\-_\s]{2,32}?)(?:\s+(?:y|para|en|de\s+antigravity|con\s+antigravity)\b|$)",
            user_text,
            re.I,
        )
        if m_p:
            proj = m_p.group(1).strip()
        else:
            # Buscar si mencionó directamente el nombre de alguno de sus proyectos reales
            for base in trunner._projects_roots():
                if base == ROOT:
                    continue
                for item in base.iterdir():
                    if item.is_dir() and len(item.name) >= 4 and _norm(item.name) in norm:
                        proj = item.name
                        break
        # Si solo preguntó por el estado ("revisa el proyecto X en antigravity") sin pedir tarea/subagente
        if re.search(r"\b(revisa|estado|como esta|como quedo)\b", norm) and not re.search(r"\b(subagente|sub a gente|busca|crea|hagas|delega|ejecuta|arregla|implementa)\b", norm):
            return project_status(proj)
        return delegate_to_antigravity(proj, user_text.strip())

    # Estado de tareas asíncronas / chequeos / inicializar memoria Helena en proyectos
    if re.search(r"\b(estado de.*tareas|como van las tareas|tareas en segundo plano)\b", norm):
        return task_status()

    m_pst = re.search(r"\b(?:estado|como esta|como quedo|revisa)\s+(?:el\s+|mi\s+)?proyecto\s+(.+)$", user_text, re.I)
    if m_pst and len(m_pst.group(1).strip()) >= 2:
        return project_status(m_pst.group(1).strip())

    m_pchk = re.search(r"\b(?:corre|ejecuta|pasa)\s+(?:los\s+)?(?:tests|chequeos|pruebas)\s+(?:en|de|del)\s+(?:proyecto\s+)?(.+)$", user_text, re.I)
    if m_pchk and len(m_pchk.group(1).strip()) >= 2:
        return run_project_checks(m_pchk.group(1).strip())

    m_init = re.search(r"\b(?:inicializa|configura|crea)\s+(?:la\s+)?memoria\s+(?:de\s+helena\s+)?(?:en|para)\s+(?:el\s+proyecto\s+)?(.+)$", user_text, re.I)
    if m_init and len(m_init.group(1).strip()) >= 2:
        return init_helena_in_project(m_init.group(1).strip())

    # Entrenamiento continuo directo ("aprende que ...")
    m_teach = re.search(r"\baprende\s+(?:que\s+)?(.+)$", user_text, re.I)
    if m_teach and len(m_teach.group(1).strip()) >= 4:
        return teach_helena(m_teach.group(1).strip())

    # Crear carpeta real ("crea una carpeta en el escritorio que se llame X" / "crea la carpeta X en proyectos")
    m_mk1 = re.search(r"\bcrea(?:r)?\s+(?:una\s+|la\s+)?carpeta(?:\s+en\s+(?:el\s+|los\s+|la\s+)?(escritorio|proyectos|documentos|descargas))?\s+(?:que\s+se\s+llame|llamada|con\s+el\s+nombre|de\s+nombre)?\s*[\"']?([^\"'\.\?!]+)", user_text, re.I)
    if m_mk1:
        loc = m_mk1.group(1) or "escritorio"
        fname = re.sub(r"\s+en\s+(?:el\s+|los\s+|la\s+)?(escritorio|proyectos|documentos|descargas)\s*$", "", m_mk1.group(2), flags=re.I).strip()
        m_loc_end = re.search(r"\ben\s+(?:el\s+|los\s+|la\s+)?(escritorio|proyectos|documentos|descargas)\b", user_text, re.I)
        if m_loc_end:
            loc = m_loc_end.group(1)
        if fname:
            return create_folder(fname, location=loc, open_after=True)

    # Listar / abrir proyectos reales
    if re.search(r"\b(cuales son mis proyectos|lista mis proyectos|que proyectos tengo)\b", norm):
        return list_projects()

    m_proj = re.search(r"\babre\s+(?:el\s+|mi\s+)?proyecto\s+(.+)$", user_text, re.I)
    if m_proj and len(m_proj.group(1).strip()) >= 2:
        ed = "antigravity" if "antigravity" in norm else ("explorador" if "explorador" in norm or "carpeta" in norm else "vscode")
        pname = re.sub(r"\s+en\s+(?:visual studio code|vscode|antigravity|el explorador).*$", "", m_proj.group(1), flags=re.I).strip()
        return open_project(pname, editor=ed)

    # Abrir carpeta específica (solo si es orden simple sin una segunda acción con 'y ...')
    m_fld = re.search(r"\babre\s+(?:la\s+|mi\s+)?carpeta\s+([^,]+)$", user_text, re.I)
    if m_fld and " y " not in norm and len(m_fld.group(1).strip()) >= 2:
        return open_folder(m_fld.group(1).strip())

    # Control multimedia / volumen / cerrar pestaña
    if re.search(r"\b(pausa|pon pausa|deten la musica|reanuda la musica)\b", norm):
        return media_control("pausar")
    if re.search(r"\b(sube|subir)\s+(?:el\s+)?volumen\b", norm):
        return media_control("subir_volumen")
    if re.search(r"\b(baja|bajar)\s+(?:el\s+)?volumen\b", norm):
        return media_control("bajar_volumen")
    if re.search(r"\b(silencia|mutea|pon silencio)\b", norm):
        return media_control("silenciar")
    if re.search(r"\b(cierra|cerrar)\s+(?:la\s+|esta\s+)?(pestana|pestaña|video)\b", norm):
        return media_control("cerrar_pestana")

    # YouTube / música / búsqueda web directa
    if "youtube" in norm and re.search(r"\b(abre|abrir|pon|poner|reproduce|reproducir|busca|buscar|video|musica)\b", norm):
        q = re.sub(
            r"\b(helena|elena|puedes|hacer|una|tarea|sencilla|como|abre|abrir|pon|poner|reproduce|reproducir|busca|buscar|un|el|video|en|youtube|por|favor)\b",
            " ",
            norm,
        )
        q = re.sub(r"\s+", " ", q).strip()
        if not q or q in ("de", "de musica", "musica"):
            q = "musica para programar"
        else:
            q = re.sub(r"^de\s+", "", q)
        return play_youtube(q)

    m_yt = re.search(r"\b(?:pon|poner|reproduce|reproducir)\s+(?:un poco de\s+)?(musica.+|cancion.+)$", norm)
    if m_yt:
        return play_youtube(m_yt.group(1).strip())

    m_search = re.search(r"\bbusca(?:me)?\s+en\s+google\s+(.+)$", user_text, re.I)
    if m_search and "youtube" not in norm and len(m_search.group(1).strip()) >= 3:
        return web_search(m_search.group(1).strip())

    # Abrir aplicaciones seguras de la lista blanca
    m_open = re.search(r"\b(?:abre|abrir|lanza|muestra)\s+(?:el|la|mi)?\s*([a-z0-9\s]{2,25})$", norm)
    if m_open:
        target_app = m_open.group(1).strip()
        for k in SAFE_APPS:
            if k in target_app:
                return open_app(k)

    return None

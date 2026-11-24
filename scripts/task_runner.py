#!/usr/bin/env python3
"""
Helena v4 Pro — Motor de ingeniería sobre proyectos y cola de tareas asíncronas con Antigravity.
Permite:
  - Inspeccionar stack y estado git de cualquier proyecto local.
  - Correr chequeos seguros (Django check, pytest, npm test, git status) en segundo plano.
  - Delegar tareas de código a Antigravity (`agy -p` headless asíncrono, o handoff a IDE + portapapeles).
  - Inicializar el protocolo de memoria Helena (`CONTEXT.md`, `.helena/index.json`, `CHANGELOG.md`, `.helena/lessons.md`) en cualquier repo sin sobrescribir nada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import get_close_matches
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
from typing import Callable
import unicodedata

ROOT = Path(r"C:\Jarvis")
TASK_LOG_DIR = ROOT / "logs" / "tasks"
TASK_QUEUE_MD = ROOT / "memory" / "task_queue.md"
NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s\-_]", " ", clean).strip()


def _projects_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = []
    env_proj = os.getenv("HELENA_PROJECTS_DIR", "").strip()
    if env_proj and Path(env_proj).exists():
        roots.append(Path(env_proj))
    desktop = home / "OneDrive" / "Desktop"
    if not desktop.exists():
        desktop = home / "Desktop"
    for p in (home / "Projects", desktop, ROOT):
        if p.exists() and p not in roots:
            roots.append(p)
    return roots


def find_project_dir(name: str) -> Path | None:
    """Resuelve un proyecto local por nombre exacto, subcadena o coincidencia difusa."""
    raw = str(name or "").strip()
    if not raw:
        return None
    cand_path = Path(raw)
    if cand_path.is_absolute() and cand_path.is_dir():
        return cand_path

    norm = _norm(raw)
    if norm in ("helena", "jarvis"):
        return ROOT

    candidates: dict[str, Path] = {}
    for base in _projects_roots():
        if base == ROOT:
            candidates["helena"] = ROOT
            continue
        try:
            for item in base.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    k = _norm(item.name)
                    candidates.setdefault(k, item)
        except Exception:
            pass

    for k, p in candidates.items():
        if norm and (norm == k or norm in k or k in norm):
            return p
    m = get_close_matches(norm, list(candidates.keys()), n=1, cutoff=0.45)
    return candidates[m[0]] if m else None


def detect_stack(proj_dir: Path) -> list[str]:
    stack = []
    if (proj_dir / "manage.py").exists():
        stack.append("Django")
    if (proj_dir / "requirements.txt").exists() or (proj_dir / "pyproject.toml").exists():
        stack.append("Python")
    if (proj_dir / "package.json").exists():
        stack.append("JavaScript/Node")
    if (proj_dir / "tsconfig.json").exists():
        stack.append("TypeScript")
    if (proj_dir / "Dockerfile").exists() or (proj_dir / "docker-compose.yml").exists():
        stack.append("Docker")
    return stack or ["Genérico"]


def get_project_status(project: str) -> str:
    """Retorna resumen técnico conciso del proyecto (stack, git, cambios y si tiene CONTEXT.md)."""
    p = find_project_dir(project)
    if not p:
        return f"No encontré el proyecto {project}."
    stack = ", ".join(detect_stack(p))
    has_ctx = (p / "CONTEXT.md").exists()
    git_info = "sin git"
    if (p / ".git").exists():
        try:
            br = subprocess.run(["git", "-C", str(p), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5, creationflags=NO_WIN)
            branch = br.stdout.strip() or "sin-commits"
            st = subprocess.run(["git", "-C", str(p), "status", "--porcelain"], capture_output=True, text=True, timeout=5, creationflags=NO_WIN)
            dirty = len([ln for ln in st.stdout.splitlines() if ln.strip()])
            git_info = f"rama {branch}, {dirty} cambios sin commit"
        except Exception:
            git_info = "git presente"
    ctx_msg = "con memoria CONTEXT.md" if has_ctx else "sin CONTEXT.md aún"
    return f"Proyecto {p.name}: stack {stack}, {git_info}, {ctx_msg}."


def init_helena_memory(project: str) -> str:
    """Crea de forma idempotente CONTEXT.md, .helena/index.json, CHANGELOG.md y .helena/lessons.md en un proyecto."""
    p = find_project_dir(project)
    if not p:
        return f"No encontré el proyecto {project}."

    today = datetime.now().strftime("%Y-%m-%d")
    stack = ", ".join(detect_stack(p))
    top_items = [x.name for x in sorted(p.iterdir()) if not x.name.startswith(".git")][:20]
    created = []

    helena_dir = p / ".helena"
    helena_dir.mkdir(exist_ok=True)

    ctx_file = p / "CONTEXT.md"
    if not ctx_file.exists():
        lines = [
            f"# CONTEXT — {p.name}",
            "",
            "## Propósito",
            f"Proyecto local en `{p}` (completar descripción funcional en 1 línea).",
            "",
            "## Stack",
            f"- {stack}",
            "",
            "## Mapa de Archivos (raíz)",
            *[f"- `{name}` — *(descripción pendiente)*" for name in top_items],
            "",
            "## Estado",
            "- 🔄 Memoria inicializada automáticamente por Helena.",
            "",
            "## Deuda Técnica",
            "- Completar comandos de arranque/test y decisiones clave.",
            "",
        ]
        ctx_file.write_text("\n".join(lines), encoding="utf-8")
        created.append("CONTEXT.md")

    idx_file = helena_dir / "index.json"
    if not idx_file.exists():
        idx_data = {
            "version": 1,
            "updated": today,
            "project": p.name,
            "stack": detect_stack(p),
            "files": [
                {"path": name, "summary": "Elemento raíz detectado", "exports": [], "updated": today}
                for name in top_items[:15]
            ],
        }
        idx_file.write_text(json.dumps(idx_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created.append(".helena/index.json")

    chg_file = p / "CHANGELOG.md"
    if not chg_file.exists():
        chg_file.write_text(f"# CHANGELOG — {p.name}\n\n## {today}\n- Inicializada memoria estructurada de Helena (`CONTEXT.md`, `.helena/index.json`, `.helena/lessons.md`).\n", encoding="utf-8")
        created.append("CHANGELOG.md")

    les_file = helena_dir / "lessons.md"
    if not les_file.exists():
        les_file.write_text(f"# Lessons Learned — {p.name}\n\nLeer al iniciar cada sesión.\n", encoding="utf-8")
        created.append(".helena/lessons.md")

    if not created:
        return f"El proyecto {p.name} ya tenía toda la memoria de Helena creada; no sobrescribí nada."
    return f"Listo, creé {', '.join(created)} en el proyecto {p.name}."


def find_agy_binary() -> str | None:
    """Localiza agy.exe en PATH o en su ruta oficial %LOCALAPPDATA%\\agy\\bin\\agy.exe."""
    in_path = shutil.which("agy")
    if in_path:
        return in_path
    fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    return str(fallback) if fallback.exists() else None


def _looks_english(text: str) -> bool:
    low = f" {text.lower()} "
    en_hits = sum(1 for w in (" the ", " error:", " command ", " permission ", " cannot ", " timed out ", " tool ", " required ", " settings.json ", " no output ") if w in low)
    return en_hits >= 2


def _friendly_spanish_summary(project_name: str, raw_out: str, returncode: int) -> str:
    clean = re.sub(r"\s+", " ", (raw_out or "")).strip()
    low = clean.lower()
    if "permission" in low and ("denied" in low or "cannot prompt" in low):
        return f"Antigravity en {project_name} necesitó un permiso de terminal que no pudo aprobarse en segundo plano. Guardé el detalle en los registros."
    if "timed out" in low or "timeout" in low or "context canceled" in low:
        return f"La tarea en {project_name} excedió el tiempo límite y se detuvo. Puedes revisar el registro."
    if returncode != 0:
        return f"Antigravity encontró un problema en {project_name}. Guardé el detalle en los registros."
    if not clean or _looks_english(clean):
        return f"Antigravity terminó su trabajo en {project_name} y guardó los resultados."
    return f"Antigravity terminó en {project_name}: {clean[:200]}"
@dataclass
class BackgroundTask:
    task_id: str
    kind: str
    project: str
    description: str
    status: str  # RUNNING | DONE | ERROR | HANDOFF_IDE
    started_at: str
    finished_at: str = ""
    summary: str = ""
    log_path: str = ""


class AsyncTaskManager:
    """Gestiona tareas asíncronas de ingeniería (chequeos y delegación a Antigravity) sin bloquear la voz."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: list[BackgroundTask] = []
        self._notifier: Callable[[str], None] | None = None

    def set_notifier(self, fn: Callable[[str], None]) -> None:
        self._notifier = fn

    def _notify(self, msg: str) -> None:
        if self._notifier:
            try:
                self._notifier(msg)
            except Exception:
                pass

    def _append_queue_md(self, t: BackgroundTask) -> None:
        TASK_QUEUE_MD.parent.mkdir(parents=True, exist_ok=True)
        if not TASK_QUEUE_MD.exists():
            TASK_QUEUE_MD.write_text("# Cola de Tareas de Ingeniería — Helena\n\n", encoding="utf-8")
        with TASK_QUEUE_MD.open("a", encoding="utf-8") as f:
            f.write(f"- **[{t.started_at}] `{t.task_id}` ({t.status})** `{t.project}` — {t.description}\n")

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}_{datetime.now().strftime('%H%M%S')}"

    def list_tasks(self) -> str:
        with self._lock:
            if not self._tasks:
                return "No hay tareas de ingeniería en curso en esta sesión."
            recent = self._tasks[-4:]
        parts = [f"{t.project} ({t.status}): {t.summary or t.description[:50]}" for t in recent]
        return "Tareas recientes: " + "; ".join(parts) + "."

    def run_checks_async(self, project: str) -> str:
        """Lanza chequeos seguros solo lectura (Django check / pytest / npm test / git) en segundo plano."""
        p = find_project_dir(project)
        if not p:
            return f"No encontré el proyecto {project}."

        tid = self._new_id("chk")
        TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = TASK_LOG_DIR / f"{tid}.log"
        t = BackgroundTask(
            task_id=tid,
            kind="checks",
            project=p.name,
            description="Chequeos locales seguros",
            status="RUNNING",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            log_path=str(log_file),
        )
        with self._lock:
            self._tasks.append(t)
        self._append_queue_md(t)

        def _worker() -> None:
            outputs = []
            ok_all = True
            try:
                # 1) Detectar python local (.venv o global)
                py_exe = str(p / ".venv" / "Scripts" / "python.exe") if (p / ".venv" / "Scripts" / "python.exe").exists() else (
                    str(p / "venv" / "Scripts" / "python.exe") if (p / "venv" / "Scripts" / "python.exe").exists() else "python"
                )
                cmds: list[tuple[str, list[str]]] = []
                if (p / ".git").exists():
                    cmds.append(("git status", ["git", "-C", str(p), "status", "--short"]))
                if (p / "manage.py").exists():
                    cmds.append(("django check", [py_exe, "manage.py", "check"]))
                elif (p / "tests").exists() or (p / "pytest.ini").exists():
                    cmds.append(("pytest", [py_exe, "-m", "pytest", "-q"]))
                if (p / "tsconfig.json").exists():
                    cmds.append(("tsc", ["cmd.exe", "/c", "npx", "tsc", "--noEmit"]))

                if not cmds:
                    outputs.append(get_project_status(str(p)))
                else:
                    for label, cmd in cmds:
                        proc = subprocess.run(cmd, cwd=str(p), capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace", creationflags=NO_WIN)
                        out = (proc.stdout or proc.stderr or "").strip()
                        if proc.returncode != 0:
                            ok_all = False
                        outputs.append(f"[{label} rc={proc.returncode}] {out[:300]}")

                log_file.write_text("\n\n".join(outputs), encoding="utf-8")
                t.status = "DONE" if ok_all else "ERROR"
                t.finished_at = datetime.now().strftime("%H:%M:%S")
                t.summary = f"Chequeos de {p.name} " + ("pasaron sin errores." if ok_all else "detectaron alertas; revisa el log.")
            except Exception as e:
                t.status = "ERROR"
                t.finished_at = datetime.now().strftime("%H:%M:%S")
                t.summary = f"Error corriendo chequeos en {p.name}: {e}"
            self._notify(t.summary)

        threading.Thread(target=_worker, daemon=True).start()
        return f"Dejé corriendo los chequeos de {p.name} en segundo plano. Te aviso apenas terminen."

    def delegate_to_antigravity(self, project: str, task: str) -> str:
        """
        Delega una tarea compleja de código a Antigravity dentro de la carpeta exacta del proyecto.
        - Con `agy` CLI instalado: ejecuta en segundo plano (`agy -p`) y notifica por voz al terminar.
        - Sin `agy` CLI: copia el brief estructurado al portapapeles y abre Antigravity en ese proyecto.
        """
        p = find_project_dir(project)
        if not p:
            return f"No encontré el proyecto {project}."
        clean_task = str(task or "").strip()
        if len(clean_task) < 4:
            return "Dime con más detalle qué tarea quieres delegar a Antigravity."

        brief = (
            f"Trabajando en el proyecto `{p.name}` (`{p}`).\n"
            f"Primero lee `CONTEXT.md`, `.helena/lessons.md` y revisa si hay skills en `.agents/skills/` del proyecto.\n"
            f"Tarea solicitada por voz: {clean_task}\n"
            f"Reglas: usa lectura/escritura de archivos y búsqueda web (evita comandos de terminal interactivos para no requerir permisos en headless), "
            f"guarda resultados en un archivo dentro del proyecto si aplica, responde SIEMPRE EN ESPAÑOL al final con un resumen "
            f"de máximo 2 frases claras (para leerse en voz alta), y NO hagas git push ni borres archivos."
        )

        tid = self._new_id("agy")
        TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = TASK_LOG_DIR / f"{tid}.log"
        agy_bin = find_agy_binary()

        if agy_bin:
            t = BackgroundTask(
                task_id=tid,
                kind="antigravity-cli",
                project=p.name,
                description=clean_task,
                status="RUNNING",
                started_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                log_path=str(log_file),
            )
            with self._lock:
                self._tasks.append(t)
            self._append_queue_md(t)

            def _agy_worker() -> None:
                try:
                    proc = subprocess.run(
                        [agy_bin, "-p", brief, "--output-format", "text", "--mode", "accept-edits", "--print-timeout", "240s"],
                        cwd=str(p),
                        capture_output=True,
                        text=True,
                        timeout=300,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=NO_WIN,
                    )
                    stdout_clean = (proc.stdout or "").strip()
                    stderr_clean = (proc.stderr or "").strip()
                    full_out = "\n".join(x for x in (stdout_clean, stderr_clean) if x)
                    log_file.write_text(full_out, encoding="utf-8")
                    t.status = "DONE" if (proc.returncode == 0 and "auto-denied" not in full_out.lower()) else "ERROR"
                    t.summary = _friendly_spanish_summary(p.name, stdout_clean or stderr_clean, proc.returncode)
                except subprocess.TimeoutExpired:
                    t.status = "ERROR"
                    t.summary = f"La tarea en {p.name} tardó demasiado tiempo y se canceló automáticamente."
                except Exception:
                    t.status = "ERROR"
                    t.summary = f"Ocurrió un problema técnico al ejecutar Antigravity en {p.name}."
                t.finished_at = datetime.now().strftime("%H:%M:%S")
                self._notify(t.summary)

            threading.Thread(target=_agy_worker, daemon=True).start()
            return f"Listo, delegué la tarea a Antigravity en {p.name} en segundo plano. Te aviso apenas termine."

        # Handoff fluido a Antigravity IDE + portapapeles (funciona hoy mismo sin instalar agy CLI!)
        try:
            subprocess.run(["clip.exe"], input=brief.encode("utf-16-le"), check=False, timeout=5)
        except Exception:
            pass
        ag_exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity" / "Antigravity.exe"
        if ag_exe.exists():
            try:
                subprocess.Popen([str(ag_exe), str(p)], cwd=str(p))
            except Exception:
                pass
        t = BackgroundTask(
            task_id=tid,
            kind="antigravity-ide",
            project=p.name,
            description=clean_task,
            status="HANDOFF_IDE",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            finished_at=datetime.now().strftime("%H:%M:%S"),
            summary=f"Abierto Antigravity en {p.name} con el brief en portapapeles.",
            log_path=str(log_file),
        )
        log_file.write_text(brief, encoding="utf-8")
        with self._lock:
            self._tasks.append(t)
        self._append_queue_md(t)
        return (
            f"Todavía falta instalar y autenticar el CLI agy para ejecutar subagentes solos. "
            f"Por ahora abrí Antigravity en {p.name} y copié la orden en tu portapapeles para pegar con Control V."
        )


TASK_MANAGER = AsyncTaskManager()

#!/usr/bin/env python3
"""
Helena — Puente de Voz Pro v3 (Avatar OOOOO + Voz con Manos + Cerebro Híbrido Triple).
Flujo: Wake word entrenada ('Helena'/'Jarvis') o 'Hey Jarvis' o Push-to-Talk (Ctrl+Alt+Espacio / clic en OOOOO)
       -> pre-buffer + grabar en RAM hasta silencio rápido (0.85 s)
       -> verificación de voz del propietario + faster-whisper (CUDA RTX 4060 si disponible, o CPU int8)
       -> Enrutador instantáneo de acciones locales (<0.5 s, 0 tokens, offline)
          o Cerebro Híbrido: agy CLI / Gemini API (Function Calling) / Ollama local en RTX 4060 (Tool Calling)
       -> edge-tts en RAM (es-CL-CatalinaNeural) con fallback offline SAPI5 + conversación continua (6.5 s).
Privacidad: cero archivos de audio en disco salvo --save-audio explícito.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import deque
import ctypes
from ctypes import wintypes
from datetime import datetime
import io
import json
import logging
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import winsound

ROOT = Path(r"C:\Jarvis")
sys.path.insert(0, str(ROOT / "scripts"))

from context_monitor import get_active_context
from soul_avatar import AvatarBridge, run_avatar_app
import task_runner as trunner
from voice_profile import PROFILE_PATH, VoiceProfile
import voice_tools as vtools

LOG_DIR = ROOT / "logs"
OFF_FLAG = ROOT / "HELENA_OFF"
VOICE_CHOICE_FILE = ROOT / "memory" / "voice_choice.txt"
AGENTS_MD = ROOT / "AGENTS.md"

VOICE_PRESETS = {
    "vivienne": ("Vivienne", "fr-FR-VivienneMultilingualNeural"),
    "vivian": ("Vivienne", "fr-FR-VivienneMultilingualNeural"),
    "paloma": ("Paloma", "es-US-PalomaNeural"),
    "ava": ("Ava", "en-US-AvaMultilingualNeural"),
}
CONTEXT_MD = ROOT / "memory" / "context.md"
ENV_FILE = ROOT / ".env"

LOG_DIR.mkdir(parents=True, exist_ok=True)
_log_handlers: list[logging.Handler] = [
    logging.FileHandler(LOG_DIR / "voice_bridge.log", encoding="utf-8")
]
if sys.stdout is not None:
    _log_handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=_log_handlers,
)
log = logging.getLogger("helena.voice")

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80 ms a 16 kHz (óptimo para VAD/audio)
WHISPER_PROMPT = "Hola Helena, abre Antigravity, crea un subagente, YouTube, Google, GitHub, LinkedIn, Django, Python y JavaScript."


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        if ENV_FILE.exists():
            load_dotenv(ENV_FILE)
    except Exception:
        pass


def normalize_text(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", clean).strip()


def clean_for_speech(text: str, max_chars: int = 480) -> str:
    t = re.sub(r"```[\s\S]*?```", " ", text)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    t = re.sub(r"[*_#>~|]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_chars:
        cut = t[:max_chars]
        last_dot = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
        t = cut[: last_dot + 1] if last_dot > 120 else cut + "..."
    return t or "Listo."


def beep(freq: int, ms: int) -> None:
    try:
        winsound.Beep(freq, ms)
    except Exception:
        pass


def check_shutdown_command(text: str) -> bool:
    norm = re.sub(r"\s+", " ", normalize_text(text))
    patterns = [
        r"\b(helena|elena)\s+apagate\b",
        r"\bapagate\s+(helena|elena)\b",
        r"\bdesactivate\s+(helena|elena)\b",
        r"\b(helena|elena)\s+desactivate\b",
    ]
    return any(re.search(p, norm) for p in patterns)


def check_visibility_command(text: str) -> tuple[str, str] | None:
    """Detecta órdenes de visibilidad del avatar OOOOO ('escóndete', 'aparece', 'modo automático')."""
    norm = re.sub(r"\s+", " ", normalize_text(text))
    if re.search(r"\b(escondete|ocultate|esconderte|no me molestes|modo discreto|vete a segundo plano)\b", norm):
        return ("hide", "Entendido, me escondo para no molestarte. Di Oye Helena cuando me necesites.")
    if re.search(r"\b(aparece|muestrate|vuelve a aparecer|deja de esconderte)\b", norm):
        return ("show", "Aquí estoy de vuelta.")
    if re.search(r"\b(modo automatico|modo inteligente)\b", norm):
        return ("auto", "Modo inteligente activado: me adaptaré a lo que estés haciendo.")
    return None


def check_voice_switch_command(text: str, current_voice: str) -> tuple[str, str] | None:
    """Permite cambiar en vivo entre Vivienne (#3) y Paloma (#4) diciendo 'cambia de voz' o el nombre."""
    norm = re.sub(r"\s+", " ", normalize_text(text))
    if not re.search(r"\b(cambia|cambiar|usa|usar|pon|poner|vuelve)\b.*\b(voz|vivienne|vivian|paloma|ava)\b", norm):
        return None
    for key, (label, vid) in VOICE_PRESETS.items():
        if re.search(rf"\b{key}\b", norm):
            return (vid, f"Listo, cambié a la voz de {label}.")
    # Si solo dijo "cambia de voz", alterna entre Vivienne (#3) y Paloma (#4)
    if current_voice == "fr-FR-VivienneMultilingualNeural":
        return ("es-US-PalomaNeural", "Listo, cambié a la voz de Paloma.")
    return ("fr-FR-VivienneMultilingualNeural", "Listo, cambié a la voz de Vivienne.")


def load_saved_voice(default_voice: str) -> str:
    if VOICE_CHOICE_FILE.exists():
        saved = VOICE_CHOICE_FILE.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    return default_voice


# Comandos de voz que activan a Helena (Whisper a veces escribe "Elena" sin H)
WAKE_PREFIX_RE = re.compile(
    r"^\s*[¡¿!?,.\s]*(?:(?:oye|hola|hey|ey|ok|okay|despierta|activa|escuchame|escucha)\s+)*"
    r"(?:helena|elena)\b[\s,.:;!?¡¿\-]*",
    re.I,
)
WAKE_ANYWHERE_RE = re.compile(r"\b(?:helena|elena)\b", re.I)


def extract_wake_command(text: str) -> tuple[bool, str]:
    """
    Detecta si el usuario invocó a Helena por voz ('Oye Helena', 'Hola Helena', 'Helena',
    'Despierta Helena'). Retorna (activada, orden_incluida).
    """
    raw = text.strip()
    if not raw:
        return False, ""
    norm = normalize_text(raw)

    if WAKE_PREFIX_RE.match(norm):
        stripped = re.sub(
            r"^\s*[¡¿!?,.\s]*(?:(?:oye|hola|hey|ey|ok|okay|despierta|activa|esc[uú]chame|escucha)[,\s¡¿!?]*)*"
            r"(?:helena|elena)\b[\s,.:;!?¡¿\-]*",
            "",
            raw,
            count=1,
            flags=re.I,
        ).strip()
        return True, stripped

    if WAKE_ANYWHERE_RE.search(norm):
        cleaned = re.sub(r"\b(?:helena|elena)\b", "", raw, flags=re.I)
        cleaned = re.sub(r"^[\s,.:;!?¡¿\-]+|[\s,.:;!?¡¿\-]+$", "", cleaned).strip()
        return True, cleaned

    return False, ""


def read_compact_voice_prompt() -> str:
    """Prompt conversacional natural + reglas de entrenamiento continuo para Helena."""
    learned = ""
    tr_file = ROOT / "memory" / "helena_training.md"
    if tr_file.exists():
        try:
            txt = tr_file.read_text(encoding="utf-8").strip()
            if txt:
                learned = "\nReglas aprendidas del usuario:\n" + txt[-900:]
        except Exception:
            pass
    return (
        "Eres Helena, compañera e ingeniera de software en Windows 11. "
        "IDIOMA OBLIGATORIO: responde SIEMPRE 100% en español; NUNCA cambies a inglés ni mezcles frases en inglés. "
        "Hablas en español natural, cálido y relajado, como una persona real cercana — NUNCA uses "
        "frases robóticas ni clichés de atención al cliente como '¿Hay algo más en lo que pueda ayudarte?'. "
        "Responde en 1 o 2 frases cortas y directas, sin markdown, listas ni emojis. "
        "Tienes 24 herramientas reales del PC y desarrollo (create_folder, open_folder, list_projects, open_project, "
        "project_status, run_project_checks, delegate_to_antigravity, task_status, init_helena_in_project, "
        "create_file, media_control, play_youtube, web_search, open_app, daily_briefing, pc_status, "
        "remember_note, list_todos, add_todo, git_audit, check_ports, probe_api, create_automation, teach_helena). "
        "REGLA DE ORO: para tareas complejas de código o cambios en proyectos usa delegate_to_antigravity; "
        "usa siempre la herramienta real y NUNCA inventes rutas falsas ni digas que hiciste algo sin llamarla."
        + learned
    )


def read_context_prompt() -> str:
    parts = []
    for p in (AGENTS_MD, CONTEXT_MD):
        if p.exists():
            try:
                parts.append(p.read_text(encoding="utf-8")[:3200])
            except Exception:
                pass
    parts.append(
        "MODO VOZ ACTIVO: Eres Helena, asistente personal de ingeniería en Windows 11. "
        "Tienes herramientas reales disponibles (briefing, estado del PC, memoria inbox/context, "
        "tareas TODO, auditoría git, puertos/APIs, abrir apps seguras y crear automatizaciones). "
        "Úsalas cuando la petición lo requiera. Responde SIEMPRE en español natural, directo y "
        "MUY BREVE (máximo 2 o 3 frases cortas sin markdown, listas, emojis ni URLs), listo para "
        "leerse en voz alta. Para acciones destructivas, pide confirmación verbal primero."
    )
    return "\n\n".join(parts)


class BrainClient:
    """
    Cerebro híbrido triple con memoria conversacional de 8 turnos y tool-calling real:
      - agy CLI headless (si está instalado)
      - Gemini API (gemini-2.5-flash con Function Calling automático)
      - Ollama local en RTX 4060 (http://127.0.0.1:11434 con /api/chat + tools)
    """

    def __init__(self, preferred: str = "auto") -> None:
        self.preferred = preferred.lower()
        self.agy_path = trunner.find_agy_binary()
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_VOICE_MODEL", "gemini-2.5-flash").strip()
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "helena").strip()
        self._genai_client = None
        self.history: deque[dict[str, str]] = deque(maxlen=8)

    def ollama_available(self, autostart: bool = False) -> tuple[bool, list[str]]:
        import requests

        def _ping() -> tuple[bool, list[str]]:
            try:
                r = requests.get(f"{self.ollama_url}/api/tags", timeout=1.5)
                if r.status_code == 200:
                    models = [m.get("name", "") for m in r.json().get("models", [])]
                    return True, models
            except Exception:
                pass
            return False, []

        ok, models = _ping()
        if ok or not autostart:
            return ok, models

        ol_exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if ol_exe.exists():
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
                subprocess.Popen(
                    [str(ol_exe), "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
                for _ in range(10):
                    time.sleep(0.5)
                    ok, models = _ping()
                    if ok:
                        log.info("Ollama local auto-iniciado (%s).", models[:2])
                        return True, models
            except Exception as e:
                log.warning("No se pudo auto-iniciar Ollama: %s", e)
        return False, []

    def _pick_ollama_model(self, available: list[str]) -> str:
        if not available:
            return self.ollama_model
        for pref in (self.ollama_model, "helena", "qwen2.5:7b"):
            base = pref.split(":")[0]
            for m in available:
                if m == pref or m.startswith(base + ":"):
                    return m
        return available[0]

    def active_backend(self, autostart_ollama: bool = False) -> str:
        ol_ok, _ = self.ollama_available(autostart=autostart_ollama)
        if self.preferred == "agy" and self.agy_path:
            return "agy"
        if self.preferred == "gemini" and self.gemini_key:
            return "gemini"
        if self.preferred == "ollama" and ol_ok:
            return "ollama"
        # Automático híbrido: Ollama local rápido (1 s) para voz diaria + agy reservado para delegate_to_antigravity
        if ol_ok:
            return "ollama"
        if self.gemini_key:
            return "gemini"
        if self.agy_path:
            return "agy"
        return "local-tools-only"

    def remember_turn(self, user_text: str, assistant_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})

    def ask(self, user_text: str) -> str:
        backend = self.active_backend()
        reply = ""
        if backend == "agy":
            reply = self._ask_agy(user_text)
        elif backend == "gemini":
            reply = self._ask_gemini(user_text)
        elif backend == "ollama":
            reply = self._ask_ollama(user_text)
        else:
            reply = (
                "Solo están activas mis acciones rápidas locales. Para conversación libre con IA, "
                "inicia Ollama en tu RTX 4060 o agrega tu GEMINI_API_KEY en el archivo punto env."
            )
        self.remember_turn(user_text, reply)
        return reply

    def _ask_agy(self, user_text: str) -> str:
        prompt = "[MODO VOZ: español, máx 2-3 frases sin markdown] " + user_text
        try:
            proc = subprocess.run(
                [self.agy_path, "-p", prompt, "--output-format", "text"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=45,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return clean_for_speech(proc.stdout)
        except Exception as e:
            log.error("Error agy: %s", e)
        if self.gemini_key:
            return self._ask_gemini(user_text)
        if self.ollama_available()[0]:
            return self._ask_ollama(user_text)
        return "No pude conectar con Antigravity CLI."

    def _ask_gemini(self, user_text: str) -> str:
        try:
            from google import genai
            from google.genai import types

            if self._genai_client is None:
                self._genai_client = genai.Client(api_key=self.gemini_key)

            contents = []
            for turn in self.history:
                role = "model" if turn["role"] == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=turn["content"])]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))

            resp = self._genai_client.models.generate_content(
                model=self.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=read_context_prompt(),
                    tools=vtools.GEMINI_TOOL_FUNCS,
                    max_output_tokens=220,
                    temperature=0.35,
                ),
            )
            if resp.text:
                return clean_for_speech(resp.text)
            return "Acción completada."
        except Exception as e:
            log.error("Error Gemini API: %s", e)
            if self.ollama_available()[0]:
                log.info("Cambiando automáticamente a Ollama local (fallback sin internet).")
                return self._ask_ollama(user_text)
            return "No pude conectar con Gemini. Revisa tu conexión o enciende Ollama local."

    def _ask_ollama(self, user_text: str) -> str:
        import requests

        ok, avail = self.ollama_available()
        if not ok:
            return "Ollama local no está activo en este momento."
        model = self._pick_ollama_model(avail)

        messages = [{"role": "system", "content": read_compact_voice_prompt()}]
        messages.extend(list(self.history))
        messages.append({"role": "user", "content": user_text})
        ol_opts = {"num_ctx": 4096, "temperature": 0.35, "num_predict": 160}

        try:
            payload = {
                "model": model,
                "messages": messages,
                "tools": vtools.OLLAMA_TOOLS,
                "stream": False,
                "keep_alive": "15m",
                "options": ol_opts,
            }
            r = requests.post(f"{self.ollama_url}/api/chat", json=payload, timeout=90)
            r.raise_for_status()
            msg = r.json().get("message", {})

            # Si el modelo local decidió usar una o más herramientas reales, ejecutarlas y cerrar turno
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                messages.append(msg)
                for tc in tool_calls[:3]:
                    fn_info = tc.get("function", {})
                    fn_name = fn_info.get("name", "")
                    fn_args = fn_info.get("arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args)
                        except Exception:
                            fn_args = {}
                    log.info("Ollama tool_call -> %s(%s)", fn_name, fn_args)
                    tool_out = vtools.execute_tool(fn_name, fn_args)
                    messages.append({"role": "tool", "content": tool_out})

                r2 = requests.post(
                    f"{self.ollama_url}/api/chat",
                    json={"model": model, "messages": messages, "stream": False, "keep_alive": "15m", "options": ol_opts},
                    timeout=90,
                )
                r2.raise_for_status()
                msg = r2.json().get("message", {})

            return clean_for_speech(msg.get("content", ""))
        except Exception as e:
            log.error("Error Ollama local (%s): %s", model, e)
            return "Hubo un error hablando con el modelo local Ollama."


async def _tts_mp3_bytes(text: str, voice: str, rate: str = "+0%", pitch: str = "-1Hz") -> bytes:
    import edge_tts

    comm = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    chunks = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.extend(chunk["data"])
    return bytes(chunks)


def _speak_gemini_tts(text: str, play: bool = True) -> int:
    """TTS humano ultra-expresivo vía Gemini 2.5 Flash Preview TTS (opcional si TTS_ENGINE=gemini y hay GEMINI_API_KEY)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return 0
    import numpy as np
    import sounddevice as sd
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    voice_name = os.getenv("GEMINI_TTS_VOICE", "Aoede")
    resp = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=f"Di lo siguiente en español natural, cálido y relajado, sin tono robótico: {text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )
    pcm_bytes = resp.candidates[0].content.parts[0].inline_data.data
    if not pcm_bytes:
        return 0
    pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    pcm *= 0.80
    if play:
        sd.play(pcm, samplerate=24000)
        sd.wait()
    return len(pcm_bytes)


def _speak_offline_sapi5(text: str) -> None:
    """Fallback 100% offline usando el sintetizador nativo de Windows (0 archivos en disco)."""
    safe = text.replace("'", " ").replace('"', " ")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } | Select-Object -First 1; "
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
        f"$s.Speak('{safe}')"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], timeout=20)


def speak_in_ram(
    text: str,
    voice: str,
    play: bool = True,
    rate: str | None = None,
    pitch: str | None = None,
    gain: float = 0.78,
) -> int:
    """Sintetiza en RAM con voz HD natural (edge-tts Multilingual v2 o Gemini TTS) y cae a SAPI5 offline."""
    import av
    import numpy as np
    import sounddevice as sd

    if os.getenv("TTS_ENGINE", "edge").lower() == "gemini" and os.getenv("GEMINI_API_KEY", "").strip():
        try:
            n = _speak_gemini_tts(text, play=play)
            if n > 0:
                return n
        except Exception as ge:
            log.warning("Gemini TTS falló (%s); usando edge-tts Multilingual HD.", ge)

    tts_rate = rate if rate is not None else os.getenv("TTS_RATE", "+0%")
    tts_pitch = pitch if pitch is not None else os.getenv("TTS_PITCH", "-1Hz")
    # Reintentar 1 vez si edge-tts falla justo al despertar el PC de suspensión
    last_err = None
    for attempt in range(2):
        try:
            mp3_bytes = asyncio.run(_tts_mp3_bytes(text, voice, rate=tts_rate, pitch=tts_pitch))
            if not mp3_bytes:
                raise RuntimeError("edge-tts devolvió 0 bytes")
            bio = io.BytesIO(mp3_bytes)
            frames = []
            sr = 24000
            with av.open(bio, format="mp3") as container:
                stream = container.streams.audio[0]
                sr = stream.rate or 24000
                for frame in container.decode(stream):
                    arr = frame.to_ndarray()
                    if arr.ndim == 2:
                        arr = arr.T
                    frames.append(arr.astype(np.float32))
            if not frames:
                return 0
            pcm = np.concatenate(frames, axis=0)
            max_abs = float(np.max(np.abs(pcm))) or 1.0
            if max_abs > 1.0:
                pcm = pcm / max_abs
            pcm = pcm * float(gain)
            fade_n = min(int(sr * 0.015), len(pcm) // 4)
            if fade_n > 1:
                ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
                if pcm.ndim == 2:
                    ramp = ramp[:, None]
                pcm[:fade_n] *= ramp
                pcm[-fade_n:] *= ramp[::-1]
            if play:
                sd.play(pcm, samplerate=sr)
                sd.wait()
            return len(mp3_bytes)
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(1.0)
    log.warning("edge-tts no disponible (%s); usando voz offline Windows SAPI5.", last_err)
    if play:
        try:
            _speak_offline_sapi5(text[:260])
        except Exception as e2:
            log.error("Error SAPI5 offline: %s", e2)
    return 0


class Win32HotkeyListener:
    """Hotkey global Ctrl+Alt+Space en Windows sin requerir privilegios de administrador."""

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_NOREPEAT = 0x4000
    VK_SPACE = 0x20
    WM_HOTKEY = 0x0312
    HOTKEY_ID = 1

    def __init__(self, callback, stop_event: threading.Event) -> None:
        self.callback = callback
        self.stop_event = stop_event
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _loop(self) -> None:
        user32 = ctypes.windll.user32
        MOD_SHIFT = 0x0004
        candidates = [
            (self.MOD_CONTROL | self.MOD_ALT | self.MOD_NOREPEAT, self.VK_SPACE, "Ctrl+Alt+Espacio"),
            (self.MOD_CONTROL | MOD_SHIFT | self.MOD_NOREPEAT, 0x48, "Ctrl+Shift+H"),
            (self.MOD_ALT | self.MOD_NOREPEAT, 0x77, "Alt+F8"),
        ]
        bound_label = None
        for mods, vk, label in candidates:
            if user32.RegisterHotKey(None, self.HOTKEY_ID, mods, vk):
                bound_label = label
                break
        if not bound_label:
            log.warning("No se pudo registrar ningún hotkey global; usa clic en el avatar OOOOO.")
            return
        log.info("Push-to-Talk activo: %s (o clic en OOOOO)", bound_label)
        msg = wintypes.MSG()
        try:
            while not self.stop_event.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                        self.callback()
                else:
                    time.sleep(0.05)
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)


def ensure_wakeword_model():
    import openwakeword
    from openwakeword.model import Model

    models_dir = Path(openwakeword.__file__).parent / "resources" / "models"
    need = ["melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx"]
    if not all((models_dir / f).exists() for f in need):
        log.info("Descargando modelos ONNX de openwakeword (hey_jarvis)...")
        openwakeword.utils.download_models(["hey_jarvis"])
    return Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")


def _register_venv_cuda_dlls() -> None:
    """Si nvidia-cublas-cu12 / nvidia-cudnn-cu12 están en .venv, expone sus DLLs a CUDA."""
    sp = ROOT / ".venv" / "Lib" / "site-packages" / "nvidia"
    if not sp.exists():
        return
    for sub in ("cublas", "cudnn", "cuda_runtime"):
        bin_dir = sp / sub / "bin"
        if bin_dir.exists():
            try:
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass


def _has_cuda_runtime() -> bool:
    _register_venv_cuda_dlls()
    for dll in ("cublas64_12.dll", "cublas64_11.dll"):
        try:
            ctypes.WinDLL(dll)
            return True
        except OSError:
            continue
    return False


def load_whisper(model_size: str, device: str):
    from faster_whisper import WhisperModel

    if device == "auto":
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0 and _has_cuda_runtime():
                try:
                    m = WhisperModel(model_size, device="cuda", compute_type="float16")
                    log.info("Whisper '%s' cargado en GPU RTX CUDA (float16).", model_size)
                    return m
                except Exception as cuda_err:
                    log.info("CUDA no disponible para Whisper (%s); usando CPU int8.", cuda_err)
        except Exception:
            pass
        device = "cpu"

    compute = "float16" if device == "cuda" else "int8"
    m = WhisperModel(model_size, device=device, compute_type=compute)
    log.info("Whisper '%s' cargado en %s (%s).", model_size, device, compute)
    return m


def record_until_silence(
    audio_q: queue.Queue,
    pre_chunks: list | None = None,
    base_noise_rms: float = 0.008,
    max_wait_speech: float = 5.5,
    silence_sec: float = 1.15,
    max_total_sec: float = 18.0,
):
    """Captura audio desde la cola del micrófono hasta detectar silencio real (100% en RAM)."""
    import numpy as np

    frames = list(pre_chunks) if pre_chunks else []
    started_speaking = bool(pre_chunks)
    speech_streak = 3 if started_speaking else 0
    silence_chunks = 0
    chunk_sec = CHUNK_SAMPLES / SAMPLE_RATE
    max_silence_chunks = max(6, int(silence_sec / chunk_sec))
    max_chunks = int(max_total_sec / chunk_sec)
    wait_chunks = int(max_wait_speech / chunk_sec)
    threshold = max(0.014, base_noise_rms * 3.0)

    for idx in range(max_chunks):
        try:
            chunk = audio_q.get(timeout=0.4)
        except queue.Empty:
            continue
        frames.append(chunk)
        rms = float(np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2)))

        if rms >= threshold:
            speech_streak += 1
            if speech_streak >= 3:  # >=240 ms de voz real (ignora clics de mouse y ecos del beep)
                started_speaking = True
            silence_chunks = 0
        else:
            if not started_speaking:
                speech_streak = 0
                if idx >= wait_chunks:
                    break
            else:
                silence_chunks += 1
                if silence_chunks >= max_silence_chunks:
                    break

    if not started_speaking or not frames:
        return None
    pcm_i16 = np.concatenate(frames)
    return pcm_i16.astype(np.float32) / 32768.0


def run_self_test(args) -> int:
    import numpy as np
    import sounddevice as sd

    print("=== HELENA VOICE BRIDGE v3 (PRO) SELF-TEST ===")
    devs = sd.query_devices()
    in_dev = sd.default.device[0]
    out_dev = sd.default.device[1]
    print(f"AUDIO_IN:  [{in_dev}] {devs[in_dev]['name'] if in_dev is not None and in_dev >= 0 else 'NONE'}")
    print(f"AUDIO_OUT: [{out_dev}] {devs[out_dev]['name'] if out_dev is not None and out_dev >= 0 else 'NONE'}")

    brain = BrainClient(args.backend)
    ol_ok, ol_models = brain.ollama_available(autostart=True)
    print(f"BRAIN_BACKEND: {brain.active_backend()} (agy={bool(brain.agy_path)}, gemini_key={bool(brain.gemini_key)}, ollama={ol_ok} {ol_models[:2]})")
    print(f"VOICE_TOOLS: {len(vtools.TOOL_REGISTRY)} activas ({', '.join(list(vtools.TOOL_REGISTRY.keys())[:5])}...)")
    print(f"INSTANT_ROUTER_TEST: {vtools.try_instant_action('que hora es')}")

    prof = VoiceProfile.load(PROFILE_PATH)
    print(f"VOICE_PROFILE: {'LOADED (' + prof.wake_label + ')' if prof else 'NO ENTRENADO AUN (ejecuta train_voice.py)'}")
    print(f"ACTIVE_CONTEXT: {get_active_context()}")

    whisper = load_whisper(args.model, args.device)
    segs, info = whisper.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), language="es", initial_prompt=WHISPER_PROMPT)
    _ = list(segs)
    print(f"WHISPER_OK: model={args.model} lang={info.language} cuda_dlls={_has_cuda_runtime()}")

    tts_bytes = speak_in_ram("Hola, soy Helena, lista con herramientas activas en tu escritorio.", args.voice, play=args.play_test)
    print(f"TTS_RAM_OK: {tts_bytes} bytes MP3 decodificados en memoria (0 archivos en disco)")
    print("SELF_TEST: PASS")
    return 0


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(
        description="Helena v3 Pro — Avatar OOOOO + Voz con Manos + Cerebro Híbrido (Ollama RTX / Gemini / agy)."
    )
    parser.add_argument("--model", default=os.getenv("WHISPER_MODEL", "small"), help="Modelo faster-whisper (base=más rápido, small=más preciso)")
    parser.add_argument("--device", default=os.getenv("WHISPER_DEVICE", "auto"), choices=["auto", "cpu", "cuda"], help="Dispositivo Whisper")
    # Default: Paloma (#4, nativa 100% español, jamás cambia de idioma); Vivienne (#3) sigue disponible con "usa la voz de Vivienne"
    default_voice = load_saved_voice(os.getenv("TTS_VOICE", "es-US-PalomaNeural"))
    parser.add_argument("--voice", default=default_voice, help="Voz natural 100% español (default: Paloma #4; alternativa: Vivienne #3)")
    parser.add_argument("--preview-voices", action="store_true", help="Reproduce 4 voces HD humanas en español para elegir tu favorita")
    parser.add_argument("--backend", default=os.getenv("VOICE_BACKEND", "auto"), choices=["auto", "agy", "gemini", "ollama"], help="Backend IA")
    parser.add_argument("--threshold", type=float, default=float(os.getenv("WAKE_THRESHOLD", "0.42")), help="Umbral hey_jarvis (default: 0.42)")
    parser.add_argument("--followup-sec", type=float, default=float(os.getenv("FOLLOWUP_SEC", "6.5")), help="Segundos de escucha continua tras responder")
    parser.add_argument("--owner-only", action="store_true", help="Exige coincidencia estricta con tu huella vocal incluso en PTT")
    parser.add_argument("--any-voice", action="store_true", help="Permite que cualquier voz (no solo la tuya) active a Helena por voz")
    parser.add_argument("--still", action="store_true", help="El avatar OOOOO no deambula por el escritorio")
    parser.add_argument("--no-wake", action="store_true", help="Desactiva wake word (solo Push-to-Talk Ctrl+Alt+Espacio o clic)")
    parser.add_argument("--no-ui", action="store_true", help="Desactiva el avatar flotante")
    parser.add_argument("--save-audio", action="store_true", help="Guarda grabaciones WAV en logs/audio (DESACTIVADO por defecto)")
    parser.add_argument("--self-test", action="store_true", help="Ejecuta verificación sin iniciar el bucle permanente")
    parser.add_argument("--play-test", action="store_true", help="En --self-test, reproduce el audio de prueba por altavoces")
    args = parser.parse_args()

    if OFF_FLAG.exists() and not args.self_test:
        log.info("HELENA_OFF presente. Saliendo sin abrir micrófono.")
        return 0

    if args.preview_voices:
        samples = [
            ("en-US-AvaMultilingualNeural", "Hola, soy Helena con la voz de Ava. Sueno mucho más cálida, relajada y humana para acompañarte mientras programas."),
            ("en-US-EmmaMultilingualNeural", "Hola, soy Emma. Mi entonación es conversacional, cercana y natural en español."),
            ("fr-FR-VivienneMultilingualNeural", "Hola, soy Vivienne. Tengo un tono suave, elegante y muy tranquilo."),
            ("es-MX-DaliaNeural", "Hola, soy Dalia, la voz latina anterior para que compares la diferencia."),
        ]
        for v_id, msg in samples:
            print(f"Probando {v_id}...")
            speak_in_ram(msg, v_id, play=True)
            time.sleep(0.4)
        return 0

    if args.self_test:
        return run_self_test(args)

    import numpy as np
    import sounddevice as sd

    stop_event = threading.Event()
    ptt_event = threading.Event()

    def trigger_ptt() -> None:
        ptt_event.set()

    def trigger_quit() -> None:
        stop_event.set()

    class _NoopAvatar:
        def set_state(self, _st: str, _detail: str | None = None) -> None:
            pass

        def set_visibility(self, _mode: str) -> None:
            pass

        def close(self) -> None:
            pass

    def voice_worker(avatar) -> None:
        audio_q: queue.Queue = queue.Queue(maxsize=150)
        hotkey = Win32HotkeyListener(callback=trigger_ptt, stop_event=stop_event)
        hotkey.start()

        profile = VoiceProfile.load(PROFILE_PATH)
        if profile:
            log.info(
                "Perfil vocal cargado (%s | wake_thr=%.2f | spk_min=%.2f | ruido=%.4f)",
                profile.wake_label, profile.wake_threshold, profile.speaker_min_sim, profile.noise_floor_rms,
            )
        else:
            log.info("Sin perfil vocal aún. Ejecuta train_voice.py (o clic derecho en OOOOO) para entrenar con tu voz.")

        brain = BrainClient(args.backend)
        log.info("Backend IA activo: %s | Herramientas voz: %d", brain.active_backend(autostart_ollama=True), len(vtools.TOOL_REGISTRY))

        log.info(
            "Activación por voz CUDA activa: di 'Oye Helena', 'Hola Helena', 'Helena' o 'Despierta Helena' (solo o con tu orden en la misma frase)."
        )

        whisper = load_whisper(args.model, args.device)
        current_voice = args.voice
        notify_q: queue.Queue[str] = queue.Queue()
        trunner.TASK_MANAGER.set_notifier(lambda msg: notify_q.put(msg))
        log.info("Voz activa: %s (di 'cambia de voz' para alternar Vivienne/Paloma)", current_voice)
        avatar.set_state("standby", "Di 'Oye Helena'…")
        base_noise = profile.noise_floor_rms if profile else 0.008
        voice_gate = max(0.015, base_noise * 3.5)
        pre_buf: deque = deque(maxlen=6)
        speech_streak_idle = 0
        followup_until = 0.0
        cooldown_until = 0.0

        def audio_cb(indata, _frames, _time_info, status) -> None:
            if status:
                log.debug("Audio status: %s", status)
            chunk = indata[:, 0].copy()
            try:
                audio_q.put_nowait(chunk)
            except queue.Full:
                pass

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SAMPLES,
            callback=audio_cb,
        ):
            while not stop_event.is_set():
              try:
                if OFF_FLAG.exists():
                    log.info("HELENA_OFF detectado. Cerrando puente de voz.")
                    break

                # Anunciar notificaciones de tareas completadas en segundo plano (si no estás en reunión)
                if not notify_q.empty() and get_active_context().mode != "meeting":
                    try:
                        n_msg = notify_q.get_nowait()
                        log.info("Notificación asíncrona: %s", n_msg)
                        avatar.set_state("happy", "✨ Tarea lista")
                        speak_in_ram(n_msg, current_voice)
                        avatar.set_state("standby")
                        pre_buf.clear()
                        cooldown_until = time.time() + 0.65
                        continue
                    except queue.Empty:
                        pass

                now = time.time()
                triggered = False
                trigger_source = ""
                keep_pre = False
                need_wake_phrase = False

                if ptt_event.is_set():
                    ptt_event.clear()
                    triggered = True
                    trigger_source = "PTT"
                    speech_streak_idle = 0
                else:
                    try:
                        chunk = audio_q.get(timeout=0.18)
                    except queue.Empty:
                        if followup_until and now > followup_until:
                            followup_until = 0.0
                            avatar.set_state("standby")
                        continue

                    pre_buf.append(chunk)
                    rms = float(np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2)))

                    if followup_until > now:
                        if rms >= voice_gate:
                            speech_streak_idle += 1
                            if speech_streak_idle >= 2:
                                triggered = True
                                trigger_source = "continuo"
                                keep_pre = True
                                followup_until = 0.0
                                speech_streak_idle = 0
                        else:
                            speech_streak_idle = 0
                    else:
                        if followup_until:
                            followup_until = 0.0
                            avatar.set_state("standby")

                        if not args.no_wake and now >= cooldown_until:
                            if rms >= voice_gate:
                                speech_streak_idle += 1
                                if speech_streak_idle >= 3:
                                    # Si estás en videollamada (Zoom/Meet/Teams), no interrumpe manos libres
                                    if get_active_context().mode == "meeting":
                                        speech_streak_idle = 0
                                        pre_buf.clear()
                                        continue
                                    triggered = True
                                    trigger_source = "voz-manos-libres"
                                    keep_pre = True
                                    need_wake_phrase = True
                                    speech_streak_idle = 0
                            else:
                                speech_streak_idle = 0

                if not triggered:
                    continue

                if need_wake_phrase:
                    audio_f32 = record_until_silence(
                        audio_q,
                        pre_chunks=list(pre_buf),
                        base_noise_rms=base_noise,
                        silence_sec=0.80,
                        max_total_sec=12.0,
                    )
                    if audio_f32 is None:
                        continue

                    if profile is not None and not args.any_voice:
                        _, sim = profile.verify_speaker(audio_f32)
                        min_wake_sim = max(0.46, profile.speaker_min_sim - 0.08)
                        if sim < min_wake_sim:
                            log.debug("Habla ambiente ignorada (sim=%.2f < %.2f)", sim, min_wake_sim)
                            pre_buf.clear()
                            continue

                    segs, _ = whisper.transcribe(
                        audio_f32,
                        language="es",
                        vad_filter=True,
                        beam_size=2,
                        condition_on_previous_text=False,
                        initial_prompt=WHISPER_PROMPT,
                    )
                    heard = " ".join(s.text.strip() for s in segs).strip()
                    if not heard:
                        pre_buf.clear()
                        continue

                    if check_shutdown_command(heard):
                        log.info("Orden de apagado por voz: %s", heard)
                        OFF_FLAG.write_text(f"Apagado por voz: {datetime.now().isoformat()}\n", encoding="utf-8")
                        avatar.set_state("off", "HELENA_OFF")
                        try:
                            speak_in_ram("Entendido. Creé el interruptor Helena OFF y me apago.", args.voice)
                        except Exception:
                            pass
                        break

                    woke, inline_cmd = extract_wake_command(heard)
                    if not woke:
                        log.info("Escuchado sin palabra de activación (ignorado): %s", heard)
                        pre_buf.clear()
                        continue

                    log.info("Activada por voz ('%s') -> orden=%s", heard, inline_cmd or "(esperando orden)")
                    if inline_cmd and len(inline_cmd) >= 3:
                        text = inline_cmd
                    else:
                        avatar.set_state("listening", "Te escucho…")
                        beep(880, 90)
                        time.sleep(0.18)
                        while not audio_q.empty():
                            try:
                                audio_q.get_nowait()
                            except queue.Empty:
                                break
                        audio_cmd = record_until_silence(audio_q, base_noise_rms=base_noise)
                        beep(520, 75)
                        if audio_cmd is None:
                            avatar.set_state("standby")
                            continue
                        avatar.set_state("thinking")
                        segs2, _ = whisper.transcribe(
                            audio_cmd,
                            language="es",
                            vad_filter=True,
                            beam_size=3,
                            condition_on_previous_text=False,
                            initial_prompt=WHISPER_PROMPT,
                        )
                        text = " ".join(s.text.strip() for s in segs2).strip()
                        log.info("Transcrito (orden): %s", text or "(vacío)")
                        if not text:
                            cooldown_until = time.time() + 1.0
                            avatar.set_state("standby")
                            continue
                else:
                    log.info("Activada por %s", trigger_source)
                    avatar.set_state("listening")
                    if not keep_pre:
                        beep(880, 90)
                        time.sleep(0.18)
                        while not audio_q.empty():
                            try:
                                audio_q.get_nowait()
                            except queue.Empty:
                                break
                    audio_f32 = record_until_silence(
                        audio_q,
                        pre_chunks=list(pre_buf) if keep_pre else None,
                        base_noise_rms=base_noise,
                    )
                    beep(520, 75)

                    if audio_f32 is None:
                        avatar.set_state("standby")
                        continue

                    if profile is not None:
                        is_owner, sim = profile.verify_speaker(audio_f32)
                        log.info("Verificación de voz: owner=%s sim=%.2f (min=%.2f)", is_owner, sim, profile.speaker_min_sim)
                        if args.owner_only and not is_owner:
                            log.info("Ignorado por --owner-only.")
                            avatar.set_state("standby", "Voz no reconocida")
                            continue

                    if args.save_audio:
                        from scipy.io import wavfile
                        ad = LOG_DIR / "audio"
                        ad.mkdir(parents=True, exist_ok=True)
                        wav_path = ad / f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                        wavfile.write(wav_path, SAMPLE_RATE, (audio_f32 * 32767).astype(np.int16))

                    avatar.set_state("thinking")
                    segs, _ = whisper.transcribe(
                        audio_f32,
                        language="es",
                        vad_filter=True,
                        beam_size=3,
                        condition_on_previous_text=False,
                        initial_prompt=WHISPER_PROMPT,
                    )
                    text = " ".join(s.text.strip() for s in segs).strip()
                    log.info("Transcrito: %s", text or "(vacío)")

                    if not text:
                        cooldown_until = time.time() + 1.2
                        avatar.set_state("standby")
                        continue

                    _, maybe_cmd = extract_wake_command(text)
                    if maybe_cmd and len(maybe_cmd) >= 3:
                        text = maybe_cmd

                if check_shutdown_command(text):
                    OFF_FLAG.write_text(f"Apagado por voz: {datetime.now().isoformat()}\n", encoding="utf-8")
                    avatar.set_state("off", "HELENA_OFF")
                    try:
                        speak_in_ram("Entendido. Creé el interruptor Helena OFF y me apago.", args.voice)
                    except Exception:
                        pass
                    break

                # Cambio de voz en vivo por comando ('cambia de voz', 'usa la voz de Paloma/Vivienne')
                vsw = check_voice_switch_command(text, current_voice)
                if vsw is not None:
                    current_voice, vsw_reply = vsw
                    try:
                        VOICE_CHOICE_FILE.write_text(current_voice + "\n", encoding="utf-8")
                    except Exception:
                        pass
                    log.info("Voz cambiada a %s", current_voice)
                    avatar.set_state("happy", "🎙 Voz cambiada")
                    try:
                        speak_in_ram(vsw_reply, current_voice)
                    except Exception:
                        pass
                    avatar.set_state("standby")
                    cooldown_until = time.time() + 0.65
                    continue

                # Control de visibilidad por voz ('escóndete', 'aparece', 'modo automático')
                vis_cmd = check_visibility_command(text)
                if vis_cmd is not None:
                    vis_mode, vis_reply = vis_cmd
                    log.info("Visibilidad -> %s", vis_mode)
                    avatar.set_state("speaking", vis_reply)
                    try:
                        speak_in_ram(vis_reply, current_voice)
                    except Exception:
                        pass
                    avatar.set_state("standby")
                    avatar.set_visibility(vis_mode)
                    cooldown_until = time.time() + 0.8
                    continue

                # 1) Acción local instantánea (<0.5 s, 0 tokens, offline) -> 2) Cerebro IA con tool-calling
                avatar.set_state("thinking")
                instant = vtools.try_instant_action(text)
                if instant is not None:
                    reply = instant
                    brain.remember_turn(text, reply)
                    avatar.set_state("happy", "✨ ¡Listo!")
                    time.sleep(0.35)
                else:
                    reply = brain.ask(text)
                log.info("Respuesta: %s", reply)

                avatar.set_state("speaking", reply)
                try:
                    speak_in_ram(reply, current_voice)
                except Exception as e:
                    log.error("Error TTS: %s", e)

                pre_buf.clear()
                while not audio_q.empty():
                    try:
                        audio_q.get_nowait()
                    except queue.Empty:
                        break
                cooldown_until = time.time() + 0.65

                if args.followup_sec > 0 and not reply.startswith("De nada"):
                    followup_until = time.time() + args.followup_sec
                    avatar.set_state("followup", "Te escucho…")
                else:
                    avatar.set_state("standby")
              except Exception as loop_err:
                log.error("Error recuperable en ciclo principal: %s", loop_err)
                avatar.set_state("standby")
                time.sleep(1.2)

        avatar.close()
        log.info("Puente de voz finalizado.")

    if args.no_ui:
        try:
            voice_worker(_NoopAvatar())
        except KeyboardInterrupt:
            stop_event.set()
        return 0

    return run_avatar_app(
        worker_fn=voice_worker,
        on_ptt=trigger_ptt,
        on_quit=trigger_quit,
        roam=not args.still,
    )


if __name__ == "__main__":
    raise SystemExit(main())

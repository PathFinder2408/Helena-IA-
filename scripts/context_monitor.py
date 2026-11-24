#!/usr/bin/env python3
"""
Helena — Monitor ligero de contexto de ventana activa en Windows 11 (Win32 puro).
Clasifica lo que está haciendo el usuario ('fullscreen', 'meeting', 'focus', 'casual')
para que el avatar OOOOO se esconda o pase a modo discreto sin molestar.
Privacidad: solo inspecciona nombre del ejecutable, título de ventana y geometría; no guarda nada.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import re

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

MEETING_PROCS = {"zoom.exe", "ms-teams.exe", "teams.exe", "webex.exe"}
MEETING_TITLE_RE = re.compile(
    r"(google meet|meet\.google\.com|zoom meeting|microsoft teams|llamada|reuni[oó]n|huddle)",
    re.I,
)
FOCUS_PROCS = {
    "code.exe",
    "antigravity.exe",
    "cursor.exe",
    "pycharm64.exe",
    "idea64.exe",
    "devenv.exe",
    "windowsterminal.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "figma.exe",
    "winword.exe",
    "excel.exe",
    "notion.exe",
    "obsidian.exe",
}
MEDIA_FULLSCREEN_IGNORE = {"explorer.exe", "shellexperiencehost.exe", "searchhost.exe", "applicationframehost.exe"}


@dataclass
class ActiveContext:
    mode: str       # 'fullscreen' | 'meeting' | 'focus' | 'casual'
    process: str    # ej. 'code.exe'
    title: str      # título truncado
    is_fullscreen: bool


def _get_process_name(pid: int) -> str:
    if pid <= 0:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            path = buf.value
            return path.rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(handle)
    return ""


def get_active_context() -> ActiveContext:
    """Inspecciona la ventana en primer plano de Windows y retorna el modo sugerido para Helena."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ActiveContext("casual", "", "", False)

        # Título
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            tbuf = ctypes.create_unicode_buffer(min(length + 1, 256))
            user32.GetWindowTextW(hwnd, tbuf, len(tbuf))
            title = tbuf.value.strip()

        # Proceso
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = _get_process_name(pid.value)

        # Pantalla completa real (videos, juegos, presentaciones)
        rect = wintypes.RECT()
        is_fs = False
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if proc not in MEDIA_FULLSCREEN_IGNORE and w >= sw - 4 and h >= sh - 4 and rect.left <= 4 and rect.top <= 4:
                is_fs = True

        # Clasificación inteligente
        if proc in MEETING_PROCS or MEETING_TITLE_RE.search(title):
            return ActiveContext("meeting", proc, title[:80], is_fs)
        if is_fs:
            return ActiveContext("fullscreen", proc, title[:80], True)
        if proc in FOCUS_PROCS:
            return ActiveContext("focus", proc, title[:80], False)
        return ActiveContext("casual", proc, title[:80], False)
    except Exception:
        return ActiveContext("casual", "", "", False)


if __name__ == "__main__":
    print(get_active_context())

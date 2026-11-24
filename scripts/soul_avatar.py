#!/usr/bin/env python3
"""
Helena — Avatar HiDPI estilo 'OOOOO' (Elio, Disney/Pixar) v2 Animado.
Incluye:
  - Contorno líquido con morphing orgánico (efecto metaballs / SDF)
  - Circuitos internos bioluminiscentes con pulsos de datos viajando en tiempo real
  - Física spring-damper (squash & stretch, inclinación al moverse/arrastrar y rebote)
  - Gotitas satélite translúcidas que se desprenden y fusionan con el cuerpo
  - Expresiones Pixar: standby, curious, happy (ojos ^ ^ + saltito), followup,
    listening, thinking (circuitos en cascada + halo holográfico) y speaking.
Renderizado 100% anti-aliased en PyQt6 (WA_TranslucentBackground, 60 FPS, hilo principal).
"""
from __future__ import annotations

import argparse
import math
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

ROOT = Path(r"C:\Jarvis")
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from context_monitor import ActiveContext, get_active_context

VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
TRAIN_SCRIPT = ROOT / "scripts" / "train_voice.py"
DASHBOARD_HTML = ROOT / "dashboard.html"


# Paletas OOOOO: (glow_rgb, core_hex, mid_hex, edge_hex, rim_hex, blush_rgb, circuit_rgb, label)
PALETTES = {
    "standby": (
        (64, 190, 255),
        "#f4fcff",
        "#9be0ff",
        "#3daeff",
        "#e4f7ff",
        (210, 185, 255),
        (185, 245, 255),
        "Helena · En espera",
    ),
    "happy": (
        (56, 224, 255),
        "#f8feff",
        "#99f0ff",
        "#22c7ff",
        "#ffffff",
        (255, 175, 225),
        (255, 248, 175),
        "✨ ¡Listo!",
    ),
    "followup": (
        (45, 226, 210),
        "#f2fffe",
        "#8cf5e8",
        "#2dd4bf",
        "#d7fffb",
        (180, 230, 255),
        (190, 255, 245),
        "Te escucho…",
    ),
    "listening": (
        (255, 110, 175),
        "#fff5fb",
        "#ffbadc",
        "#f472b6",
        "#ffe3f1",
        (255, 150, 200),
        (255, 235, 180),
        "🎙 Escuchando…",
    ),
    "thinking": (
        (158, 122, 255),
        "#f7f4ff",
        "#c8b4ff",
        "#7c4dff",
        "#ede9fe",
        (196, 181, 253),
        (125, 245, 255),
        "⚡ Procesando…",
    ),
    "speaking": (
        (52, 224, 175),
        "#f2fff9",
        "#8cf2cf",
        "#2ec997",
        "#d8ffef",
        (167, 243, 208),
        (215, 255, 240),
        "🔊 Hablando…",
    ),
    "off": (
        (120, 140, 170),
        "#e2e8f0",
        "#94a3b8",
        "#64748b",
        "#cbd5e1",
        (148, 163, 184),
        (203, 213, 225),
        "⏻ Apagando…",
    ),
}


class AvatarBridge(QObject):
    """Puente thread-safe para controlar el avatar desde cualquier hilo worker."""

    state_changed = pyqtSignal(str, str)
    visibility_changed = pyqtSignal(str)  # 'hide' | 'show' | 'auto'
    quit_requested = pyqtSignal()

    def set_state(self, state: str, detail: str | None = None) -> None:
        self.state_changed.emit(state, detail or "")

    def set_visibility(self, mode: str) -> None:
        self.visibility_changed.emit(mode)

    def close(self) -> None:
        self.quit_requested.emit()


def _liquid_squircle_path(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    dt: float,
    morph_amp: float = 1.0,
) -> QPainterPath:
    """Silueta líquida tipo OOOOO con ondulación orgánica de puntos de control (metaball feel)."""
    # Armónicos suaves desfasados en cada cuadrante para efecto fluido real
    m_top = math.sin(dt * 2.9) * 1.1 * morph_amp
    m_bot = math.cos(dt * 2.5 + 1.1) * 1.1 * morph_amp
    m_r = math.sin(dt * 3.3 + 2.2) * 1.2 * morph_amp
    m_l = math.cos(dt * 3.1 + 0.5) * 1.2 * morph_amp

    w_r = rx + m_r
    w_l = rx + m_l
    h_t = ry + m_top
    h_b = ry + m_bot

    kx_r = w_r * 0.73
    kx_l = w_l * 0.73
    ky_t = h_t * 0.70
    ky_b = h_b * 0.72

    path = QPainterPath()
    path.moveTo(cx, cy - h_t)
    path.cubicTo(cx + kx_r, cy - h_t, cx + w_r, cy - ky_t, cx + w_r, cy + h_b * 0.04)
    path.cubicTo(cx + w_r, cy + ky_b * 1.04, cx + kx_r * 0.96, cy + h_b, cx, cy + h_b)
    path.cubicTo(cx - kx_l * 0.96, cy + h_b, cx - w_l, cy + ky_b * 1.04, cx - w_l, cy + h_b * 0.04)
    path.cubicTo(cx - w_l, cy - ky_t, cx - kx_l, cy - h_t, cx, cy - h_t)
    path.closeSubpath()
    return path


def _draw_internal_circuitry(
    painter: QPainter,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    dt: float,
    state: str,
    circuit_rgb: tuple[int, int, int],
) -> None:
    """Dibuja los circuitos bioluminiscentes internos característicos de OOOOO (Elio)."""
    is_active = state in ("thinking", "listening", "speaking", "happy")
    base_alpha = 118 if state == "thinking" else (92 if is_active else 62)
    speed = 2.6 if state == "thinking" else (1.8 if is_active else 0.75)

    # Trazos simétricos finos estilo circuito cuántico orgánico
    traces = [
        # Superior izquierdo -> borde
        [(-rx * 0.85, -ry * 0.28), (-rx * 0.52, -ry * 0.28), (-rx * 0.36, -ry * 0.58), (-rx * 0.10, -ry * 0.58)],
        # Superior derecho -> borde
        [(rx * 0.85, -ry * 0.28), (rx * 0.52, -ry * 0.28), (rx * 0.36, -ry * 0.58), (rx * 0.10, -ry * 0.58)],
        # Inferior izquierdo
        [(-rx * 0.78, ry * 0.42), (-rx * 0.46, ry * 0.42), (-rx * 0.30, ry * 0.68), (-rx * 0.06, ry * 0.68)],
        # Inferior derecho
        [(rx * 0.78, ry * 0.42), (rx * 0.46, ry * 0.42), (rx * 0.30, ry * 0.68), (rx * 0.06, ry * 0.68)],
        # Arco superior corona
        [(-rx * 0.24, -ry * 0.80), (0.0, -ry * 0.68), (rx * 0.24, -ry * 0.80)],
    ]

    r_c, g_c, b_c = circuit_rgb
    for ti, pts in enumerate(traces):
        path = QPainterPath()
        p0 = QPointF(cx + pts[0][0], cy + pts[0][1])
        path.moveTo(p0)
        for px, py in pts[1:]:
            path.lineTo(QPointF(cx + px, cy + py))

        # Trazo base translúcido
        pen = QPen(QColor(r_c, g_c, b_c, base_alpha), 1.15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Nodos brillantes en extremos
        end_p = QPointF(cx + pts[-1][0], cy + pts[-1][1])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, min(230, base_alpha + 70))))
        painter.drawEllipse(end_p, 1.5, 1.5)

        # Pulso de luz viajando a lo largo del circuito
        prog = (dt * speed + ti * 0.23) % 1.0
        pt_pulse = path.pointAtPercent(prog)
        g_p = QRadialGradient(pt_pulse, 5.2)
        g_p.setColorAt(0.0, QColor(255, 255, 255, 235 if is_active else 165))
        g_p.setColorAt(0.5, QColor(r_c, g_c, b_c, 145 if is_active else 80))
        g_p.setColorAt(1.0, QColor(r_c, g_c, b_c, 0))
        painter.setBrush(QBrush(g_p))
        painter.drawEllipse(pt_pulse, 5.2, 5.2)


def paint_ooooo(
    painter: QPainter,
    width: int,
    height: int,
    state: str,
    dt: float,
    look_x: float = 0.0,
    look_y: float = 0.0,
    blink_factor: float = 0.0,
    tilt_deg: float = 0.0,
    squash_x: float = 1.0,
    squash_y: float = 1.0,
    bounce_y: float = 0.0,
    label_text: str = "",
    label_alpha: float = 0.0,
) -> None:
    """Renderiza a OOOOO con física líquida, circuitos internos pulsantes y expresiones Pixar."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    glow_rgb, core_hex, mid_hex, edge_hex, rim_hex, blush_rgb, circuit_rgb, default_lbl = PALETTES.get(
        state, PALETTES["standby"]
    )

    cx = width / 2.0
    bob_amp = 4.2 if state not in ("listening", "happy") else (2.2 if state == "listening" else 6.0)
    bob_spd = 2.4 if state not in ("speaking", "happy") else (5.6 if state == "speaking" else 7.2)
    cy = 58.0 + math.sin(dt * bob_spd) * bob_amp + bounce_y

    # Respiración gelatinosa orgánica + squash & stretch
    breath = math.sin(dt * (6.4 if state == "speaking" else (4.2 if state == "thinking" else 2.6)))
    rx = (34.5 + breath * (1.8 if state == "speaking" else 0.8)) * squash_x
    ry = (25.5 - breath * (1.3 if state == "speaking" else 0.55)) * squash_y
    morph_amp = 2.2 if state == "thinking" else (1.5 if state in ("speaking", "happy") else 0.85)

    # 1. Halo ambiental bioluminiscente exterior
    glow_r = 58.0 + math.sin(dt * 3.0) * 3.2
    g_halo = QRadialGradient(QPointF(cx, cy + 2), glow_r)
    g_halo.setColorAt(0.0, QColor(glow_rgb[0], glow_rgb[1], glow_rgb[2], 150))
    g_halo.setColorAt(0.55, QColor(glow_rgb[0], glow_rgb[1], glow_rgb[2], 62))
    g_halo.setColorAt(0.84, QColor(glow_rgb[0], glow_rgb[1], glow_rgb[2], 16))
    g_halo.setColorAt(1.0, QColor(glow_rgb[0], glow_rgb[1], glow_rgb[2], 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(g_halo))
    painter.drawEllipse(QPointF(cx, cy + 2), glow_r, glow_r * 0.88)

    # 2. Ondas líquidas translúcidas (listening / speaking / followup) o anillo holográfico (thinking)
    if state in ("listening", "speaking", "followup"):
        for idx in range(2):
            phase = (dt * 1.2 + idx * 0.5) % 1.0
            fade = int((1.0 - phase) * 170)
            wrx = rx + 5.5 + phase * 22.0
            wry = ry + 4.5 + phase * 18.0
            painter.setPen(QPen(QColor(glow_rgb[0], glow_rgb[1], glow_rgb[2], fade), 2.0 - phase * 0.9))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(_liquid_squircle_path(cx, cy, wrx, wry, dt, morph_amp=0.6))
    elif state == "thinking":
        # Anillo holográfico inclinado rotando alrededor de la supercomputadora líquida
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(math.sin(dt * 1.4) * 14.0)
        pen_holo = QPen(QColor(circuit_rgb[0], circuit_rgb[1], circuit_rgb[2], 135), 1.4, Qt.PenStyle.DashLine)
        pen_holo.setDashOffset(-dt * 12.0)
        painter.setPen(pen_holo)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), rx + 12.5, ry + 11.0)
        painter.restore()

    # 3. Gotitas satélite líquidas (mini-metaballs que se desprenden y fusionan suavemente)
    n_drops = 4 if state in ("thinking", "happy") else 2
    for i in range(n_drops):
        ang = dt * (1.9 if state in ("thinking", "happy") else 0.75) + i * (math.tau / n_drops)
        orbit_pulse = 0.5 + 0.5 * math.sin(dt * 2.2 + i * 1.7)
        drx = rx + 4.5 + orbit_pulse * (10.5 if state in ("thinking", "happy") else 6.5)
        dry = ry + 3.5 + orbit_pulse * 8.0
        dx_d = cx + math.cos(ang) * drx
        dy_d = cy + math.sin(ang) * dry
        rad_d = (3.4 if state in ("thinking", "happy") else 2.5) * (0.7 + 0.35 * (1.0 - orbit_pulse))
        g_d = QRadialGradient(QPointF(dx_d - 0.8, dy_d - 0.8), rad_d * 1.4)
        g_d.setColorAt(0.0, QColor(255, 255, 255, 235))
        g_d.setColorAt(0.55, QColor(mid_hex))
        ec = QColor(edge_hex)
        ec.setAlpha(185)
        g_d.setColorAt(1.0, ec)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(g_d))
        painter.drawEllipse(QPointF(dx_d, dy_d), rad_d, rad_d)

    # Transformación de cuerpo (inclinación curiosa / inercia al moverse)
    painter.save()
    painter.translate(cx, cy)
    painter.rotate(tilt_deg)
    painter.translate(-cx, -cy)

    # 4. Patitas / bracitos chiquititos flotantes (saludan rápido cuando está happy!)
    foot_y = cy + ry + 0.8
    for side in (-1, 1):
        spd_f = 10.5 if state == "happy" else 3.2
        amp_f = 3.2 if state == "happy" else 1.4
        phase_f = dt * spd_f + (0.0 if side < 0 else 1.4)
        fx = cx + side * 11.4 + math.sin(phase_f) * (2.2 if state == "happy" else 0.8)
        fy = foot_y + math.cos(phase_f) * amp_f
        g_foot = QRadialGradient(QPointF(fx - 1.5, fy - 2.0), 9.0)
        g_foot.setColorAt(0.0, QColor(core_hex))
        g_foot.setColorAt(0.55, QColor(mid_hex))
        edge_c = QColor(edge_hex)
        edge_c.setAlpha(215)
        g_foot.setColorAt(1.0, edge_c)
        painter.setPen(QPen(QColor(235, 250, 255, 175), 0.95))
        painter.setBrush(QBrush(g_foot))
        painter.drawEllipse(QPointF(fx, fy), 5.0, 6.2)

    # 5. Cuerpo principal squircle líquido con iluminación 3D subsuperficial
    body_path = _liquid_squircle_path(cx, cy, rx, ry, dt, morph_amp=morph_amp)
    g_body = QRadialGradient(QPointF(cx - rx * 0.22, cy - ry * 0.30), rx * 1.48)
    c_core = QColor(core_hex)
    c_core.setAlpha(246)
    c_mid = QColor(mid_hex)
    c_mid.setAlpha(234)
    c_edge = QColor(edge_hex)
    c_edge.setAlpha(222)
    c_outer = QColor(edge_hex).darker(112)
    c_outer.setAlpha(230)
    g_body.setColorAt(0.0, c_core)
    g_body.setColorAt(0.50, c_mid)
    g_body.setColorAt(0.85, c_edge)
    g_body.setColorAt(1.0, c_outer)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(g_body))
    painter.drawPath(body_path)

    # 6. Capas internas recortadas al cuerpo: CIRCUITOS BIOLUMINISCENTES + iridiscencia + brillo 3D
    painter.save()
    painter.setClipPath(body_path)

    _draw_internal_circuitry(painter, cx, cy, rx, ry, dt, state, circuit_rgb)

    # Brillo iridiscente suave inferior-derecho
    g_iri = QRadialGradient(QPointF(cx + rx * 0.32, cy + ry * 0.55), rx * 0.95)
    g_iri.setColorAt(0.0, QColor(blush_rgb[0], blush_rgb[1], blush_rgb[2], 118))
    g_iri.setColorAt(0.65, QColor(blush_rgb[0], blush_rgb[1], blush_rgb[2], 32))
    g_iri.setColorAt(1.0, QColor(blush_rgb[0], blush_rgb[1], blush_rgb[2], 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(g_iri))
    painter.drawRect(QRectF(cx - rx - 4, cy - ry - 4, (rx + 4) * 2, (ry + 4) * 2))

    # Brillo especular vítreo superior-izquierdo
    g_spec = QLinearGradient(QPointF(cx - rx * 0.55, cy - ry * 0.95), QPointF(cx - rx * 0.15, cy - ry * 0.10))
    g_spec.setColorAt(0.0, QColor(255, 255, 255, 190))
    g_spec.setColorAt(0.55, QColor(255, 255, 255, 50))
    g_spec.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(QBrush(g_spec))
    painter.drawEllipse(QPointF(cx - rx * 0.25, cy - ry * 0.52), rx * 0.54, ry * 0.32)

    # Subsurface bounce light inferior
    g_bot = QLinearGradient(QPointF(cx, cy + ry * 0.35), QPointF(cx, cy + ry))
    g_bot.setColorAt(0.0, QColor(255, 255, 255, 0))
    g_bot.setColorAt(1.0, QColor(225, 248, 255, 115))
    painter.setBrush(QBrush(g_bot))
    painter.drawEllipse(QPointF(cx, cy + ry * 0.78), rx * 0.78, ry * 0.36)
    painter.restore()

    # Contorno cristalino HiDPI
    rim_c = QColor(rim_hex)
    rim_c.setAlpha(210)
    painter.setPen(QPen(rim_c, 1.35))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(body_path)

    # 7. Rubor suave en mejillas
    cheek_y = cy + 5.0 + look_y * 0.35
    cheek_alpha = 115 if state == "happy" else 72
    for side in (-1, 1):
        ch_x = cx + side * 21.0 + look_x * 0.45
        g_ch = QRadialGradient(QPointF(ch_x, cheek_y), 7.5)
        g_ch.setColorAt(0.0, QColor(255, 160, 210, cheek_alpha))
        g_ch.setColorAt(1.0, QColor(255, 160, 210, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(g_ch))
        painter.drawEllipse(QPointF(ch_x, cheek_y), 7.5, 4.8)

    # 8. Ojos expresivos Pixar (incluye arcos felices ^ ^ en modo happy!)
    eye_y = cy - 1.5 + look_y * 0.65
    eye_sep = 15.8
    for side in (-1, 1):
        ex = cx + side * eye_sep + look_x * 0.75
        if state == "happy" or blink_factor > 0.75:
            painter.setPen(QPen(QColor("#0a1628"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            arc_path = QPainterPath()
            if state == "happy":
                # Ojos felices ^ ^ bien expresivos
                arc_path.moveTo(ex - 4.8, eye_y + 1.6)
                arc_path.quadTo(ex, eye_y - 4.4, ex + 4.8, eye_y + 1.6)
            else:
                arc_path.moveTo(ex - 4.4, eye_y + 0.5)
                arc_path.quadTo(ex, eye_y - 2.4, ex + 4.4, eye_y + 0.5)
            painter.drawPath(arc_path)
        else:
            er_x = 4.8 if state == "listening" else 4.3
            er_y = (5.5 if state == "listening" else 4.9) * (1.0 - blink_factor * 0.85)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(30, 95, 165, 42)))
            painter.drawEllipse(QPointF(ex, eye_y + 0.4), er_x + 1.2, er_y + 1.2)

            g_eye = QRadialGradient(QPointF(ex - 1.0, eye_y - 1.2), er_y * 1.4)
            g_eye.setColorAt(0.0, QColor("#1b2b4a"))
            g_eye.setColorAt(0.45, QColor("#091120"))
            g_eye.setColorAt(1.0, QColor("#040811"))
            painter.setBrush(QBrush(g_eye))
            painter.drawEllipse(QPointF(ex, eye_y), er_x, er_y)

            painter.setBrush(QBrush(QColor(255, 255, 255, 248)))
            painter.drawEllipse(QPointF(ex - 1.5 + look_x * 0.15, eye_y - 1.6 + look_y * 0.15), 1.65, 1.65)
            painter.setBrush(QBrush(QColor(200, 245, 255, 200)))
            painter.drawEllipse(QPointF(ex + 1.5, eye_y + 1.5), 0.8, 0.8)

    # 9. Boquita expresiva reactiva
    mx = cx + look_x * 0.5
    my = cy + 6.2 + look_y * 0.45
    if state == "speaking":
        open_h = 1.6 + abs(math.sin(dt * 14.5)) * 3.5
        painter.setPen(QPen(QColor("#0b1930"), 1.3))
        painter.setBrush(QBrush(QColor("#17345e")))
        painter.drawEllipse(QPointF(mx, my + 0.5), 3.7, open_h)
    elif state == "listening":
        painter.setPen(QPen(QColor("#102342"), 1.5))
        painter.setBrush(QBrush(QColor(25, 65, 120, 115)))
        painter.drawEllipse(QPointF(mx, my + 0.8), 2.6, 2.9)
    elif state == "thinking":
        painter.setPen(QPen(QColor("#102342"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        mp = QPainterPath()
        mp.moveTo(mx - 3.8, my + 0.8)
        mp.quadTo(mx, my - 1.0, mx + 3.8, my + 0.2)
        painter.drawPath(mp)
    elif state == "happy":
        painter.setPen(QPen(QColor("#0f2a50"), 1.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(QBrush(QColor(255, 145, 190, 150)))
        mp = QPainterPath()
        mp.moveTo(mx - 5.2, my - 0.6)
        mp.quadTo(mx, my + 5.2, mx + 5.2, my - 0.6)
        mp.closeSubpath()
        painter.drawPath(mp)
    else:
        painter.setPen(QPen(QColor(18, 52, 96, 185), 1.55, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        mp = QPainterPath()
        mp.moveTo(mx - 4.4, my - 0.3)
        mp.quadTo(mx, my + 3.1, mx + 4.4, my - 0.3)
        painter.drawPath(mp)

    painter.restore()  # fin rotación cuerpo

    # 10. Pastilla glassmorphism flotante debajo del avatar
    if label_alpha > 0.04:
        txt = (label_text or default_lbl)[:22]
        a_bg = int(198 * label_alpha)
        a_bd = int(190 * label_alpha)
        a_tx = int(248 * label_alpha)
        pill_rect = QRectF(10.0, height - 24.0, width - 20.0, 20.0)
        painter.setPen(QPen(QColor(glow_rgb[0], glow_rgb[1], glow_rgb[2], a_bd), 1.15))
        painter.setBrush(QBrush(QColor(10, 17, 32, a_bg)))
        painter.drawRoundedRect(pill_rect, 10.0, 10.0)
        font = QFont("Segoe UI", 7)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(244, 250, 255, a_tx))
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, txt)


class OooooAvatarWindow(QWidget):
    """Ventana flotante transparente sin bordes (60 FPS) con física líquida en hilo principal."""

    W = 140
    H = 138

    def __init__(self, bridge: AvatarBridge, on_ptt=None, on_quit=None, roam: bool = True) -> None:
        super().__init__(None)
        self.bridge = bridge
        self.on_ptt = on_ptt or (lambda: None)
        self.on_quit = on_quit or (lambda: None)
        self.roam_enabled = roam

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        screen = QApplication.primaryScreen().availableGeometry()
        self.screen_rect = screen
        self.pos_x = float(max(screen.left() + 20, screen.right() - self.W - 28))
        self.pos_y = float(screen.top() + 72)
        self.target_x = self.pos_x
        self.target_y = self.pos_y
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.move(int(self.pos_x), int(self.pos_y))

        self.state = "standby"
        self.label_text = "Helena lista"
        self.t0 = time.time()
        self.label_until = self.t0 + 2.8
        self.label_alpha = 1.0
        self.hovering = False

        self.dragging = False
        self.drag_moved = False
        self.drag_offset = QPoint(0, 0)
        self.last_drag_pos = QPointF(self.pos_x, self.pos_y)

        # Variables de física gelatinosa (spring-damper)
        self.tilt_deg = 0.0
        self.squash_x = 1.0
        self.squash_y = 1.0
        self.squash_vel = 0.0
        self.bounce_y = 0.0
        self.curious_tilt = 0.0
        self.next_curious = self.t0 + 5.0

        self.next_wander = self.t0 + 3.0
        self.next_blink = self.t0 + random.uniform(2.2, 4.8)
        self.blink_start = 0.0
        self.look_x = 0.0
        self.look_y = 0.0
        self._showcase_running = False

        # Inteligencia contextual: se esconde en pantalla completa/reuniones y se atenúa en IDEs/foco
        self.smart_context = True
        self.manual_hidden = False
        self.current_ctx = ActiveContext("casual", "", "", False)
        self.last_ctx_check = 0.0
        self.current_opacity = 0.95

        self.bridge.state_changed.connect(self._on_state_changed)
        self.bridge.visibility_changed.connect(self._on_visibility_changed)
        self.bridge.quit_requested.connect(self._on_quit_signal)

        self._init_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)  # ~60 FPS

    def _build_tray_icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.scale(64 / 140.0, 64 / 138.0)
        paint_ooooo(p, 140, 138, "standby", 0.3, label_alpha=0.0)
        p.end()
        return QIcon(pix)

    def _init_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self._build_tray_icon(), self)
        tray.setToolTip("Helena — Activa en segundo plano (di 'Oye Helena')")
        tray_menu = QMenu()
        tray_menu.addAction("🎙 Hablar ahora", self.on_ptt)
        tray_menu.addAction("✨ Mostrar avatar", lambda: self._on_visibility_changed("show"))
        tray_menu.addAction("👻 Esconder avatar (sigue escuchando)", lambda: self._on_visibility_changed("hide"))
        tray_menu.addAction("🧠 Modo inteligente automático", lambda: self._on_visibility_changed("auto"))
        tray_menu.addSeparator()
        tray_menu.addAction("⏻ Cerrar Helena", self._quit_all)
        tray.setContextMenu(tray_menu)
        tray.activated.connect(self._on_tray_click)
        tray.show()
        self.tray = tray

    def _on_tray_click(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.on_ptt()
            else:
                self._on_visibility_changed("show")

    def _quit_all(self) -> None:
        self.on_quit()
        self._on_quit_signal()

    def _on_visibility_changed(self, mode: str) -> None:
        m = mode.lower().strip()
        if m == "hide":
            self.manual_hidden = True
            self.hide()
        elif m == "show":
            self.manual_hidden = False
            self.setWindowOpacity(0.95)
            self.show()
            self._trigger_jiggle(0.16)
        elif m == "auto":
            self.manual_hidden = False
            self.smart_context = True
            self.show()

    def _trigger_jiggle(self, strength: float = 0.16) -> None:
        self.squash_vel += strength

    def _on_state_changed(self, new_state: str, detail: str) -> None:
        if new_state != self.state:
            self._trigger_jiggle(0.18 if new_state in ("happy", "listening") else 0.10)
        self.state = new_state
        pal = PALETTES.get(new_state, PALETTES["standby"])
        self.label_text = detail if detail else pal[7]
        now = time.time()
        self.label_until = now + (2.6 if new_state == "standby" else 999.0)

        # Si Helena entra en interacción activa, aparece visible aunque estuviera escondida
        if new_state in ("listening", "thinking", "speaking", "happy", "followup"):
            if not self.isVisible():
                self.show()
            self.setWindowOpacity(0.96)
        elif new_state == "off":
            if self.tray:
                self.tray.hide()
            QTimer.singleShot(350, QApplication.quit)

    def _on_quit_signal(self) -> None:
        self.timer.stop()
        if self.tray:
            self.tray.hide()
        self.close()
        QApplication.quit()

    def _pick_edge_target(self) -> tuple[float, float]:
        r = self.screen_rect
        zone = random.choice(["right", "right", "top", "left", "bottom_right"])
        if zone == "right":
            return (
                float(r.right() - self.W - random.randint(14, 52)),
                float(random.randint(r.top() + 40, max(r.top() + 80, r.bottom() - self.H - 40))),
            )
        if zone == "top":
            return (
                float(random.randint(r.left() + int(r.width() * 0.25), max(r.left() + 80, r.right() - self.W - 24))),
                float(r.top() + random.randint(16, 72)),
            )
        if zone == "left":
            return (
                float(r.left() + random.randint(14, 54)),
                float(random.randint(r.top() + 40, max(r.top() + 80, r.bottom() - self.H - 40))),
            )
        return (
            float(r.right() - self.W - random.randint(20, 120)),
            float(max(r.top() + 40, r.bottom() - self.H - random.randint(24, 150))),
        )

    def _tick(self) -> None:
        now = time.time()
        dt = now - self.t0

        # Evaluar contexto de ventana activa cada 1.2 s en modo espera
        if self.state == "standby" and (now - self.last_ctx_check) >= 1.2:
            self.last_ctx_check = now
            self.current_ctx = get_active_context()

            if self.manual_hidden:
                if self.isVisible():
                    self.hide()
                return

            if self.smart_context:
                if self.current_ctx.mode in ("fullscreen", "meeting"):
                    if self.isVisible():
                        self.hide()
                    return
                elif not self.isVisible():
                    self.show()

        if not self.isVisible():
            return

        # Opacidad y comportamiento según contexto (discreto al programar en IDE/terminal)
        in_focus = self.smart_context and self.state == "standby" and self.current_ctx.mode == "focus" and not self.hovering
        target_op = 0.38 if in_focus else 0.95
        if abs(target_op - self.current_opacity) > 0.01:
            self.current_opacity += (target_op - self.current_opacity) * 0.12
            self.setWindowOpacity(self.current_opacity)

        # En modo foco, estacionar tranquila en la esquina superior derecha para no distraer
        if in_focus and not self.dragging:
            corner_x = float(max(self.screen_rect.left() + 20, self.screen_rect.right() - self.W - 22))
            corner_y = float(self.screen_rect.top() + 56)
            dx = corner_x - self.pos_x
            dy = corner_y - self.pos_y
            dist = math.hypot(dx, dy)
            if dist > 2.0:
                spd = min(2.2, max(0.3, dist * 0.03))
                self.vel_x = (dx / dist) * spd
                self.vel_y = (dy / dist) * spd
                self.pos_x += self.vel_x
                self.pos_y += self.vel_y
                self.move(int(self.pos_x), int(self.pos_y))
            else:
                self.vel_x *= 0.8
                self.vel_y *= 0.8
        elif self.roam_enabled and not self.dragging and self.state in ("standby", "speaking", "happy"):
            if now >= self.next_wander:
                self.target_x, self.target_y = self._pick_edge_target()
                self.next_wander = now + random.uniform(7.5, 14.0)
            dx = self.target_x - self.pos_x
            dy = self.target_y - self.pos_y
            dist = math.hypot(dx, dy)
            if dist > 1.5:
                spd = min(1.45, max(0.24, dist * 0.012))
                self.vel_x = (dx / dist) * spd
                self.vel_y = (dy / dist) * spd
                self.pos_x += self.vel_x
                self.pos_y += self.vel_y
                self.move(int(self.pos_x), int(self.pos_y))
            else:
                self.vel_x *= 0.85
                self.vel_y *= 0.85
        elif not self.dragging:
            self.vel_x *= 0.82
            self.vel_y *= 0.82

        # Inclinación curiosa espontánea en standby
        if now >= self.next_curious:
            self.curious_tilt = random.choice([-7.5, 0.0, 7.5, 0.0]) if self.state == "standby" else 0.0
            self.next_curious = now + random.uniform(3.8, 7.5)

        target_tilt = max(-16.0, min(16.0, self.vel_x * 4.2 + self.curious_tilt))
        if self.state == "happy":
            target_tilt = math.sin(dt * 9.0) * 8.5
        self.tilt_deg += (target_tilt - self.tilt_deg) * 0.14

        # Resorte gelatinoso squash & stretch
        spring_k = 0.22
        damping = 0.78
        force = (1.0 - self.squash_x) * spring_k
        self.squash_vel = (self.squash_vel + force) * damping
        self.squash_x = max(0.84, min(1.18, self.squash_x + self.squash_vel))
        self.squash_y = 2.0 - self.squash_x  # conserva volumen líquido!

        # Saltito feliz en estado happy
        target_bounce = -abs(math.sin(dt * 7.5)) * 7.5 if self.state == "happy" else 0.0
        self.bounce_y += (target_bounce - self.bounce_y) * 0.25

        # Seguimiento suavizado del cursor con los ojos
        cur = QCursor.pos()
        cx = self.pos_x + self.W / 2.0
        cy = self.pos_y + 58.0
        dx_m = cur.x() - cx
        dy_m = cur.y() - cy
        md = max(1.0, math.hypot(dx_m, dy_m))
        if self.state == "thinking":
            tx = math.sin(dt * 3.2) * 3.0
            ty = -2.6
        else:
            tx = (dx_m / md) * min(3.4, md * 0.014)
            ty = (dy_m / md) * min(2.4, md * 0.014)
        self.look_x += (tx - self.look_x) * 0.14
        self.look_y += (ty - self.look_y) * 0.14

        if now >= self.next_blink:
            self.blink_start = now
            self.next_blink = now + random.uniform(2.5, 5.5)

        want_label = self.hovering or (now < self.label_until) or (self.state != "standby")
        target_a = 1.0 if want_label else 0.0
        self.label_alpha += (target_a - self.label_alpha) * 0.14

        self.update()

    def _blink_factor(self, now: float) -> float:
        el = now - self.blink_start
        if 0.0 <= el < 0.16:
            return math.sin((el / 0.16) * math.pi)
        return 0.0

    def paintEvent(self, _event) -> None:
        now = time.time()
        painter = QPainter(self)
        paint_ooooo(
            painter,
            self.W,
            self.H,
            self.state,
            now - self.t0,
            look_x=self.look_x,
            look_y=self.look_y,
            blink_factor=self._blink_factor(now),
            tilt_deg=self.tilt_deg,
            squash_x=self.squash_x,
            squash_y=self.squash_y,
            bounce_y=self.bounce_y,
            label_text=self.label_text,
            label_alpha=self.label_alpha,
        )
        painter.end()

    def enterEvent(self, _event) -> None:
        self.hovering = True
        self._trigger_jiggle(0.08)

    def leaveEvent(self, _event) -> None:
        self.hovering = False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_moved = False
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            self.last_drag_pos = QPointF(self.pos_x, self.pos_y)
            self._trigger_jiggle(-0.10)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self.dragging:
            np_pt = event.globalPosition().toPoint() - self.drag_offset
            if abs(np_pt.x() - self.pos_x) > 4 or abs(np_pt.y() - self.pos_y) > 4:
                self.drag_moved = True
            self.vel_x = max(-6.0, min(6.0, (np_pt.x() - self.last_drag_pos.x()) * 0.45))
            self.vel_y = max(-6.0, min(6.0, (np_pt.y() - self.last_drag_pos.y()) * 0.45))
            self.last_drag_pos = QPointF(np_pt.x(), np_pt.y())
            self.pos_x, self.pos_y = float(np_pt.x()), float(np_pt.y())
            self.target_x, self.target_y = self.pos_x, self.pos_y
            self.move(np_pt)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self._trigger_jiggle(0.16)
            if not self.drag_moved:
                self.on_ptt()
            else:
                self.next_wander = time.time() + 10.0

    def _run_showcase(self) -> None:
        if self._showcase_running:
            return
        self._showcase_running = True

        def _seq() -> None:
            steps = [
                ("happy", "✨ ¡Hola!", 2.4),
                ("listening", "🎙 Escuchando…", 2.4),
                ("thinking", "⚡ Circuitos…", 2.6),
                ("speaking", "🔊 Hablando…", 2.4),
                ("standby", "Helena lista", 0.1),
            ]
            for st, msg, dur in steps:
                self.bridge.set_state(st, msg)
                time.sleep(dur)
            self._showcase_running = False

        threading.Thread(target=_seq, daemon=True).start()

    def _show_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #0b1324; color: #e2e8f0; border: 1px solid #38bdf8; border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 6px 14px; border-radius: 5px; }"
            "QMenu::item:selected { background-color: #0284c7; color: #ffffff; }"
        )
        act_talk = menu.addAction("🎙 Hablar ahora (clic / Ctrl+Shift+H)")
        act_smart = menu.addAction("🧠 Modo inteligente: ON" if self.smart_context else "🧠 Modo inteligente: OFF")
        act_hide = menu.addAction("👻 Esconder avatar (sigue escuchando)")
        act_show = menu.addAction("🎬 Ver animaciones de OOOOO")
        act_roam = menu.addAction("📌 Quedarse quieta" if self.roam_enabled else "✨ Volver a flotar")
        act_train = menu.addAction("🎤 Entrenar con mi voz")
        act_dash = menu.addAction("📊 Abrir panel Helena")
        menu.addSeparator()
        act_quit = menu.addAction("⏻ Cerrar Helena")

        chosen = menu.exec(global_pos)
        if chosen == act_talk:
            self.on_ptt()
        elif chosen == act_smart:
            self.smart_context = not self.smart_context
            self.label_text = "🧠 Modo auto ON" if self.smart_context else "🧠 Modo auto OFF"
            self.label_until = time.time() + 2.0
        elif chosen == act_hide:
            self._on_visibility_changed("hide")
        elif chosen == act_show:
            self._run_showcase()
        elif chosen == act_roam:
            self.roam_enabled = not self.roam_enabled
            self.label_text = "✨ Flotando" if self.roam_enabled else "📌 Fija aquí"
            self.label_until = time.time() + 2.0
        elif chosen == act_train:
            py = str(VENV_PY if VENV_PY.exists() else sys.executable)
            if TRAIN_SCRIPT.exists():
                subprocess.Popen(["cmd.exe", "/c", "start", "Entrenar Voz — Helena", py, str(TRAIN_SCRIPT)], cwd=str(ROOT))
        elif chosen == act_dash:
            if DASHBOARD_HTML.exists():
                subprocess.Popen(["cmd.exe", "/c", "start", "", str(DASHBOARD_HTML)])
        elif chosen == act_quit:
            self._quit_all()


def render_snapshot(out_path: str) -> int:
    """Renderiza vista previa HiDPI 2x de los 5 estados animados de OOOOO (con circuitos y morphing)."""
    app = QApplication.instance() or QApplication(sys.argv)
    scale = 2
    cell_w, cell_h = 152, 150
    states = [
        ("standby", "En espera", 0.4, -5.0, 1.0, 1.0),
        ("happy", "¡Listo!", 0.3, 6.0, 0.94, 1.06),
        ("listening", "Escuchando…", 0.5, 0.0, 1.04, 0.96),
        ("thinking", "Circuitos…", 1.2, -3.0, 1.0, 1.0),
        ("speaking", "Hablando…", 0.4, 3.0, 1.05, 0.95),
    ]
    pix = QPixmap(cell_w * len(states) * scale, cell_h * scale)
    pix.fill(QColor("#080e1c"))
    painter = QPainter(pix)
    painter.scale(scale, scale)
    for i, (st, lbl, dt, tilt, sx, sy) in enumerate(states):
        painter.save()
        painter.translate(i * cell_w + 6, 6)
        paint_ooooo(
            painter, 140, 138, st, dt,
            look_x=1.4, look_y=-0.4, tilt_deg=tilt, squash_x=sx, squash_y=sy,
            label_text=lbl, label_alpha=1.0,
        )
        painter.restore()
    painter.end()
    ok = pix.save(out_path)
    print(f"SNAPSHOT_OK: {ok} -> {out_path}")
    return 0 if ok else 1


def run_avatar_app(worker_fn=None, on_ptt=None, on_quit=None, roam: bool = True) -> int:
    """Ejecuta Qt en el hilo principal y opcionalmente un worker en hilo secundario."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # permite esconderse sin cerrar Helena!
    bridge = AvatarBridge()
    win = OooooAvatarWindow(bridge, on_ptt=on_ptt, on_quit=on_quit, roam=roam)
    win.show()

    if worker_fn is not None:
        t = threading.Thread(target=worker_fn, args=(bridge,), daemon=True)
        t.start()

    return app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="Avatar HiDPI estilo OOOOO (Elio) v2 con circuitos y física líquida.")
    parser.add_argument("--demo", action="store_true", help="Recorre los 5 estados animados durante 14 s")
    parser.add_argument("--still", action="store_true", help="Inicia fija sin deambular")
    parser.add_argument("--snapshot", default="", help="Renderiza vista previa HiDPI de los 5 estados a un PNG y sale")
    args = parser.parse_args()

    if args.snapshot:
        return render_snapshot(args.snapshot)

    stop = threading.Event()

    def demo_worker(bridge: AvatarBridge) -> None:
        seq = [
            ("standby", "Helena lista", 2.4),
            ("happy", "✨ ¡Hola!", 2.4),
            ("listening", "🎙 Escuchando…", 2.8),
            ("thinking", "⚡ Circuitos…", 2.8),
            ("speaking", "🔊 Respondiendo", 2.8),
        ]
        for st, msg, dur in seq:
            if stop.is_set():
                break
            bridge.set_state(st, msg)
            time.sleep(dur)
        bridge.close()

    return run_avatar_app(
        worker_fn=demo_worker if args.demo else None,
        on_quit=stop.set,
        roam=not args.still,
    )


if __name__ == "__main__":
    raise SystemExit(main())

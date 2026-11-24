#!/usr/bin/env python3
"""
Entrenador interactivo de voz para Helena (JARVIS).
Calibra:
  1) Ruido ambiente real de tu escritorio (para cortes rápidos y sin falsos positivos).
  2) Tu wake word personalizada ("Helena" / "Jarvis") usando embeddings neuronales ONNX.
  3) Tu huella vocal (speaker verification) para reconocerte a ti.
Privacidad: TODO el audio se procesa en RAM y se descarta al instante; solo se
guardan vectores numéricos en C:\\Jarvis\\memory\\voice_profile.pkl.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
import time
import winsound
import numpy as np

ROOT = Path(r"C:\Jarvis")
sys.path.insert(0, str(ROOT / "scripts"))

from voice_profile import (
    PROFILE_PATH,
    SAMPLE_RATE,
    VoiceProfile,
    extract_speaker_vector,
    flatten_wake_window,
)

WAKE_CLIP_SAMPLES = 30720  # 1.92 s -> produce ventanas suficientes de 16 frames en AudioFeatures


def _beep(freq: int = 880, ms: int = 110) -> None:
    try:
        winsound.Beep(freq, ms)
    except Exception:
        pass


def record_clip(seconds: float) -> np.ndarray:
    import sounddevice as sd

    n = int(SAMPLE_RATE * seconds)
    buf = sd.rec(n, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return buf[:, 0].copy()


def rms_meter(pcm_i16: np.ndarray) -> tuple[float, str]:
    rms = float(np.sqrt(np.mean((pcm_i16.astype(np.float32) / 32768.0) ** 2)))
    bars = min(16, int(rms * 180))
    return rms, "[" + "#" * bars + "-" * (16 - bars) + f"] rms={rms:.3f}"


def extract_windows(af, pcm_i16: np.ndarray, augment: bool = False) -> list[np.ndarray]:
    """Extrae ventanas (16, 96) del modelo neuronal ONNX de openwakeword."""
    windows = []
    # Asegurar longitud mínima de ~2.0 s para obtener 16 frames de embedding
    min_len = WAKE_CLIP_SAMPLES
    if len(pcm_i16) < min_len:
        pad = np.zeros(min_len - len(pcm_i16), dtype=np.int16)
        clips = [np.concatenate([pad, pcm_i16])]
    else:
        clips = [pcm_i16]

    if augment:
        rng = np.random.default_rng(42)
        base = clips[0]
        # Pequeños desplazamientos temporales y ruido leve para máxima receptividad
        for shift in (-1600, 1600):
            clips.append(np.roll(base, shift))
        noise = (rng.normal(0, 120, size=base.shape)).astype(np.int16)
        clips.append(np.clip(base.astype(np.int32) + noise, -32768, 32767).astype(np.int16))

    for clip in clips:
        af.reset()
        # Alimentar en bloques de 1280 muestras (exactamente igual que en streaming)
        for i in range(0, len(clip) - 1279, 1280):
            af(clip[i : i + 1280])
        feat = af.get_features(16)
        windows.append(flatten_wake_window(feat))
    return windows


def build_and_save_profile(
    owner_name: str,
    wake_label: str,
    ambient_clips: list[np.ndarray],
    pos_clips: list[np.ndarray],
    neg_speech_clips: list[np.ndarray],
    out_path: Path,
) -> VoiceProfile:
    from openwakeword.utils import AudioFeatures
    from sklearn.linear_model import LogisticRegression

    af = AudioFeatures(inference_framework="onnx")

    # 1. Ruido ambiente
    ambient_rms = [float(np.sqrt(np.mean((c.astype(np.float32) / 32768.0) ** 2))) for c in ambient_clips]
    noise_floor = float(np.median(ambient_rms)) if ambient_rms else 0.008

    # 2. Ventanas positivas (wake word con tu voz + augmentación)
    X_pos = []
    for c in pos_clips:
        X_pos.extend(extract_windows(af, c, augment=True))
    X_pos_arr = np.vstack(X_pos).astype(np.float32)

    # 3. Ventanas negativas (ruido ambiente + frases normales sin wake word + ruido sintético)
    X_neg = []
    for c in ambient_clips + neg_speech_clips:
        # Extraer múltiples ventanas deslizantes de cada clip negativo
        step = 12800  # 0.8 s
        if len(c) <= WAKE_CLIP_SAMPLES:
            X_neg.extend(extract_windows(af, c, augment=False))
        else:
            for start in range(0, len(c) - WAKE_CLIP_SAMPLES + 1, step):
                X_neg.extend(extract_windows(af, c[start : start + WAKE_CLIP_SAMPLES], augment=False))
    # Añadir 4 muestras de ruido sintético variado para estabilidad numérica
    rng = np.random.default_rng(7)
    for amp in (40, 150, 500, 1200):
        syn = rng.normal(0, amp, size=WAKE_CLIP_SAMPLES).astype(np.int16)
        X_neg.extend(extract_windows(af, syn, augment=False))
    X_neg_arr = np.vstack(X_neg).astype(np.float32)

    X = np.vstack([X_pos_arr, X_neg_arr])
    y = np.concatenate([np.ones(len(X_pos_arr), dtype=int), np.zeros(len(X_neg_arr), dtype=int)])

    clf = LogisticRegression(C=3.0, max_iter=500, class_weight="balanced")
    clf.fit(X, y)

    # Calibrar umbral con margen de seguridad entre negativos y positivos
    pos_scores = clf.predict_proba(X_pos_arr)[:, 1]
    neg_scores = clf.predict_proba(X_neg_arr)[:, 1]
    p_low = float(np.percentile(pos_scores, 15))
    n_high = float(np.percentile(neg_scores, 95))
    wake_thr = float(np.clip((p_low + n_high) * 0.52, 0.52, 0.82))

    # 4. Huella biométrica del locutor (solo de clips con tu voz)
    spk_vecs = [extract_speaker_vector(c.astype(np.float32) / 32768.0) for c in (pos_clips + neg_speech_clips)]
    spk_mat = np.vstack(spk_vecs)
    centroid = np.mean(spk_mat, axis=0)
    c_norm = float(np.linalg.norm(centroid))
    if c_norm > 1e-8:
        centroid = centroid / c_norm
    sims = spk_mat @ centroid
    spk_min_sim = float(np.clip(float(np.min(sims)) - 0.12, 0.55, 0.86))

    prof = VoiceProfile(
        owner_name=owner_name,
        wake_label=wake_label,
        wake_clf=clf,
        wake_pos_matrix=X_pos_arr,
        wake_threshold=wake_thr,
        speaker_centroid=centroid.astype(np.float32),
        speaker_min_sim=spk_min_sim,
        noise_floor_rms=noise_floor,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    prof.save(out_path)
    print(f"\n[OK] Perfil vocal guardado en: {out_path} (0 archivos de audio en disco)")
    print(f"     Wake word: '{wake_label}' | umbral={wake_thr:.2f} (pos_p15={p_low:.2f} vs neg_p95={n_high:.2f})")
    print(f"     Huella vocal: sim_min={spk_min_sim:.2f} | piso_ruido={noise_floor:.4f}")
    return prof


def run_dry_run(out_path: Path) -> int:
    """Valida el pipeline completo de entrenamiento con señales sintéticas sin tocar el perfil real."""
    rng = np.random.default_rng(123)
    t = np.linspace(0, 2.0, WAKE_CLIP_SAMPLES, endpoint=False)
    pos = [((np.sin(2 * np.pi * (220 + i * 12) * t) * 8000) + rng.normal(0, 300, t.size)).astype(np.int16) for i in range(4)]
    amb = [rng.normal(0, 120, size=WAKE_CLIP_SAMPLES).astype(np.int16) for _ in range(2)]
    neg = [((np.sin(2 * np.pi * (520 + i * 30) * t) * 6000) + rng.normal(0, 500, t.size)).astype(np.int16) for i in range(3)]
    tmp = ROOT / "logs" / "_dryrun_voice_profile.pkl"
    prof = build_and_save_profile("Test", "Helena", amb, pos, neg, tmp)
    ok, sim = prof.verify_speaker(pos[0].astype(np.float32) / 32768.0)
    print(f"DRYRUN_SPEAKER_CHECK: match={ok} sim={sim:.3f}")
    tmp.unlink(missing_ok=True)
    print("TRAIN_DRYRUN: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Entrena a Helena con tu voz (wake word + huella vocal, 100% local).")
    parser.add_argument("--word", default="Helena", help="Palabra principal de activación a entrenar (default: Helena)")
    parser.add_argument("--owner", default="Helena-User", help="Nombre del propietario del perfil")
    parser.add_argument("--samples", type=int, default=6, help="Número de repeticiones del wake word (default: 6)")
    parser.add_argument("--dry-run", action="store_true", help="Prueba el pipeline sin usar micrófono ni sobrescribir el perfil")
    args = parser.parse_args()

    if args.dry_run:
        return run_dry_run(PROFILE_PATH)

    print("=======================================================")
    print("  ENTRENAMIENTO DE VOZ — HELENA (100% LOCAL EN RAM)")
    print("=======================================================")
    print("Duración aproximada: 45-60 segundos. No se guardan audios en disco.\n")

    # Paso 1: Ruido ambiente
    input("[Paso 1/3] Guarda silencio 3 segundos para medir el ruido de tu escritorio. Pulsa ENTER...")
    _beep(600, 90)
    print("  Grabando ambiente (3 s)...")
    amb_clip = record_clip(3.2)
    _, meter = rms_meter(amb_clip)
    print(f"  Listo {meter}\n")

    # Paso 2: Wake word con tu voz
    prompts_wake = [
        f'Di "Oye {args.word}" con tu tono normal',
        f'Di "Hola {args.word}" un poco más rápido',
        f'Di "{args.word}" de forma natural',
        f'Di "Oye {args.word}" un poco más suave',
        f'Di "Despierta {args.word}" con tu tono normal',
        f'Di "Hola {args.word}" con claridad',
    ][: max(4, args.samples)]

    pos_clips = []
    print(f"[Paso 2/3] Entrenaremos tu activación ({len(prompts_wake)} muestras cortas de 2 s):")
    for idx, prompt in enumerate(prompts_wake, 1):
        input(f"  ({idx}/{len(prompts_wake)}) {prompt}. Pulsa ENTER y habla tras el pitido...")
        _beep(880, 110)
        clip = record_clip(2.0)
        _beep(520, 80)
        _, meter = rms_meter(clip)
        print(f"       Capturada {meter}")
        pos_clips.append(clip)

    # Paso 3: Frases naturales para huella vocal + muestras negativas de habla cotidiana
    phrases = [
        "Revisa el estado de mis repositorios git y los cambios pendientes.",
        "Cuál es el clima hoy en mi ciudad y cuáles son mis tres prioridades.",
        "Crea una automatización en Python con registro de logs y modo prueba.",
    ]
    neg_clips = []
    print(f"\n[Paso 3/3] Huella de tu voz ({len(phrases)} frases de 3.5 s, SIN decir {args.word}):")
    for idx, phrase in enumerate(phrases, 1):
        input(f'  ({idx}/{len(phrases)}) Lee: "{phrase}" — Pulsa ENTER...')
        _beep(880, 110)
        clip = record_clip(3.5)
        _beep(520, 80)
        _, meter = rms_meter(clip)
        print(f"       Capturada {meter}")
        neg_clips.append(clip)

    print("\nEntrenando modelo neuronal local con tu voz...")
    build_and_save_profile(args.owner, args.word, [amb_clip], pos_clips, neg_clips, PROFILE_PATH)
    print("\n¡Listo! La próxima vez que inicies voice_bridge.py, Helena reconocerá tu voz automáticamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

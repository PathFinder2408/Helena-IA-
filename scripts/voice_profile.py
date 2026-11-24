#!/usr/bin/env python3
"""
Perfil biométrico y detector personalizado de wake word para Helena (JARVIS).
Usa embeddings neuronales ONNX (Google Speech Embedding de openwakeword) +
rasgos espectrales Mel en RAM. NUNCA guarda audio en disco: solo vectores y
pesos numéricos en C:\\Jarvis\\memory\\voice_profile.pkl.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pickle
import numpy as np

SAMPLE_RATE = 16000
PROFILE_PATH = Path(r"C:\Jarvis\memory\voice_profile.pkl")


def _mel_filterbank(n_fft: int = 512, sr: int = SAMPLE_RATE, n_mels: int = 26) -> np.ndarray:
    def hz_to_mel(hz: np.ndarray) -> np.ndarray:
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def mel_to_hz(mel: np.ndarray) -> np.ndarray:
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    mels = np.linspace(hz_to_mel(np.array(70.0)), hz_to_mel(np.array(sr / 2.0)), n_mels + 2)
    hz = mel_to_hz(mels)
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        f_l, f_c, f_r = bins[m - 1], bins[m], bins[m + 1]
        if f_c > f_l:
            fb[m - 1, f_l:f_c] = (np.arange(f_l, f_c) - f_l) / (f_c - f_l)
        if f_r > f_c:
            fb[m - 1, f_c:f_r] = (f_r - np.arange(f_c, f_r)) / (f_r - f_c)
    return fb


_MEL_FB = _mel_filterbank()


def extract_speaker_vector(audio_f32: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Extrae una huella acústica normalizada L2 (56 dims) de la voz del locutor."""
    x = np.asarray(audio_f32, dtype=np.float32).flatten()
    if x.size < 400:
        return np.zeros(56, dtype=np.float32)

    # Pre-énfasis ligero para resaltar formantes vocales
    x = np.append(x[0], x[1:] - 0.95 * x[:-1])

    win_len = 400  # 25 ms
    hop = 160      # 10 ms
    n_frames = 1 + max(0, (len(x) - win_len) // hop)
    if n_frames < 3:
        return np.zeros(56, dtype=np.float32)

    window = np.hanning(win_len).astype(np.float32)
    frames = np.lib.stride_tricks.as_strided(
        x,
        shape=(n_frames, win_len),
        strides=(x.strides[0] * hop, x.strides[0]),
    ).copy()

    # Seleccionar solo frames con voz activa (top 65% por energía)
    energy = np.mean(frames ** 2, axis=1)
    thr = max(1e-6, float(np.percentile(energy, 35)))
    voiced = frames[energy >= thr]
    if voiced.shape[0] < 3:
        voiced = frames

    spec = np.abs(np.fft.rfft(voiced * window, n=512)) ** 2
    mel = np.log1p(spec @ _MEL_FB.T)
    mel_mean = np.mean(mel, axis=0)
    mel_std = np.std(mel, axis=0)

    # Perfil de energía en bandas de pitch fundamental (80-180, 180-320, 320-600, 600-1500 Hz)
    freqs = np.fft.rfftfreq(512, d=1.0 / sr)
    total_e = float(np.sum(spec) + 1e-8)
    bands = []
    for lo, hi in ((80, 180), (180, 320), (320, 600), (600, 1500)):
        mask = (freqs >= lo) & (freqs < hi)
        bands.append(float(np.sum(spec[:, mask]) / total_e))

    vec = np.concatenate([mel_mean, mel_std, np.array(bands, dtype=np.float32)]).astype(np.float32)
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 1e-8 else vec


def flatten_wake_window(feat_16x96: np.ndarray) -> np.ndarray:
    """Convierte ventana (1, 16, 96) o (16, 96) en vector L2 compacto (1536 dims)."""
    arr = np.asarray(feat_16x96, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr[0]
    flat = arr.reshape(-1)
    norm = float(np.linalg.norm(flat))
    return flat / norm if norm > 1e-8 else flat


@dataclass
class VoiceProfile:
    owner_name: str
    wake_label: str
    wake_clf: object                  # sklearn LogisticRegression
    wake_pos_matrix: np.ndarray       # (N_pos, 1536) normalizado L2
    wake_threshold: float
    speaker_centroid: np.ndarray      # (56,) normalizado L2
    speaker_min_sim: float
    noise_floor_rms: float
    created_at: str

    def predict_wake(self, feat_16x96: np.ndarray) -> float:
        """Retorna score [0..1] combinando clasificador entrenado + similitud coseno."""
        vec = flatten_wake_window(feat_16x96)
        prob = float(self.wake_clf.predict_proba(vec.reshape(1, -1))[0, 1])
        cos_max = float(np.max(self.wake_pos_matrix @ vec)) if self.wake_pos_matrix.size else 0.0
        cos_scaled = max(0.0, min(1.0, (cos_max - 0.35) / 0.55))
        return 0.65 * prob + 0.35 * cos_scaled

    def verify_speaker(self, audio_f32: np.ndarray) -> tuple[bool, float]:
        """Verifica si la voz corresponde al usuario entrenado (retorna match, similitud)."""
        vec = extract_speaker_vector(audio_f32)
        sim = float(np.dot(vec, self.speaker_centroid))
        return (sim >= self.speaker_min_sim, sim)

    def save(self, path: Path = PROFILE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: Path = PROFILE_PATH) -> "VoiceProfile | None":
        if not path.exists():
            return None
        try:
            with path.open("rb") as f:
                obj = pickle.load(f)
            return obj if isinstance(obj, cls) else None
        except Exception:
            return None

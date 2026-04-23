# """
# Peak detection and cardiac cycle analysis for ECG signals.
# Includes pacemaker trigger logic.
# """

# import numpy as np
# import time


# def detect_r_peaks(signal_data, threshold, distance):
#     """
#     Simple R-peak detector based on threshold and minimum distance.
#     """
#     if len(signal_data) < 3:
#         return []

#     peaks = []
#     last_peak = -distance

#     for i in range(1, len(signal_data) - 1):
#         if (
#             signal_data[i] > threshold
#             and signal_data[i] > signal_data[i - 1]
#             and signal_data[i] > signal_data[i + 1]
#         ):
#             if i - last_peak >= distance:
#                 peaks.append(i)
#                 last_peak = i

#     return peaks


# def calculate_bpm(peaks, sample_rate):
#     """
#     Calculate BPM from R-peak indices.
#     """
#     if len(peaks) < 2:
#         return 0
#     rr_intervals = [(peaks[i+1]-peaks[i])/sample_rate for i in range(len(peaks)-1)]
#     avg_rr = sum(rr_intervals)/len(rr_intervals)
#     bpm = 60 / avg_rr
#     return bpm


# # ==================================================
# # NUEVO: Análisis del ciclo cardíaco (marcapasos)
# # ==================================================

# def analyze_cardiac_cycle(peaks, sample_rate, min_bpm=50, max_rr_interval=2.0):
#     """
#     Analyze cardiac rhythm to detect failures.

#     Args:
#         peaks (list): R-peak indices
#         sample_rate (int): Hz
#         min_bpm (int): Minimum safe BPM
#         max_rr_interval (float): Max allowed RR interval in seconds

#     Returns:
#         dict: Cardiac status
#     """
#     status = {
#         "bpm": 0,
#         "asystole": False,
#         "bradycardia": False,
#         "pacemaker_needed": False,
#         "last_rr_interval": None,
#     }

#     if len(peaks) < 2:
#         status["asystole"] = True
#         status["pacemaker_needed"] = True
#         return status

#     rr_intervals = np.diff(peaks) / sample_rate
#     last_rr = rr_intervals[-1]
#     bpm = 60 / np.mean(rr_intervals)

#     status["bpm"] = bpm
#     status["last_rr_interval"] = last_rr

#     # Asystole: demasiado tiempo sin latido
#     if last_rr > max_rr_interval:
#         status["asystole"] = True
#         status["pacemaker_needed"] = True

#     # Bradycardia
#     elif bpm < min_bpm:
#         status["bradycardia"] = True
#         status["pacemaker_needed"] = True

#     return status


"""
Peak detection and cardiac cycle analysis for ECG signals.

- detect_r_peaks(): detecta picos R usando umbral y distancia mínima
  (mejorado para detectar picos positivos o negativos usando abs()).
- calculate_bpm(): calcula BPM de forma más robusta usando mediana de RR
  y descartando intervalos imposibles.
"""

from __future__ import annotations
import numpy as np


def _moving_average(x: np.ndarray, n: int) -> np.ndarray:
    """Suavizado simple para reducir ruido antes de buscar máximos."""
    if n <= 1:
        return x
    kernel = np.ones(int(n), dtype=float) / float(n)
    return np.convolve(x, kernel, mode="same")


def detect_r_peaks(signal_data, threshold: float, distance: int):
    """
    Detector simple de picos tipo R:
    - Usa abs(signal) para funcionar aunque el QRS salga invertido.
    - Suaviza un poco para que el ruido no dispare falsos picos.

    Args:
        signal_data: array-like (ya idealmente centrado en 0 por tu app.py)
        threshold: umbral en VOLTIOS sobre |señal|
        distance: distancia mínima entre picos (en samples)

    Returns:
        list[int]: índices de picos dentro de la ventana
    """
    x = np.asarray(signal_data, dtype=float)
    if x.size < 3:
        return []

    distance = int(max(1, distance))

    # Para que funcione en derivadas con QRS negativo también:
    x_abs = np.abs(x)

    # Suavizado leve (5 samples ~ 5 ms a 1 kHz)
    x_f = _moving_average(x_abs, n=5)

    thr = float(threshold)

    peaks = []
    last_peak = -distance

    # máximo local + umbral + distancia mínima
    for i in range(1, len(x_f) - 1):
        if x_f[i] > thr and x_f[i] > x_f[i - 1] and x_f[i] > x_f[i + 1]:
            if i - last_peak >= distance:
                peaks.append(i)
                last_peak = i

    return peaks


def calculate_bpm(peaks, sample_rate: float):
    """
    BPM robusto:
    - Si hay pocos picos -> 0
    - Calcula RR en segundos
    - Descarta RR imposibles (muy cortos o muy largos)
    - Usa mediana para estabilidad

    OJO: si estás metiendo un seno rápido (20 Hz), esto NO representa BPM real.
    """
    if len(peaks) < 2:
        return 0.0

    sr = float(sample_rate)
    rr = np.diff(np.asarray(peaks, dtype=float)) / sr  # segundos

    # Filtrado básico fisiológico (ajusta si quieres)
    rr = rr[(rr >= 0.25) & (rr <= 2.0)]  # 240 bpm .. 30 bpm

    if rr.size == 0:
        return 0.0

    bpm = 60.0 / float(np.median(rr))

    # límite de seguridad
    if bpm < 30 or bpm > 240:
        return 0.0

    return bpm


def analyze_cardiac_cycle(peaks, sample_rate, min_bpm=50, max_rr_interval=2.0):
    """
    Mantengo tu función, pero usando RR robusto.
    """
    status = {
        "bpm": 0,
        "asystole": False,
        "bradycardia": False,
        "pacemaker_needed": False,
        "last_rr_interval": None,
    }

    if len(peaks) < 2:
        status["asystole"] = True
        status["pacemaker_needed"] = True
        return status

    rr_intervals = np.diff(peaks) / float(sample_rate)
    last_rr = float(rr_intervals[-1])

    # robusto
    bpm = 60.0 / float(np.median(rr_intervals))

    status["bpm"] = bpm
    status["last_rr_interval"] = last_rr

    if last_rr > max_rr_interval:
        status["asystole"] = True
        status["pacemaker_needed"] = True
    elif bpm < min_bpm:
        status["bradycardia"] = True
        status["pacemaker_needed"] = True

    return status
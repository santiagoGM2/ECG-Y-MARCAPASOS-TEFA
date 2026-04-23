# import threading
# import time
# from collections import deque
# import tkinter as tk
# from . import config


# class AppState:
#     def __init__(self, master=None):
#         # =====================================================
#         # ---------------- DATA BUFFERS -----------------------
#         # =====================================================
#         self.data_lock = threading.Lock()

#         maxlen = getattr(config, "MAX_BUFFER_SIZE", 5000)
#         self.voltage_buffer = deque(maxlen=maxlen)
#         self.time_buffer = deque(maxlen=maxlen)

#         self.sample_count = 0

#         # =====================================================
#         # --------------- CONNECTION STATUS -------------------
#         # =====================================================
#         self.esp32_connected = False

#         # =====================================================
#         # --------------- DERIVATION CONTROL ------------------
#         # =====================================================
#         self.mux_state_label = {
#             0: "I",
#             1: "II",
#             2: "III",
#             3: "aVR",
#             4: "aVL",
#             5: "aVF",
#         }

#         self.current_mux_state = 0
#         self.mux_lock = threading.Lock()

#         # =====================================================
#         # ----------- UX STATES (blanking / no signal / pace) ---
#         # =====================================================

#         self.blank_until = 0.0               # tiempo (time.time()) hasta el que se dibuja línea base muerta
#         self.no_signal = True                # bandera calculada en GUI
#         self.no_signal_since = None          # timestamp desde que empezó "sin señal"

#         # Marcapasos por UI
#         self.pace_pulse_pending = False      # se setea cuando aprietas el botón
#         self.pace_alert_until = 0.0          # alerta encendida hasta este tiempo

#         # =====================================================
#         # ----------- MANUAL / AUTO CONTROL MODE -------------
#         # =====================================================
#         # Master explícito para evitar problemas si cambias el orden de creación
#         self.operation_mode = tk.StringVar(master=master, value=config.MODE_MANUAL)

#         self.last_manual_action_time = time.time()
#         self.last_auto_switch_time = time.time()

#         # =====================================================
#         # -------- UI VARIABLES (AFFECT PROCESSING) -----------
#         # =====================================================
#         self.ecg_gain = tk.DoubleVar(master=master, value=config.DEFAULT_GAIN)
#         self.window_size = tk.IntVar(master=master, value=config.DEFAULT_WINDOW_SIZE)
#         self.y_max = tk.DoubleVar(master=master, value=config.DEFAULT_Y_MAX)

#         self.r_threshold = tk.DoubleVar(master=master, value=config.DEFAULT_R_THRESHOLD)
#         self.r_distance = tk.IntVar(master=master, value=config.DEFAULT_R_DISTANCE)

#     # =========================================================
#     # ---------------- SIGNAL ACCESS ---------------------------
#     # =========================================================
#     def get_current_signal(self):
#         return list(self.voltage_buffer)

#     def add_sample(self, volts: float):
#         """Útil si luego quieres que todo el append viva aquí."""
#         with self.data_lock:
#             self.voltage_buffer.append(volts)
#             self.time_buffer.append(self.sample_count)
#             self.sample_count += 1

#     # =========================================================
#     # ---------------- MUX CONTROL -----------------------------
#     # =========================================================
#     def set_mux_state(self, state: int):
#         with self.mux_lock:
#             self.current_mux_state = int(state) % config.TOTAL_DERIVATIONS
#             self.operation_mode.set(config.MODE_MANUAL)
#             self.last_manual_action_time = time.time()

#     def next_derivation(self):
#         with self.mux_lock:
#             self.current_mux_state = (self.current_mux_state + 1) % config.TOTAL_DERIVATIONS

#     # =========================================================
#     # ---------------- AUTO MODE LOGIC -------------------------
#     # =========================================================
#     def check_auto_mode(self):
#         # AUTO si no se toca nada por AUTO_TIMEOUT
#         if time.time() - self.last_manual_action_time > config.AUTO_TIMEOUT:
#             self.operation_mode.set(config.MODE_AUTO)

#     def auto_switch_if_needed(self):
#         if time.time() - self.last_auto_switch_time > config.AUTO_SWITCH_INTERVAL:
#             self.next_derivation()
#             self.last_auto_switch_time = time.time()

"""
data_model.py
Estado compartido del proyecto ECG (GUI + Serial + Control MUX)

Objetivo:
- Guardar buffers de señal (voltaje y tiempo)
- Guardar estados de conexión del ESP32
- Guardar estado actual del MUX (derivada)
- Guardar modo MANUAL/AUTO y temporizadores
- Guardar estados de UX nuevos:
    * blanking después de cambiar derivada
    * detección de "no signal"
    * botón de marcapasos (pulso simulado) + alerta temporal

NOTA:
Este archivo NO dibuja nada ni lee serial: solo guarda estado.
"""

import threading
import time
from collections import deque
import tkinter as tk
from . import config


class AppState:
    def __init__(self, master=None):
        # =====================================================
        # ---------------- DATA BUFFERS -----------------------
        # =====================================================
        self.data_lock = threading.Lock()

        maxlen = getattr(config, "MAX_BUFFER_SIZE", 5000)

        # Señal principal (en VOLTIOS)
        self.voltage_buffer = deque(maxlen=maxlen)

        # Eje X (conteo de muestra / sample index)
        self.time_buffer = deque(maxlen=maxlen)

        # Compatibilidad: si en algún archivo viejo todavía usan signal_buffer
        # (lo mantenemos para no romper nada)
        self.signal_buffer = deque(maxlen=maxlen)

        self.sample_count = 0

        # =====================================================
        # --------------- CONNECTION STATUS -------------------
        # =====================================================
        # Bandera usada por la UI
        self.esp32_connected = False

        # Compatibilidad: si algún código anterior usaba esto
        self.serial_connected = False

        # =====================================================
        # --------------- DERIVATION CONTROL ------------------
        # =====================================================
        self.mux_state_label = {
            0: "I",
            1: "II",
            2: "III",
            3: "aVR",
            4: "aVL",
            5: "aVF",
        }

        self.current_mux_state = 0
        self.mux_lock = threading.Lock()

        # =====================================================
        # ----------- UX STATES (blanking / no signal / pace) ---
        # =====================================================
        # “Blanking” después de cambiar derivada:
        # hasta este tiempo (time.time()) dibujas baseline y no calculas BPM
        self.blank_until = 0.0

        # "No signal" (la UI lo calcula con thresholds)
        self.no_signal = True
        self.no_signal_since = None

        # Marcapasos por UI:
        self.pace_pulse_pending = False
        self.pace_alert_until = 0.0

        # =====================================================
        # ----------- MANUAL / AUTO CONTROL MODE -------------
        # =====================================================
        # IMPORTANTE: pasar master evita bugs con Tkinter si cambias el orden de creación
        self.operation_mode = tk.StringVar(master=master, value=config.MODE_MANUAL)

        self.last_manual_action_time = time.time()
        self.last_auto_switch_time = time.time()

        # =====================================================
        # -------- UI VARIABLES (AFFECT PROCESSING) -----------
        # =====================================================
        self.ecg_gain = tk.DoubleVar(master=master, value=config.DEFAULT_GAIN)
        self.window_size = tk.IntVar(master=master, value=config.DEFAULT_WINDOW_SIZE)
        self.y_max = tk.DoubleVar(master=master, value=config.DEFAULT_Y_MAX)

        self.r_threshold = tk.DoubleVar(master=master, value=config.DEFAULT_R_THRESHOLD)
        self.r_distance = tk.IntVar(master=master, value=config.DEFAULT_R_DISTANCE)

    # =========================================================
    # ---------------- SIGNAL ACCESS ---------------------------
    # =========================================================
    def get_current_signal(self):
        """Retorna lista de la señal en voltios."""
        return list(self.voltage_buffer)

    def add_sample(self, volts: float):
        """
        Agrega una muestra en VOLTIOS de forma thread-safe.
        Útil para centralizar el append (en vez de hacerlo en serial_handler).
        """
        with self.data_lock:
            self.voltage_buffer.append(volts)

            # Compatibilidad: también llenar signal_buffer
            self.signal_buffer.append(volts)

            self.time_buffer.append(self.sample_count)
            self.sample_count += 1

    # =========================================================
    # ---------------- MUX CONTROL -----------------------------
    # =========================================================
    def set_mux_state(self, state: int):
        """
        Setea derivada manualmente:
        - actualiza current_mux_state
        - cambia a modo MANUAL
        - refresca last_manual_action_time
        """
        total = getattr(config, "TOTAL_DERIVATIONS", 6)
        with self.mux_lock:
            self.current_mux_state = int(state) % total
            self.operation_mode.set(config.MODE_MANUAL)
            self.last_manual_action_time = time.time()

    def next_derivation(self):
        """Pasa a la siguiente derivada (0..TOTAL_DERIVATIONS-1)."""
        total = getattr(config, "TOTAL_DERIVATIONS", 6)
        with self.mux_lock:
            self.current_mux_state = (self.current_mux_state + 1) % total

    # =========================================================
    # ---------------- AUTO MODE LOGIC -------------------------
    # =========================================================
    def check_auto_mode(self):
        """
        Pasa a AUTO si no se toca nada por AUTO_TIMEOUT.
        """
        if time.time() - self.last_manual_action_time > config.AUTO_TIMEOUT:
            self.operation_mode.set(config.MODE_AUTO)

    def auto_switch_if_needed(self):
        """
        Cambia derivada cada AUTO_SWITCH_INTERVAL si está en modo AUTO.
        (Ojo: normalmente esto lo controlas desde la UI o desde el SerialReader).
        """
        if time.time() - self.last_auto_switch_time > config.AUTO_SWITCH_INTERVAL:
            self.next_derivation()
            self.last_auto_switch_time = time.time()
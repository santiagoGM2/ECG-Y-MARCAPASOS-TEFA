"""
Global configuration file
ECG Monitor - ESP32 + CD4051 MUX

"""

# =========================================================
# ---------------- SERIAL CONFIGURATION -------------------
# =========================================================

# Puerto del ESP32 (CAMBIAR según tu PC)
SERIAL_PORT = "COM6"
#uv run python -c "import serial.tools.list_ports; [print(p) for p in serial.tools.list_ports.comports()]"

# Baudrate (Debe coincidir con el ESP32)
BAUDRATE = 115200

# Timeout de lectura serial (segundos)
SERIAL_TIMEOUT = 1


# =========================================================
# ---------------- SAMPLING CONFIG ------------------------
# =========================================================

# Frecuencia de muestreo del ECG (Hz)
# Debe coincidir con la frecuencia real del ADC del ESP32
SAMPLE_RATE = 1000  

ENABLE_FILTERS = False  # Enable/disable filters

# Intervalo de actualización de la GUI (ms)
REFRESH_INTERVAL = 80

# Tamaño máximo del buffer circular
MAX_BUFFER_SIZE = 5000


# =========================================================
# ---------------- MUX CONFIGURATION ----------------------
# =========================================================

# Prefijo del comando enviado al ESP32
# Ejemplo enviado: "MUX:0"
MUX_COMMAND_PREFIX = "MUX:"

# Número total de derivaciones
TOTAL_DERIVATIONS = 6


# =========================================================
# ---------------- SIGNAL DISPLAY CONFIG ------------------
# =========================================================

# Valor máximo inicial del eje Y (Voltios)
DEFAULT_Y_MAX = 2.0

# Tamaño inicial de ventana de visualización (samples)
DEFAULT_WINDOW_SIZE = 2000

# Ganancia inicial de visualización
DEFAULT_GAIN = 1.0


# =========================================================
# ---------------- PEAK DETECTION CONFIG ------------------
# =========================================================

# Umbral inicial para detección R
DEFAULT_R_THRESHOLD = 0.8

# Distancia mínima entre picos R (samples)
DEFAULT_R_DISTANCE = 200


# =========================================================
# ---------------- SYSTEM MODES ---------------------------
# =========================================================

MODE_MANUAL = "MANUAL"
MODE_AUTO = "AUTO"

AUTO_TIMEOUT = 10          # segundos sin tocar nada → pasa a AUTO
AUTO_SWITCH_INTERVAL = 8   # cada cuántos segundos cambia derivada en AUTO

# =========================================================
# ---------------- DEBUG ----------------------------------
# =========================================================

ENABLE_DEBUG_PRINTS = False


PACE_TIMEOUT_SEC = 1.5
PACE_MIN_INTERVAL_SEC = 0.8

# =========================================================
# ---------------- DISPLAY / UX ---------------------------
# =========================================================

# ====== UI / DERIVATION SWITCH (blanking) ======
DERIVATION_SWITCH_BLANK_SEC = 2.5
BLANK_AFTER_SWITCH_SEC = DERIVATION_SWITCH_BLANK_SEC  # alias para el app.py

# ====== NO SIGNAL DETECTION (en VOLTIOS) ======
# ventana sobre la que se calcula P2P para decidir si “hay señal”
NO_SIGNAL_WINDOW_SAMPLES = int(SAMPLE_RATE * 0.30)  # ~300 ms

# umbral pico a pico mínimo para considerar que sí hay señal
NO_SIGNAL_P2P_V = 0.020
NO_SIGNAL_P2P_THRESHOLD = NO_SIGNAL_P2P_V  # alias para el app.py

# cuánto tiempo sin señal para ya mostrar baseline “muerta”
NO_SIGNAL_TIMEOUT_SEC = 1.0
NO_SIGNAL_MIN_SECONDS = NO_SIGNAL_TIMEOUT_SEC  # alias para el app.py

# ====== PACEMAKER UI / DETECTION ======
PACE_UI_ALERT_SEC = 1.0
PACE_ALERT_HOLD_SEC = PACE_UI_ALERT_SEC  # alias para el app.py

# Spike simulado cuando presionas el botón (en VOLTIOS)
# (ajusta si tu señal está muy pequeña o muy grande)
PACE_SPIKE_WIDTH_SAMPLES = max(3, int(SAMPLE_RATE * 0.010))  # ~10 ms
PACE_SPIKE_AMPLITUDE = 0.7

# Detección tipo “pacer”: si el salto entre muestras es muy brusco
PACE_DERIV_THRESHOLD = 0.35

# ====== Serial robustness ======
SERIAL_RECONNECT_SEC = 1.5     # cada cuánto reintenta abrir COM si se cae
SERIAL_STALE_SEC = 2.0         # si no llegan bytes en este tiempo => desconectado visualmente

# ====== ADC conversion ======
ADC_VREF = 3.3
ADC_MAX = 4095

# ====== MUX command format ======
# Tu firmware Arduino acepta: "STATE_3", "STATE3", "MUX:3", o solo "3"
MUX_COMMAND_FORMAT = "STATE_{state}\n"
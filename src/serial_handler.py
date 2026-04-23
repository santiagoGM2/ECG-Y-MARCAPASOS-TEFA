# import serial
# import threading
# from . import config

# class SerialReader(threading.Thread):
#     def __init__(self, app_state):
#         super().__init__(daemon=True)
#         self.app_state = app_state
#         self.running = True

#         try:
#             self.serial_port = serial.Serial(
#                 config.SERIAL_PORT,
#                 config.BAUDRATE,
#                 timeout=config.SERIAL_TIMEOUT
#             )
#             self.app_state.esp32_connected = True
#         except Exception as e:
#             print("❌ ERROR abriendo puerto:", e)
#             self.serial_port = None
#             self.app_state.esp32_connected = False

#     def run(self):
#         if self.serial_port is None:
#             return

#         while self.running:
#             try:
#                 line = self.serial_port.readline().decode(errors="ignore").strip()
#                 if not line:
#                     continue

#                 # Aceptar solo números (por si algún día mandas logs)
#                 # Ej: "OK STATE 3" se ignora
#                 if not line.lstrip("-").isdigit():
#                     continue

#                 adc = int(line)  # 0..4095

#                 # Convertir a volts (si prefieres crudo, guarda adc tal cual)
#                 volts = (adc * 3.3) / 4095.0

#                 with self.app_state.data_lock:
#                     self.app_state.voltage_buffer.append(volts)
#                     self.app_state.time_buffer.append(self.app_state.sample_count)
#                     self.app_state.sample_count += 1

#             except Exception as e:
#                 print("⚠️ Error leyendo serial:", e)
#                 self.app_state.esp32_connected = False
#                 break

#     def send_mux_command(self, state: int):
#         """
#         Tu GUI manda INT. Enviamos 'STATE_#' para que sea claro.
#         (El main.cpp acepta también solo '#', así que ambas valen)
#         """
#         if self.serial_port and self.serial_port.is_open:
#             try:
#                 state = int(state) & 0x07
#                 self.serial_port.write(f"STATE_{state}\n".encode())
#             except Exception as e:
#                 print("❌ Error enviando comando:", e)

#     def stop(self):
#         self.running = False
#         if self.serial_port and self.serial_port.is_open:
#             self.serial_port.close()
#             self.app_state.esp32_connected = False

import time
import threading
import serial
from . import config


class SerialReader(threading.Thread):
    """
    SerialReader robusto (ASCII + opcional BINARIO):
    - ASCII: una muestra por línea (ej: "2048\n")  <-- tu main.cpp actual
    - ASCII doble canal: "adc25,adc26\n" (toma el primero, deja listo el futuro)
    - BINARIO (opcional): [0xAA][LSB][MSB][XOR]    <-- firmware compañero
    - Ignora logs: READY, ESP32 ECG READY, etc.
    - Reintenta reconectar si Windows tumba el puerto (PermissionError / ClearCommError)
    """

    PKT_START = 0xAA

    def __init__(self, app_state):
        super().__init__(daemon=True)
        self.app_state = app_state
        self.running = True

        self.serial_port = None
        self._rx_buf = bytearray()

        # Defaults si no existen en config.py
        self._reconnect_sec = float(getattr(config, "SERIAL_RECONNECT_SEC", 1.5))
        self._open_delay_sec = float(getattr(config, "SERIAL_OPEN_DELAY_SEC", 0.2))

        # Conversión ADC->Voltios (tu app trabaja en voltios)
        self._vref = float(getattr(config, "ADC_VREF", 3.3))
        self._adc_max = int(getattr(config, "ADC_MAX", 4095))

        # Formato comando MUX (tu Arduino acepta "STATE_3", "3", "MUX:3", etc.)
        # Default: STATE_3\n
        self._mux_cmd_fmt = getattr(config, "MUX_COMMAND_FORMAT", "STATE_{state}\n")

        self._open_port()

    # =====================================================
    # ----------------- CONNECTION ------------------------
    # =====================================================
    def _set_connected(self, ok: bool):
        self.app_state.esp32_connected = bool(ok)
        # compatibilidad por si existe en algún momento
        if hasattr(self.app_state, "serial_connected"):
            self.app_state.serial_connected = bool(ok)

    def _open_port(self):
        try:
            self.serial_port = serial.Serial(
                port=config.SERIAL_PORT,
                baudrate=config.BAUDRATE,
                timeout=getattr(config, "SERIAL_TIMEOUT", 1),
            )

            # En algunos ESP32 abrir puerto resetea la placa:
            time.sleep(self._open_delay_sec)

            try:
                self.serial_port.reset_input_buffer()
                self.serial_port.reset_output_buffer()
            except Exception:
                pass

            self._set_connected(True)

        except Exception as e:
            print("❌ ERROR abriendo puerto:", e)
            self.serial_port = None
            self._set_connected(False)

    def _close_port(self):
        try:
            if self.serial_port and getattr(self.serial_port, "is_open", False):
                self.serial_port.close()
        except Exception:
            pass
        self.serial_port = None
        self._set_connected(False)

    # =====================================================
    # ----------------- PUSH SAMPLE -----------------------
    # =====================================================
    def _push_sample_adc(self, adc: int):
        """Convierte ADC->V y lo mete al AppState sin romper tu flujo."""
        adc = int(adc)
        if adc < 0:
            return

        volts = (adc * self._vref) / float(self._adc_max)

        # Si AppState tiene add_sample(), úsalo.
        if hasattr(self.app_state, "add_sample"):
            self.app_state.add_sample(volts)
            return

        # Si no, usa buffers directo (como tu implementación original)
        with self.app_state.data_lock:
            self.app_state.voltage_buffer.append(volts)
            self.app_state.time_buffer.append(self.app_state.sample_count)
            self.app_state.sample_count += 1

    # =====================================================
    # ----------------- TEXT HANDLER ----------------------
    # =====================================================
    def _handle_text_line(self, line: str):
        s = (line or "").strip()
        if not s:
            return

        up = s.upper()
        if up in ("READY", "ESP32 ECG READY"):
            return

        # ACK del firmware del compañero: OK:idx:nombre
        if s.startswith("OK:"):
            # ejemplo: OK:3:aVR
            parts = s.split(":")
            if len(parts) >= 2:
                try:
                    idx = int(parts[1])
                    if hasattr(self.app_state, "mux_lock"):
                        with self.app_state.mux_lock:
                            self.app_state.current_mux_state = idx
                except Exception:
                    pass
            return

        # Si algún día mandas "adc25,adc26"
        if "," in s:
            first = s.split(",", 1)[0].strip()
            if first.lstrip("-").isdigit():
                self._push_sample_adc(int(first))
            return

        # ASCII normal: solo enteros
        if s.lstrip("-").isdigit():
            self._push_sample_adc(int(s))
            return

        # Si no es número, es log: opcional imprimir
        if getattr(config, "ENABLE_DEBUG_PRINTS", False):
            print("ℹ️ UART:", s)

    # =====================================================
    # ----------------- RX PARSER -------------------------
    # =====================================================
    def _parse_rx_buffer(self):
        """
        Parser híbrido:
        - BINARIO: [0xAA][LSB][MSB][XOR]
        - TEXTO: líneas terminadas en '\n'
        """
        while True:
            if not self._rx_buf:
                return

            # Si el primer byte NO es 0xAA, puede ser TEXTO o basura antes del binario.
            if self._rx_buf[0] != self.PKT_START:
                nl = self._rx_buf.find(b"\n")
                pkt = self._rx_buf.find(bytes([self.PKT_START]))

                # Caso: viene binario pero no alineado -> descarta hasta 0xAA
                if pkt != -1 and (nl == -1 or pkt < nl):
                    del self._rx_buf[:pkt]
                    continue

                # Caso: texto sin newline todavía -> espera
                if nl == -1:
                    # evita crecimiento infinito si hay basura
                    if len(self._rx_buf) > 4096:
                        self._rx_buf.clear()
                    return

                raw_line = self._rx_buf[:nl]
                del self._rx_buf[: nl + 1]
                try:
                    line = raw_line.decode(errors="ignore").strip()
                except Exception:
                    line = ""
                self._handle_text_line(line)
                continue

            # Ahora sí: empieza con 0xAA -> intenta binario
            if len(self._rx_buf) < 4:
                return

            b0, lsb, msb, x = self._rx_buf[0], self._rx_buf[1], self._rx_buf[2], self._rx_buf[3]
            del self._rx_buf[:4]

            if (b0 ^ lsb ^ msb) != x:
                # paquete corrupto
                continue

            adc = (msb << 8) | lsb
            self._push_sample_adc(adc)

    # =====================================================
    # ----------------- THREAD LOOP -----------------------
    # =====================================================
    def run(self):
        while self.running:
            # Reintento si no hay puerto
            if self.serial_port is None or (hasattr(self.serial_port, "is_open") and not self.serial_port.is_open):
                self._set_connected(False)
                time.sleep(self._reconnect_sec)
                self._open_port()
                continue

            try:
                n = getattr(self.serial_port, "in_waiting", 0)
                data = self.serial_port.read(n if n > 0 else 1)

                if data:
                    self._rx_buf.extend(data)
                    self._parse_rx_buffer()
                    self._set_connected(True)

            except (serial.SerialException, OSError, PermissionError) as e:
                print("⚠️ Error leyendo serial:", e)
                self._close_port()
                time.sleep(self._reconnect_sec)

            except Exception as e:
                print("⚠️ Error inesperado serial:", e)
                self._close_port()
                time.sleep(self._reconnect_sec)

    # =====================================================
    # ----------------- SEND COMMANDS ---------------------
    # =====================================================
    def send_mux_command(self, state: int):
        """
        Envía comando al ESP32 para cambiar derivada.
        Default (Arduino): 'STATE_3\\n'

        Si usas firmware del compañero (que acepta "0".."5"):
            MUX_COMMAND_FORMAT = "{state}\\n"
        """
        if not (self.serial_port and getattr(self.serial_port, "is_open", False)):
            self._set_connected(False)
            return

        try:
            st = int(state) & 0x07
            cmd = self._mux_cmd_fmt.format(state=st)
            self.serial_port.write(cmd.encode())
        except Exception as e:
            print("❌ Error enviando comando:", e)
            self._close_port()

    def stop(self):
        self.running = False
        self._close_port()
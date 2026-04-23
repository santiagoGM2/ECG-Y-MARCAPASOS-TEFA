import tkinter as tk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import time

from . import config
from .data_model import AppState
from .serial_handler import SerialReader
from .peak_detection import detect_r_peaks, calculate_bpm


# =====================================================
# -------------------- THEMES -------------------------
# =====================================================

LIGHT_JURY_THEME = {
    "name": "Jury Light Theme",
    "bg": "#F4F8FB",
    "panel": "#FFFFFF",
    "border": "#D9E2EC",
    "text": "#1F2937",
    "muted": "#6B7280",
    "title": "#0F3D5E",
    "primary": "#1976D2",
    "primary_active": "#1565C0",
    "accent": "#14B8A6",
    "accent_active": "#0F9E91",
    "success": "#2EAF6D",
    "warning": "#F59E0B",
    "danger": "#D32F2F",
    "danger_active": "#B71C1C",
    "neutral_bg": "#EEF3F8",
    "neutral_fg": "#425466",
    "info_bg": "#E8F1FB",
    "info_fg": "#1565C0",
    "accent_bg": "#E8FCF9",
    "accent_fg": "#0F766E",
    "success_bg": "#EAF8F0",
    "success_fg": "#1F8E56",
    "warning_bg": "#FFF4DB",
    "warning_fg": "#B87900",
    "danger_bg": "#FDECEC",
    "danger_fg": "#C62828",
    "button_text": "#FFFFFF",
    "plot_bg": "#FFFFFF",
    "plot_border": "#D9E2EC",
    "plot_text": "#324A5F",
    "grid": "#D6E1EB",
    "ecg_line": "#14B8A6",
    "peak": "#D32F2F",
    "baseline": "#94A3B8",
}

DARK_ICU_THEME = {
    "name": "ICU Dark Theme",
    "bg": "#0B1220",
    "panel": "#111827",
    "border": "#1F2937",
    "text": "#E5E7EB",
    "muted": "#94A3B8",
    "title": "#F8FAFC",
    "primary": "#3B82F6",
    "primary_active": "#2563EB",
    "accent": "#22D3EE",
    "accent_active": "#06B6D4",
    "success": "#10B981",
    "warning": "#FBBF24",
    "danger": "#EF4444",
    "danger_active": "#DC2626",
    "neutral_bg": "#1B2636",
    "neutral_fg": "#CBD5E1",
    "info_bg": "#13233B",
    "info_fg": "#60A5FA",
    "accent_bg": "#0F2E2B",
    "accent_fg": "#2DD4BF",
    "success_bg": "#0F2A23",
    "success_fg": "#34D399",
    "warning_bg": "#3A2A0D",
    "warning_fg": "#FBBF24",
    "danger_bg": "#3A1418",
    "danger_fg": "#F87171",
    "button_text": "#FFFFFF",
    "plot_bg": "#0F172A",
    "plot_border": "#243244",
    "plot_text": "#E5E7EB",
    "grid": "#233244",
    "ecg_line": "#22D3EE",
    "peak": "#F87171",
    "baseline": "#64748B",
}

THEMES = {
    "light_jury": LIGHT_JURY_THEME,   # Opción A
    "dark_icu": DARK_ICU_THEME,       # Opción B
}

#ACTIVE_THEME_NAME = "light_jury"
ACTIVE_THEME_NAME = "dark_icu"


class ECGApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.theme = THEMES[ACTIVE_THEME_NAME]

        self.title("ECG Vital Signs Monitor")
        self.geometry("1500x930")
        self.minsize(1280, 760)
        self.configure(bg=self.theme["bg"])

        self.is_running = True

        # Estado principal
        self.app_state = AppState(master=self)
        self.serial_reader = SerialReader(self.app_state)

        # Control MUX
        self.previous_mux_state = self.app_state.current_mux_state
        self.last_auto_change_time = time.time()

        # BPM / marcapasos
        self.last_r_abs_sample = None
        self.last_r_time = None

        # ========================
        # Variables editables UI
        # ========================
        self.auto_switch_interval_var = tk.DoubleVar(
            value=float(getattr(config, "AUTO_SWITCH_INTERVAL", 3.0))
        )

        self.refresh_interval_var = tk.IntVar(
            value=int(getattr(config, "REFRESH_INTERVAL", 80))
        )

        self.pace_amplitude_var = tk.DoubleVar(
            value=float(getattr(config, "PACE_SPIKE_AMPLITUDE", 0.8))
        )

        self.pace_alert_hold_var = tk.DoubleVar(
            value=float(
                getattr(
                    config,
                    "PACE_UI_ALERT_SEC",
                    getattr(config, "PACE_ALERT_HOLD_SEC", 1.0)
                )
            )
        )

        sample_rate = int(getattr(config, "SAMPLE_RATE", 1000))
        default_width_samples = int(getattr(config, "PACE_SPIKE_WIDTH_SAMPLES", 4))
        default_duration_ms = (default_width_samples / sample_rate) * 1000.0

        self.pace_duration_options = [f"{i} ms" for i in range(1, 31)] + ["1000 ms (1 s)"]
        self.pace_duration_ms_var = tk.StringVar(
            value=self._duration_ms_to_label(default_duration_ms)
        )

        self._create_widgets()

        self._normalize_pace_duration_input()

        # Estado visual inicial
        self.update_derivation_label()
        self.update_mode_display()
        self.update_pacemaker_alert()
        self._update_status_basic()
        self._update_alarm_panel()
        self._update_acquisition_panel()
        self._update_pace_parameter_panel()
        self._update_header_connection()
        self._update_clock()

        self.serial_reader.start()

        self.after(0, self.update_gui)
        self.after(200, self.check_auto_mode)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # =====================================================
    # ---------------- SAFE HELPERS -----------------------
    # =====================================================

    def _safe_float(self, value, default=0.0):
        try:
            raw = value.get() if hasattr(value, "get") else value
            return float(raw)
        except Exception:
            return float(default)

    def _safe_int(self, value, default=0):
        try:
            raw = value.get() if hasattr(value, "get") else value
            return int(float(raw))
        except Exception:
            return int(default)

    def _get_config_label(self, attr_name, default_value):
        return getattr(config, attr_name, default_value)

    def _duration_ms_to_label(self, ms):
        try:
            ms = float(ms)
        except Exception:
            ms = 4.0

        if ms >= 1000:
            return "1000 ms (1 s)"

        ms = int(round(max(1, min(30, ms))))
        return f"{ms} ms"

    def _get_pace_duration_ms(self):
        raw = str(self.pace_duration_ms_var.get()).strip().lower()

        if "1000" in raw or "1 s" in raw or raw == "1s":
            return 1000.0

        numeric = "".join(ch for ch in raw if (ch.isdigit() or ch == "."))
        try:
            ms = float(numeric)
        except Exception:
            ms = 4.0

        ms = max(1.0, min(30.0, ms))
        return ms

    def _normalize_pace_duration_input(self, event=None):
        ms = self._get_pace_duration_ms()
        self.pace_duration_ms_var.set(self._duration_ms_to_label(ms))

    def _get_current_refresh_interval(self):
        return max(20, self._safe_int(
            self.refresh_interval_var,
            getattr(config, "REFRESH_INTERVAL", 80)
        ))

    def _get_current_auto_switch_interval(self):
        return max(0.5, self._safe_float(
            self.auto_switch_interval_var,
            getattr(config, "AUTO_SWITCH_INTERVAL", 3.0)
        ))

    def _get_current_pace_amplitude(self):
        return max(0.0, self._safe_float(
            self.pace_amplitude_var,
            getattr(config, "PACE_SPIKE_AMPLITUDE", 0.8)
        ))

    def _get_current_pace_hold(self):
        return max(
            0.1,
            self._safe_float(
                self.pace_alert_hold_var,
                getattr(
                    config,
                    "PACE_UI_ALERT_SEC",
                    getattr(config, "PACE_ALERT_HOLD_SEC", 1.0)
                )
            )
        )

    # =====================================================
    # ---------------- VISUAL HELPERS ---------------------
    # =====================================================

    def _create_widgets(self):
        root = tk.Frame(self, bg=self.theme["bg"])
        root.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._create_header(root)

        body = tk.Frame(root, bg=self.theme["bg"])
        body.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        plot_card = self._create_card(
            body,
            title="Real-Time ECG Signal",
            subtitle="Live waveform visualization with R-peak tracking"
        )
        plot_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        self._create_plots(plot_card.content)

        sidebar_container = tk.Frame(body, bg=self.theme["bg"], width=390)
        sidebar_container.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar_container.pack_propagate(False)

        sidebar = self._create_scrollable_sidebar(sidebar_container)

        self._create_derivation_panel(sidebar)
        self._create_mode_panel(sidebar)
        self._create_status_panel(sidebar)
        self._create_pacemaker_panel(sidebar)
        self._create_alarm_panel(sidebar)
        self._create_acquisition_panel(sidebar)

    def _create_header(self, parent):
        header = tk.Frame(
            parent,
            bg=self.theme["panel"],
            highlightthickness=1,
            highlightbackground=self.theme["border"],
            bd=0
        )
        header.pack(fill=tk.X)

        left = tk.Frame(header, bg=self.theme["panel"])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=18, pady=16)

        tk.Label(
            left,
            text="ECG Vital Signs Monitor",
            bg=self.theme["panel"],
            fg=self.theme["title"],
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")

        tk.Label(
            left,
            text="6-lead acquisition • biomedical interface • real-time analysis",
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(5, 0))

        right = tk.Frame(header, bg=self.theme["panel"])
        right.pack(side=tk.RIGHT, padx=18, pady=16)

        self.theme_badge = tk.Label(
            right,
            text=self.theme["name"],
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
            bd=0,
        )
        self.theme_badge.pack(anchor="e", pady=(0, 8))
        self._set_badge(self.theme_badge, self.theme["name"], "accent")

        session_text = self._get_config_label("SESSION_LABEL", "SIMULATION MODE")
        self.session_badge = tk.Label(
            right,
            text=session_text,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
            bd=0,
        )
        self.session_badge.pack(anchor="e", pady=(0, 8))
        self._set_badge(self.session_badge, session_text, "info")

        self.header_connection_badge = tk.Label(
            right,
            text="ESP32 OFFLINE",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
            bd=0,
        )
        self.header_connection_badge.pack(anchor="e", pady=(0, 8))

        self.clock_label = tk.Label(
            right,
            text="--:--:--",
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            font=("Segoe UI", 12, "bold"),
        )
        self.clock_label.pack(anchor="e")

    def _create_card(self, parent, title, subtitle=None):
        outer = tk.Frame(
            parent,
            bg=self.theme["panel"],
            highlightthickness=1,
            highlightbackground=self.theme["border"],
            bd=0
        )

        header = tk.Frame(outer, bg=self.theme["panel"])
        header.pack(fill=tk.X, padx=18, pady=(16, 8))

        tk.Label(
            header,
            text=title,
            bg=self.theme["panel"],
            fg=self.theme["title"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")

        if subtitle:
            tk.Label(
                header,
                text=subtitle,
                bg=self.theme["panel"],
                fg=self.theme["muted"],
                font=("Segoe UI", 9),
            ).pack(anchor="w", pady=(4, 0))

        divider = tk.Frame(outer, bg=self.theme["border"], height=1)
        divider.pack(fill=tk.X, padx=18, pady=(0, 14))

        content = tk.Frame(outer, bg=self.theme["panel"])
        content.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 16))

        outer.content = content
        return outer

    def _create_scrollable_sidebar(self, parent):
        outer = tk.Frame(parent, bg=self.theme["bg"], bd=0, highlightthickness=0)
        outer.pack(fill=tk.BOTH, expand=True)

        self.sidebar_canvas = tk.Canvas(
            outer,
            bg=self.theme["bg"],
            highlightthickness=0,
            bd=0,
            relief="flat"
        )
        self.sidebar_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.sidebar_scrollbar = tk.Scrollbar(
            outer,
            orient="vertical",
            command=self.sidebar_canvas.yview
        )
        self.sidebar_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)

        self.sidebar_inner = tk.Frame(self.sidebar_canvas, bg=self.theme["bg"])
        self.sidebar_window = self.sidebar_canvas.create_window(
            (0, 0),
            window=self.sidebar_inner,
            anchor="nw"
        )

        self.sidebar_inner.bind("<Configure>", self._on_sidebar_frame_configure)
        self.sidebar_canvas.bind("<Configure>", self._on_sidebar_canvas_configure)

        self.sidebar_canvas.bind("<Enter>", self._bind_sidebar_mousewheel)
        self.sidebar_canvas.bind("<Leave>", self._unbind_sidebar_mousewheel)
        self.sidebar_inner.bind("<Enter>", self._bind_sidebar_mousewheel)
        self.sidebar_inner.bind("<Leave>", self._unbind_sidebar_mousewheel)

        return self.sidebar_inner

    def _on_sidebar_frame_configure(self, event=None):
        bbox = self.sidebar_canvas.bbox("all")
        if bbox is not None:
            self.sidebar_canvas.configure(scrollregion=bbox)

    def _on_sidebar_canvas_configure(self, event):
        self.sidebar_canvas.itemconfig(self.sidebar_window, width=event.width)

    def _bind_sidebar_mousewheel(self, event=None):
        self.sidebar_canvas.bind_all("<MouseWheel>", self._on_sidebar_mousewheel)
        self.sidebar_canvas.bind_all("<Button-4>", self._on_sidebar_mousewheel)
        self.sidebar_canvas.bind_all("<Button-5>", self._on_sidebar_mousewheel)

    def _unbind_sidebar_mousewheel(self, event=None):
        self.sidebar_canvas.unbind_all("<MouseWheel>")
        self.sidebar_canvas.unbind_all("<Button-4>")
        self.sidebar_canvas.unbind_all("<Button-5>")

    def _on_sidebar_mousewheel(self, event):
        if hasattr(event, "delta") and event.delta:
            self.sidebar_canvas.yview_scroll(int(-event.delta / 120), "units")
        elif getattr(event, "num", None) == 4:
            self.sidebar_canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.sidebar_canvas.yview_scroll(1, "units")

    def _create_action_button(self, parent, text, command, kind="primary"):
        if kind == "primary":
            bg = self.theme["primary"]
            active_bg = self.theme["primary_active"]
        elif kind == "accent":
            bg = self.theme["accent"]
            active_bg = self.theme["accent_active"]
        else:
            bg = self.theme["danger"]
            active_bg = self.theme["danger_active"]

        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=self.theme["button_text"],
            activebackground=active_bg,
            activeforeground=self.theme["button_text"],
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=11,
            highlightthickness=0,
        )
        return btn

    def _set_badge(self, widget, text, kind="neutral", font=None):
        bg_map = {
            "neutral": self.theme["neutral_bg"],
            "info": self.theme["info_bg"],
            "accent": self.theme["accent_bg"],
            "success": self.theme["success_bg"],
            "warning": self.theme["warning_bg"],
            "danger": self.theme["danger_bg"],
        }
        fg_map = {
            "neutral": self.theme["neutral_fg"],
            "info": self.theme["info_fg"],
            "accent": self.theme["accent_fg"],
            "success": self.theme["success_fg"],
            "warning": self.theme["warning_fg"],
            "danger": self.theme["danger_fg"],
        }

        widget.config(
            text=text,
            bg=bg_map[kind],
            fg=fg_map[kind],
            font=font or ("Segoe UI", 10, "bold"),
        )

    def _create_metric_row(self, parent, label_text):
        row = tk.Frame(parent, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=4)

        tk.Label(
            row,
            text=label_text,
            bg=self.theme["panel"],
            fg=self.theme["text"],
            font=("Segoe UI", 10),
        ).pack(side=tk.LEFT)

        value_label = tk.Label(
            row,
            text="N/A",
            padx=10,
            pady=5,
            bd=0,
        )
        value_label.pack(side=tk.RIGHT)
        self._set_badge(value_label, "N/A", "neutral", font=("Segoe UI", 9, "bold"))
        return value_label

    def _style_input_widget(self, widget):
        try:
            widget.configure(
                bg=self.theme["neutral_bg"],
                fg=self.theme["text"],
                insertbackground=self.theme["text"],
                relief="flat",
                bd=1,
                highlightthickness=1,
                highlightbackground=self.theme["border"],
                highlightcolor=self.theme["primary"],
                buttonbackground=self.theme["panel"],
                disabledbackground=self.theme["neutral_bg"],
                readonlybackground=self.theme["neutral_bg"],
                selectbackground=self.theme["primary"],
                selectforeground=self.theme["button_text"],
                justify="center",
            )
        except Exception:
            pass
        return widget

    def _make_numeric_spinbox(self, parent, textvariable, from_, to, increment, width=10):
        sb = tk.Spinbox(
            parent,
            from_=from_,
            to=to,
            increment=increment,
            textvariable=textvariable,
            width=width,
            font=("Segoe UI", 10),
            justify="center",
        )
        return self._style_input_widget(sb)

    def _make_values_spinbox(self, parent, textvariable, values, width=14):
        sb = tk.Spinbox(
            parent,
            values=values,
            textvariable=textvariable,
            width=width,
            font=("Segoe UI", 10),
            justify="center",
            wrap=False,
        )
        self._style_input_widget(sb)
        sb.bind("<FocusOut>", self._normalize_pace_duration_input)
        sb.bind("<Return>", self._normalize_pace_duration_input)
        return sb

    def _add_control_row(self, parent, label_text, help_text, control_builder):
        row = tk.Frame(parent, bg=self.theme["panel"])
        row.pack(fill=tk.X, pady=6)

        left = tk.Frame(row, bg=self.theme["panel"])
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        right = tk.Frame(row, bg=self.theme["panel"])
        right.pack(side=tk.RIGHT, anchor="e")

        tk.Label(
            left,
            text=label_text,
            bg=self.theme["panel"],
            fg=self.theme["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        if help_text:
            tk.Label(
                left,
                text=help_text,
                bg=self.theme["panel"],
                fg=self.theme["muted"],
                font=("Segoe UI", 8),
                justify="left",
                wraplength=180,
            ).pack(anchor="w", pady=(2, 0))

        control_widget = control_builder(right)
        control_widget.pack(anchor="e")

    def _update_clock(self):
        if not self.is_running:
            return
        self.clock_label.config(text=time.strftime("%H:%M:%S"))
        self.after(1000, self._update_clock)

    def _update_header_connection(self):
        if self.app_state.esp32_connected:
            self._set_badge(self.header_connection_badge, "ESP32 ONLINE", "success")
        else:
            self._set_badge(self.header_connection_badge, "ESP32 OFFLINE", "danger")

    # =====================================================
    # ---------------- NO SIGNAL HELPERS ------------------
    # =====================================================

    def _update_no_signal_state(self, present: bool):
        now = time.time()

        min_sec = getattr(
            config,
            "NO_SIGNAL_TIMEOUT_SEC",
            getattr(config, "NO_SIGNAL_MIN_SECONDS", 1.0),
        )

        if present:
            self.app_state.no_signal = False
            self.app_state.no_signal_since = None
            return

        if self.app_state.no_signal_since is None:
            self.app_state.no_signal_since = now

        if (now - self.app_state.no_signal_since) >= float(min_sec):
            self.app_state.no_signal = True

    def _signal_present(self, y_np: np.ndarray) -> bool:
        if y_np is None or len(y_np) < 20:
            return False

        win_samples = getattr(
            config,
            "NO_SIGNAL_WINDOW_SAMPLES",
            int(getattr(config, "SAMPLE_RATE", 1000) * 0.5),
        )
        N = min(len(y_np), int(win_samples))
        seg = y_np[-N:]

        p2p_thr = getattr(
            config,
            "NO_SIGNAL_P2P_V",
            getattr(config, "NO_SIGNAL_P2P_THRESHOLD", 0.02),
        )
        std_thr = getattr(config, "NO_SIGNAL_STD_V", 0.005)

        p2p = float(np.max(seg) - np.min(seg))
        std = float(np.std(seg))

        return (p2p >= float(p2p_thr)) or (std >= float(std_thr))

    # =====================================================
    # ------------------ PLOTS ----------------------------
    # =====================================================

    def _create_plots(self, parent):
        self.fig, self.ax = plt.subplots(figsize=(10, 6), dpi=100)
        self.fig.patch.set_facecolor(self.theme["panel"])
        self.ax.set_facecolor(self.theme["plot_bg"])

        for spine in self.ax.spines.values():
            spine.set_color(self.theme["plot_border"])

        self.ax.tick_params(colors=self.theme["plot_text"], labelsize=10)
        self.ax.grid(True, color=self.theme["grid"], alpha=0.60, linewidth=0.8)
        self.ax.set_title("ECG Signal", color=self.theme["plot_text"], fontsize=16, pad=12)
        self.ax.set_ylabel("Voltage / ADC", color=self.theme["plot_text"], fontsize=11)
        self.ax.set_xlabel("Samples", color=self.theme["plot_text"], fontsize=11)
        self.ax.margins(x=0)

        self.baseline_line = self.ax.axhline(
            0,
            color=self.theme["baseline"],
            linewidth=0.9,
            alpha=0.65
        )

        self.line, = self.ax.plot(
            [],
            [],
            linewidth=2.0,
            color=self.theme["ecg_line"],
            solid_capstyle="round"
        )

        self.peaks_line, = self.ax.plot(
            [],
            [],
            linestyle="",
            marker="o",
            markersize=5,
            color=self.theme["peak"],
        )

        self.fig.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.10)

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.pack(fill=tk.BOTH, expand=True)
        canvas_widget.configure(bg=self.theme["panel"], highlightthickness=0)

    # =====================================================
    # -------------- DERIVATION PANEL ---------------------
    # =====================================================

    def _create_derivation_panel(self, parent):
        card = self._create_card(
            parent,
            title="Derivation Control",
            subtitle="Lead selection and navigation"
        )
        card.pack(fill=tk.X, pady=(0, 12))

        self.current_derivation_label = tk.Label(
            card.content,
            text="I DERIVADA",
            padx=14,
            pady=8,
            bd=0,
        )
        self.current_derivation_label.pack(fill=tk.X, pady=(0, 10))
        self._set_badge(
            self.current_derivation_label,
            "I DERIVADA",
            "info",
            font=("Segoe UI", 12, "bold")
        )

        tk.Label(
            card.content,
            text="Active lead currently displayed in the ECG window.",
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=300,
        ).pack(anchor="w", pady=(0, 12))

        self._create_action_button(
            card.content,
            text="Next Derivation",
            command=self.next_derivation_manual,
            kind="primary",
        ).pack(fill="x")

    def next_derivation_manual(self):
        self.app_state.next_derivation()
        self.app_state.last_manual_action_time = time.time()
        self.app_state.operation_mode.set(config.MODE_MANUAL)

        self._send_mux_if_changed()
        self.update_derivation_label()

    def update_derivation_label(self):
        state = self.app_state.current_mux_state
        label = self.app_state.mux_state_label.get(state, "N/A")

        self._set_badge(
            self.current_derivation_label,
            f"{label} DERIVADA",
            "info",
            font=("Segoe UI", 12, "bold")
        )

        if hasattr(self, "ax"):
            self.ax.set_title(f"ECG Signal • {label}", color=self.theme["plot_text"], fontsize=16, pad=12)
            if hasattr(self, "canvas"):
                self.canvas.draw_idle()

    # =====================================================
    # ---------------- MODE PANEL -------------------------
    # =====================================================

    def _create_mode_panel(self, parent):
        card = self._create_card(
            parent,
            title="Operation Mode",
            subtitle="Automatic scan or manual control"
        )
        card.pack(fill=tk.X, pady=(0, 12))

        self.mode_label = tk.Label(
            card.content,
            text="MANUAL MODE",
            padx=14,
            pady=8,
            bd=0,
        )
        self.mode_label.pack(fill=tk.X, pady=(0, 10))

        self.mode_detail_label = tk.Label(
            card.content,
            text="Waiting for mode update.",
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=300,
        )
        self.mode_detail_label.pack(anchor="w")

    def update_mode_display(self):
        mode = self.app_state.operation_mode.get()

        if mode == config.MODE_AUTO:
            self._set_badge(
                self.mode_label,
                "AUTO MODE",
                "accent",
                font=("Segoe UI", 12, "bold")
            )
            self.mode_detail_label.config(
                text="Automatic derivation cycling is active."
            )
        else:
            self._set_badge(
                self.mode_label,
                "MANUAL MODE",
                "info",
                font=("Segoe UI", 12, "bold")
            )

            remaining = max(
                0,
                int(config.AUTO_TIMEOUT - (time.time() - self.app_state.last_manual_action_time))
            )
            self.mode_detail_label.config(
                text=f"Manual control active. Auto mode resumes in about {remaining}s."
            )

    # =====================================================
    # ---------------- STATUS PANEL -----------------------
    # =====================================================

    def _create_status_panel(self, parent):
        card = self._create_card(
            parent,
            title="System Status",
            subtitle="Connection and acquisition overview"
        )
        card.pack(fill=tk.X, pady=(0, 12))

        self.status_labels = {}
        for label in ["ESP32", "Samples", "BPM", "Derivation"]:
            self.status_labels[label] = self._create_metric_row(card.content, label)

    def _update_status_basic(self):
        if self.app_state.esp32_connected:
            self._set_badge(self.status_labels["ESP32"], "ONLINE", "success")
        else:
            self._set_badge(self.status_labels["ESP32"], "OFFLINE", "danger")

        self._set_badge(
            self.status_labels["Samples"],
            f"{int(self.app_state.sample_count):,}",
            "neutral"
        )

        st = self.app_state.current_mux_state
        derivation = self.app_state.mux_state_label.get(st, "N/A")
        self._set_badge(self.status_labels["Derivation"], derivation, "info")

        self._update_header_connection()

    # =====================================================
    # -------------- PACEMAKER / TRIGGER ------------------
    # =====================================================

    def _create_pacemaker_panel(self, parent):
        card = self._create_card(
            parent,
            title="Pacemaker / Trigger",
            subtitle="Spike detection, software trigger and long-pulse demo option"
        )
        card.pack(fill=tk.X, pady=(0, 12))

        self.pacemaker_label = tk.Label(
            card.content,
            text="NO ALERT",
            padx=14,
            pady=10,
            bd=0,
        )
        self.pacemaker_label.pack(fill=tk.X, pady=(0, 10))
        self._set_badge(
            self.pacemaker_label,
            "NO ALERT",
            "success",
            font=("Segoe UI", 12, "bold")
        )

        self.pacemaker_detail_label = tk.Label(
            card.content,
            text="No pacemaker pulse detected.",
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=300,
        )
        self.pacemaker_detail_label.pack(anchor="w", pady=(0, 12))

        self.trigger_mode_chip = self._create_metric_row(card.content, "Trigger input")
        self.trigger_state_chip = self._create_metric_row(card.content, "Trigger state")
        self.pace_amplitude_chip = self._create_metric_row(card.content, "Pulse amplitude")
        self.pace_duration_chip = self._create_metric_row(card.content, "Pulse duration")
        self.pace_hold_chip = self._create_metric_row(card.content, "Alert hold")

        self._set_badge(self.trigger_mode_chip, "SOFTWARE / PUSH BUTTON", "info")
        self._set_badge(self.trigger_state_chip, "READY", "accent")

        controls = tk.Frame(card.content, bg=self.theme["panel"])
        controls.pack(fill=tk.X, pady=(10, 4))

        self._add_control_row(
            controls,
            "Amplitude",
            "Pulse height shown in the ECG signal.",
            lambda parent: self._make_numeric_spinbox(
                parent,
                self.pace_amplitude_var,
                from_=0.1,
                to=3.0,
                increment=0.1,
                width=10
            )
        )

        self._add_control_row(
            controls,
            "Duration",
            "Options from 1 ms to 30 ms plus 1000 ms (1 s).",
            lambda parent: self._make_values_spinbox(
                parent,
                self.pace_duration_ms_var,
                values=self.pace_duration_options,
                width=14
            )
        )

        self._add_control_row(
            controls,
            "Alert hold",
            "How long the pacemaker alert stays visible.",
            lambda parent: self._make_numeric_spinbox(
                parent,
                self.pace_alert_hold_var,
                from_=0.1,
                to=5.0,
                increment=0.1,
                width=10
            )
        )

        tk.Label(
            card.content,
            text="Use the trigger button now. Later you can map the same action to the external physical push-button.",
            bg=self.theme["panel"],
            fg=self.theme["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=300,
        ).pack(anchor="w", pady=(10, 12))

        self._create_action_button(
            card.content,
            text="Trigger Pacemaker Pulse",
            command=self.on_pace_pulse,
            kind="danger",
        ).pack(fill="x")

    def _update_pace_parameter_panel(self):
        amp = self._get_current_pace_amplitude()
        dur = self._get_pace_duration_ms()
        hold = self._get_current_pace_hold()

        self._set_badge(self.pace_amplitude_chip, f"{amp:.2f} V", "danger")
        if dur >= 1000:
            self._set_badge(self.pace_duration_chip, "1000 ms", "warning")
        else:
            self._set_badge(self.pace_duration_chip, f"{int(round(dur))} ms", "info")
        self._set_badge(self.pace_hold_chip, f"{hold:.1f} s", "accent")

    def _inject_pacemaker_pulse(self, y_signal):
        y_out = np.array(y_signal, dtype=float).copy()

        sample_rate = int(getattr(config, "SAMPLE_RATE", 1000))
        duration_ms = self._get_pace_duration_ms()
        width_samples = max(1, int(round(sample_rate * duration_ms / 1000.0)))
        amp = self._get_current_pace_amplitude()

        if len(y_out) < 5:
            return y_out

        end_idx = max(2, len(y_out) - 3)
        start_idx = max(1, end_idx - width_samples)

        left_ref_start = max(0, start_idx - 20)
        left_ref_end = max(left_ref_start + 1, start_idx)
        local_baseline = float(np.median(y_out[left_ref_start:left_ref_end]))

        y_out[start_idx:start_idx + width_samples] = local_baseline + amp

        if start_idx - 1 >= 0:
            y_out[start_idx - 1] = local_baseline
        if start_idx + width_samples < len(y_out):
            y_out[start_idx + width_samples] = local_baseline

        return y_out

    def on_pace_pulse(self):
        self.app_state.pace_pulse_pending = True
        now = time.time()
        self.app_state.pace_alert_until = now + self._get_current_pace_hold()

    def update_pacemaker_alert(self):
        now = time.time()

        if now < getattr(self.app_state, "pace_alert_until", 0.0):
            self._set_badge(
                self.pacemaker_label,
                "PACEMAKER DETECTED",
                "danger",
                font=("Segoe UI", 12, "bold")
            )
            self._set_badge(self.trigger_state_chip, "TRIGGERED", "danger")
            self.pacemaker_detail_label.config(
                text="Pacing spike detected or simulated in the current waveform."
            )
            return

        if now < getattr(self.app_state, "blank_until", 0.0):
            self._set_badge(
                self.pacemaker_label,
                "SWITCHING...",
                "warning",
                font=("Segoe UI", 12, "bold")
            )
            self._set_badge(self.trigger_state_chip, "WAITING", "warning")
            self.pacemaker_detail_label.config(
                text="Lead change in progress. Pacemaker detection is temporarily paused."
            )
            return

        if getattr(self.app_state, "no_signal", False):
            self._set_badge(
                self.pacemaker_label,
                "NO SIGNAL",
                "neutral",
                font=("Segoe UI", 12, "bold")
            )
            self._set_badge(self.trigger_state_chip, "READY", "neutral")
            self.pacemaker_detail_label.config(
                text="No valid signal available for pacing analysis."
            )
            return

        self._set_badge(
            self.pacemaker_label,
            "NO ALERT",
            "success",
            font=("Segoe UI", 12, "bold")
        )
        self._set_badge(self.trigger_state_chip, "READY", "accent")
        self.pacemaker_detail_label.config(
            text="No pacemaker pulse detected."
        )

    # =====================================================
    # ---------------- ALARM SETTINGS ---------------------
    # =====================================================

    def _create_alarm_panel(self, parent=None):
        if parent is not None:
            card = self._create_card(
                parent,
                title="Alarm Settings",
                subtitle="Current signal and detection thresholds"
            )
            card.pack(fill=tk.X, pady=(0, 12))

            self.alarm_signal_chip = self._create_metric_row(card.content, "Signal state")
            self.alarm_rthr_chip = self._create_metric_row(card.content, "R threshold")
            self.alarm_rdist_chip = self._create_metric_row(card.content, "R distance")
            self.alarm_pace_deriv_chip = self._create_metric_row(card.content, "Pacer deriv.")

            tk.Label(
                card.content,
                text="This section shows the active limits used by the detection logic during the demo.",
                bg=self.theme["panel"],
                fg=self.theme["muted"],
                font=("Segoe UI", 9),
                justify="left",
                wraplength=300,
            ).pack(anchor="w", pady=(10, 0))
            return

    def _update_alarm_panel(self, in_blanking=False):
        try:
            r_thr = self._safe_float(self.app_state.r_threshold, 0.0)
            self._set_badge(self.alarm_rthr_chip, f"{r_thr:.3f}", "info")
        except Exception:
            self._set_badge(self.alarm_rthr_chip, "N/A", "neutral")

        try:
            r_dist = self._safe_int(self.app_state.r_distance, 0)
            self._set_badge(self.alarm_rdist_chip, f"{r_dist}", "info")
        except Exception:
            self._set_badge(self.alarm_rdist_chip, "N/A", "neutral")

        try:
            pace_deriv = float(getattr(config, "PACE_DERIV_THRESHOLD", 0.6))
            self._set_badge(self.alarm_pace_deriv_chip, f"{pace_deriv:.2f}", "accent")
        except Exception:
            self._set_badge(self.alarm_pace_deriv_chip, "N/A", "neutral")

        if in_blanking:
            self._set_badge(self.alarm_signal_chip, "SWITCHING", "warning")
        elif getattr(self.app_state, "no_signal", False):
            self._set_badge(self.alarm_signal_chip, "NO SIGNAL", "neutral")
        else:
            self._set_badge(self.alarm_signal_chip, "SIGNAL OK", "success")

    # =====================================================
    # -------------- ACQUISITION SETTINGS -----------------
    # =====================================================

    def _create_acquisition_panel(self, parent=None):
        if parent is not None:
            card = self._create_card(
                parent,
                title="Acquisition Settings",
                subtitle="Current acquisition and editable display parameters"
            )
            card.pack(fill=tk.X, pady=(0, 18))

            self.acq_sample_rate_chip = self._create_metric_row(card.content, "Sample rate")
            self.acq_window_chip = self._create_metric_row(card.content, "Window size")
            self.acq_gain_chip = self._create_metric_row(card.content, "ECG gain")
            self.acq_ymax_chip = self._create_metric_row(card.content, "Y max")
            self.acq_refresh_chip = self._create_metric_row(card.content, "Refresh")
            self.acq_auto_switch_chip = self._create_metric_row(card.content, "Auto switch")

            controls = tk.Frame(card.content, bg=self.theme["panel"])
            controls.pack(fill=tk.X, pady=(10, 4))

            self._add_control_row(
                controls,
                "Window size",
                "Visible number of samples in the graph.",
                lambda parent: self._make_numeric_spinbox(
                    parent,
                    self.app_state.window_size,
                    from_=500,
                    to=10000,
                    increment=100,
                    width=10
                )
            )

            self._add_control_row(
                controls,
                "ECG gain",
                "Visual amplification applied to the signal.",
                lambda parent: self._make_numeric_spinbox(
                    parent,
                    self.app_state.ecg_gain,
                    from_=0.1,
                    to=10.0,
                    increment=0.1,
                    width=10
                )
            )

            self._add_control_row(
                controls,
                "Y max",
                "Vertical display limit of the ECG plot.",
                lambda parent: self._make_numeric_spinbox(
                    parent,
                    self.app_state.y_max,
                    from_=0.5,
                    to=10.0,
                    increment=0.1,
                    width=10
                )
            )

            self._add_control_row(
                controls,
                "Refresh",
                "GUI refresh interval in milliseconds.",
                lambda parent: self._make_numeric_spinbox(
                    parent,
                    self.refresh_interval_var,
                    from_=20,
                    to=500,
                    increment=10,
                    width=10
                )
            )

            self._add_control_row(
                controls,
                "Auto switch",
                "Seconds between lead changes in AUTO mode.",
                lambda parent: self._make_numeric_spinbox(
                    parent,
                    self.auto_switch_interval_var,
                    from_=0.5,
                    to=20.0,
                    increment=0.5,
                    width=10
                )
            )

            tk.Label(
                card.content,
                text="These values update the monitor behavior live, useful during the final presentation.",
                bg=self.theme["panel"],
                fg=self.theme["muted"],
                font=("Segoe UI", 9),
                justify="left",
                wraplength=300,
            ).pack(anchor="w", pady=(10, 0))
            return

    def _update_acquisition_panel(self):
        try:
            sample_rate = int(getattr(config, "SAMPLE_RATE", 1000))
            self._set_badge(self.acq_sample_rate_chip, f"{sample_rate} Hz", "info")
        except Exception:
            self._set_badge(self.acq_sample_rate_chip, "N/A", "neutral")

        try:
            window_size = max(100, self._safe_int(self.app_state.window_size, 1000))
            self._set_badge(self.acq_window_chip, f"{window_size}", "neutral")
        except Exception:
            self._set_badge(self.acq_window_chip, "N/A", "neutral")

        try:
            gain = max(0.1, self._safe_float(self.app_state.ecg_gain, 1.0))
            self._set_badge(self.acq_gain_chip, f"{gain:.2f}", "accent")
        except Exception:
            self._set_badge(self.acq_gain_chip, "N/A", "neutral")

        try:
            y_max = max(0.1, self._safe_float(self.app_state.y_max, 1.0))
            self._set_badge(self.acq_ymax_chip, f"{y_max:.2f}", "neutral")
        except Exception:
            self._set_badge(self.acq_ymax_chip, "N/A", "neutral")

        try:
            refresh = self._get_current_refresh_interval()
            self._set_badge(self.acq_refresh_chip, f"{refresh} ms", "info")
        except Exception:
            self._set_badge(self.acq_refresh_chip, "N/A", "neutral")

        try:
            auto_switch = self._get_current_auto_switch_interval()
            self._set_badge(self.acq_auto_switch_chip, f"{auto_switch:.1f} s", "info")
        except Exception:
            self._set_badge(self.acq_auto_switch_chip, "N/A", "neutral")

    # =====================================================
    # ---------------- MAIN UPDATE ------------------------
    # =====================================================

    def update_gui(self):
        if not self.is_running:
            return

        now = time.time()
        win = max(100, self._safe_int(self.app_state.window_size, 1000))
        gain = max(0.1, self._safe_float(self.app_state.ecg_gain, 1.0))
        y_max = max(0.5, self._safe_float(self.app_state.y_max, 2.0))

        in_blanking = now < getattr(self.app_state, "blank_until", 0.0)

        with self.app_state.data_lock:
            x_buf = list(self.app_state.time_buffer)
            y_buf = list(self.app_state.voltage_buffer)
            sc = int(self.app_state.sample_count)

        have_xy = (len(x_buf) > 1) and (len(x_buf) == len(y_buf))

        if have_xy:
            xw = x_buf[-win:]
            yw = np.array(y_buf[-win:], dtype=float)
        else:
            end = sc
            start = max(0, end - win)
            if end <= start:
                xw = list(range(0, max(2, win)))
            else:
                xw = list(range(start, end))
            yw = np.zeros(len(xw), dtype=float)

        present = False if in_blanking else self._signal_present(yw)
        self._update_no_signal_state(present)

        self._update_status_basic()
        self.update_mode_display()
        self._update_alarm_panel(in_blanking=in_blanking)
        self._update_acquisition_panel()
        self._update_pace_parameter_panel()

        if in_blanking or getattr(self.app_state, "no_signal", False):
            baseline = np.zeros_like(yw)

            self.line.set_data(xw, baseline)
            self.peaks_line.set_data([], [])

            self.ax.set_ylim(-y_max, y_max)
            if len(xw) > 1:
                self.ax.set_xlim(xw[0], xw[-1])
            else:
                self.ax.set_xlim(0, max(1, win))

            self.canvas.draw_idle()

            if in_blanking:
                self._set_badge(self.status_labels["BPM"], "SWITCHING...", "warning")
            else:
                self._set_badge(self.status_labels["BPM"], "NO SIGNAL", "neutral")

            self.update_pacemaker_alert()
            self.after(self._get_current_refresh_interval(), self.update_gui)
            return

        N = min(len(yw), 300)
        dc = float(np.median(yw[-N:]))
        y_centered = (yw - dc) * gain
        
        # # Invertir solo la derivada aVR
        # state = self.app_state.current_mux_state
        # lead_label = str(self.app_state.mux_state_label.get(state, "")).strip().lower()

        # if lead_label == "avr":
        #     y_centered = -y_centered

        if getattr(self.app_state, "pace_pulse_pending", False):
            y_centered = self._inject_pacemaker_pulse(y_centered)
            self.app_state.pace_pulse_pending = False
            self.app_state.pace_alert_until = now + self._get_current_pace_hold()

        deriv_thr = float(getattr(config, "PACE_DERIV_THRESHOLD", 0.6))
        dy = np.diff(y_centered)

        if len(dy) > 0 and (np.max(np.abs(dy)) > deriv_thr):
            self.app_state.pace_alert_until = now + self._get_current_pace_hold()

        self.line.set_data(xw, y_centered)
        self.ax.set_ylim(-y_max, y_max)

        if len(xw) > 1:
            self.ax.set_xlim(xw[0], xw[-1])
        else:
            self.ax.set_xlim(0, max(1, win))

        peaks = detect_r_peaks(
            y_centered,
            self.app_state.r_threshold.get(),
            self.app_state.r_distance.get(),
        )

        self.peaks_line.set_data(
            [xw[i] for i in peaks],
            [y_centered[i] for i in peaks],
        )

        self.canvas.draw_idle()

        bpm = calculate_bpm(peaks, getattr(config, "SAMPLE_RATE", 1000))
        if bpm > 0:
            self._set_badge(self.status_labels["BPM"], f"{bpm:.0f} BPM", "success")
        else:
            self._set_badge(self.status_labels["BPM"], "CALCULATING", "warning")

        self.update_pacemaker_alert()

        self.after(self._get_current_refresh_interval(), self.update_gui)

    # =====================================================
    # ---------------- AUTO MODE TIMER --------------------
    # =====================================================

    def check_auto_mode(self):
        now = time.time()

        if self.app_state.operation_mode.get() == config.MODE_MANUAL:
            if (now - self.app_state.last_manual_action_time) >= config.AUTO_TIMEOUT:
                self.app_state.operation_mode.set(config.MODE_AUTO)
                self.last_auto_change_time = now

        if self.app_state.operation_mode.get() == config.MODE_AUTO:
            if (now - self.last_auto_change_time) >= self._get_current_auto_switch_interval():
                self.app_state.next_derivation()
                self.last_auto_change_time = now
                self._send_mux_if_changed()
                self.update_derivation_label()

        self.update_mode_display()
        self.after(200, self.check_auto_mode)

    # =====================================================
    # ----------- SEND MUX ONLY IF CHANGED ----------------
    # =====================================================

    def _send_mux_if_changed(self):
        state = self.app_state.current_mux_state
        if state != self.previous_mux_state:
            self.serial_reader.send_mux_command(state)

            blank_sec = getattr(
                config,
                "DERIVATION_SWITCH_BLANK_SEC",
                getattr(config, "BLANK_AFTER_SWITCH_SEC", 2.5)
            )
            self.app_state.blank_until = time.time() + float(blank_sec)

            with self.app_state.data_lock:
                self.app_state.voltage_buffer.clear()
                self.app_state.time_buffer.clear()

            self.last_r_abs_sample = None
            self.last_r_time = None

            self.app_state.no_signal_since = None
            self.app_state.no_signal = False

            self.previous_mux_state = state

    # =====================================================
    # ---------------- CLOSE APP --------------------------
    # =====================================================

    def on_closing(self):
        self.is_running = False

        try:
            self.serial_reader.stop()
        except Exception:
            pass

        try:
            plt.close(self.fig)
        except Exception:
            pass

        self.destroy()

        import sys
        sys.exit(0)


if __name__ == "__main__":
    app = ECGApp()
    app.mainloop()
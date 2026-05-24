import shutil
from pathlib import Path

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QTextEdit, QFrame,
)

from core.state import AppState
from ui.pages._page_base_style import BASE_STYLE

_LOG_STYLE = (
    "font-family: monospace; font-size: 12px; "
    "background: rgba(16, 16, 18, 220); color: #c0ffc0; "
    "border: 1px solid rgba(62, 62, 72, 180); padding: 6px;"
)
_RES_STYLE = (
    "font-size: 11px; color: #888890; background: rgba(16,16,18,180); "
    "border: 1px solid rgba(62,62,72,120); padding: 4px 10px;"
)


def _read_cpu_temp() -> str:
    for zone in sorted(Path('/sys/class/thermal').glob('thermal_zone*/temp')):
        try:
            c = int(zone.read_text().strip()) / 1000
            return f"{c:.1f} °C"
        except Exception:
            continue
    return "N/A"


def _read_ram() -> str:
    try:
        info = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            k, v = line.split(':', 1)
            info[k.strip()] = int(v.strip().split()[0])
        total = info.get('MemTotal', 0)
        avail = info.get('MemAvailable', 0)
        used  = total - avail
        return f"{used/1024/1024:.1f} / {total/1024/1024:.1f} GB"
    except Exception:
        return "N/A"


def _read_disk() -> str:
    try:
        usage = shutil.disk_usage('/')
        free_gb  = usage.free  / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        return f"{free_gb:.1f} / {total_gb:.1f} GB free"
    except Exception:
        return "N/A"


class FlashPage(QWidget):
    flash_done = Signal(bool, str)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._runner = None
        self._res_timer = QTimer(self)
        self._res_timer.setInterval(2000)
        self._res_timer.timeout.connect(self._update_resources)
        self.setStyleSheet(BASE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(16)

        self._title = QLabel("Flashing…")
        self._title.setObjectName("page-title")
        layout.addWidget(self._title)

        layout.addWidget(_sep())

        self.status_label = QLabel("Waiting to start…")
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        layout.addWidget(QLabel("Live log:"))

        self.log_view = QTextEdit()
        self.log_view.setStyleSheet(_LOG_STYLE)
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Operations will appear here in real time…")
        layout.addWidget(self.log_view, 1)

        # ── resource bar ──────────────────────────────────────────────────────
        res_bar = QHBoxLayout()
        res_bar.setSpacing(16)

        self._temp_lbl = QLabel("🌡  CPU: —")
        self._temp_lbl.setStyleSheet(_RES_STYLE)
        res_bar.addWidget(self._temp_lbl)

        self._ram_lbl = QLabel("🧠  RAM: —")
        self._ram_lbl.setStyleSheet(_RES_STYLE)
        res_bar.addWidget(self._ram_lbl)

        self._disk_lbl = QLabel("💾  Disk: —")
        self._disk_lbl.setStyleSheet(_RES_STYLE)
        res_bar.addWidget(self._disk_lbl)

        res_bar.addStretch(1)
        layout.addLayout(res_bar)

    # ── public API ────────────────────────────────────────────────────────────

    def start_flash(self, runner) -> None:
        self._runner = runner
        self._reset_ui()
        runner.log_line.connect(self.append_log)
        runner.progress.connect(self._on_progress)
        runner.finished.connect(self._on_finished)
        runner.start()
        self._res_timer.start()
        self._update_resources()

    def append_log(self, line: str) -> None:
        self.log_view.append(line)

    def set_status(self, msg: str, pct: int | None = None) -> None:
        self.status_label.setText(msg)
        if pct is not None:
            self.progress.setValue(pct)

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_progress(self, pct: int, msg: str) -> None:
        self.progress.setValue(pct)
        if msg:
            self.status_label.setText(msg)
            self.append_log(msg)

    def _on_finished(self, success: bool, msg: str) -> None:
        self._res_timer.stop()
        self._runner = None
        if success:
            self._title.setText("Flash Complete")
            self._title.setStyleSheet(
                "color: #5cb85c; font-size: 22px; font-weight: bold; background: transparent;"
            )
            self.status_label.setText("Done : device written successfully.")
            self.progress.setValue(100)
        else:
            self._title.setText("Flash Failed")
            self._title.setStyleSheet(
                "color: #d9534f; font-size: 22px; font-weight: bold; background: transparent;"
            )
            self.status_label.setText(f"Failed: {msg}")
            self.append_log(f"\nFAIL: {msg}")
        self.flash_done.emit(success, msg)

    def _update_resources(self) -> None:
        self._temp_lbl.setText(f"🌡  CPU: {_read_cpu_temp()}")
        self._ram_lbl.setText(f"🧠  RAM: {_read_ram()}")
        self._disk_lbl.setText(f"💾  Disk: {_read_disk()}")

    def _reset_ui(self) -> None:
        is_dist        = self._state.mode == 'distribution'
        is_flash_image = self._state.flash_mode == 'flash_image'
        if is_dist and not is_flash_image:
            self._title.setText("Building Image…")
        elif is_flash_image:
            self._title.setText("Flashing Image…")
        else:
            self._title.setText("Flashing…")
        self._title.setStyleSheet("")
        self.log_view.clear()
        self.progress.setValue(0)
        self.status_label.setText("Starting…")


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

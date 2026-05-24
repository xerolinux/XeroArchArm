from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QPushButton, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPixmap


class _PanelWidget(QWidget):
    """Panel widget that paints its own background, bypassing Qt theme defaults."""
    _bg = QColor(16, 16, 18, 145)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        p.end()

from pathlib import Path

from core.state import AppState

_ASSETS = Path(__file__).resolve().parent.parent / 'assets'
from ui.workers.flash_runner import FlashRunner
from ui.pages.page_tarball   import TarballPage
from ui.pages.page_device    import DevicePage
from ui.pages.page_user      import UserPage
from ui.pages.page_wifi      import WifiPage
from ui.pages.page_packages  import PackagesPage
from ui.pages.page_confirm   import ConfirmPage
from ui.pages.page_flash     import FlashPage
from ui.pages.page_done      import DonePage


STEPS = [
    "Home",
    "Select Device",
    "User Account",
    "Network",
    "Packages",
    "Confirm",
    "Flash",
    "Done",
]

C_BG      = "rgba(36,  36,  40,  160)"
C_PANEL   = "rgba(16,  16,  18,  248)"
C_BORDER  = "rgba(62,  62,  72,  160)"
C_ACTIVE  = "rgba(32,  32,  36,  180)"
C_TEXT    = "#e8e8e8"
C_TEXT_S  = "#888890"
C_ACCENT  = "#5b9bd5"
C_GREEN   = "#5cb85c"
C_BTN     = "rgba(56,  56,  64,  200)"
C_BTN_HOV = "rgba(70,  70,  80,  220)"

STYLE = f"""
QMainWindow {{ background: transparent; }}
QWidget#root-widget {{ background: transparent; }}

QWidget#sidebar {{
    background: {C_PANEL};
    border-right: 1px solid {C_BORDER};
}}

QLabel#step-label {{
    color: {C_TEXT_S};
    font-size: 13px;
    padding: 10px 20px;
    border-left: 3px solid transparent;
    background: transparent;
}}
QLabel#step-label[active="true"] {{
    color: {C_TEXT};
    border-left: 3px solid {C_ACCENT};
    background: {C_ACTIVE};
}}
QLabel#step-label[done="true"] {{
    color: {C_GREEN};
    background: transparent;
}}

QLabel#app-title {{
    font-size: 16px; font-weight: bold;
    padding: 20px; color: {C_TEXT}; background: transparent;
}}
QLabel#app-subtitle {{
    color: {C_TEXT_S}; font-size: 11px;
    padding: 0 20px 20px 20px; background: transparent;
}}

QWidget#nav-bar {{
    background: {C_PANEL};
    border-top: 1px solid {C_BORDER};
}}
QStackedWidget#content-area {{ background: {C_BG}; }}

QPushButton#btn-next {{
    background: {C_ACCENT}; color: #ffffff;
    border: 1px solid #4a8ac4; padding: 8px 24px; font-size: 13px;
}}
QPushButton#btn-next:hover    {{ background: #6aaade; border-color: #6aaade; }}
QPushButton#btn-next:disabled {{ background: {C_BTN}; color: {C_TEXT_S}; border: 1px solid rgba(70,70,82,180); }}

QPushButton#btn-back {{
    background: {C_BTN}; color: {C_TEXT};
    border: 1px solid rgba(100, 100, 118, 220); padding: 8px 24px; font-size: 13px;
}}
QPushButton#btn-back:hover    {{ background: {C_BTN_HOV}; border-color: rgba(130,130,150,240); }}
QPushButton#btn-back:disabled {{ background: transparent; color: #505060; border: 1px solid rgba(62,62,72,120); }}

QPushButton#btn-cancel {{
    background: rgba(48, 48, 58, 160); color: #a0a0a8;
    border: 1px solid rgba(90, 90, 105, 180); padding: 8px 16px; font-size: 13px;
}}
QPushButton#btn-cancel:hover {{ color: #d9534f; border-color: #d9534f; background: rgba(50,28,28,180); }}
"""


class StepLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("step-label")
        self.setProperty("active", False)
        self.setProperty("done", False)
        self.setMinimumHeight(40)

    def set_active(self, v: bool) -> None:
        self.setProperty("active", v)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_done(self, v: bool) -> None:
        self.setProperty("done", v)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self, dist_enabled: bool = False):
        super().__init__()
        self.setWindowTitle("XeroPi4 : Arch ARM Pi Flasher")
        self.setMinimumSize(1100, 760)
        self.resize(1140, 820)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(STYLE)

        self._state = AppState()
        self._dist_enabled = dist_enabled
        self._current = 0
        self._step_labels: list[StepLabel] = []
        self._flash_done = False    # True once FlashRunner finishes (success or fail)
        self._runner: FlashRunner | None = None

        root = QWidget()
        root.setObjectName("root-widget")
        self.setCentralWidget(root)

        hl = QHBoxLayout(root)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(self._build_sidebar())

        right = QWidget()
        vl = QVBoxLayout(right)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setObjectName("content-area")

        s = self._state
        self._pages = [
            TarballPage(s, dist_enabled=self._dist_enabled),    # 0
            DevicePage(s),     # 1
            UserPage(s),       # 2
            WifiPage(s),       # 3
            PackagesPage(s),   # 4
            ConfirmPage(s),    # 5
            FlashPage(s),      # 6
            DonePage(s),       # 7
        ]
        for p in self._pages:
            self._stack.addWidget(p)

        self._pages[self._FLASH_IDX].flash_done.connect(self._on_flash_done)

        vl.addWidget(self._stack, 1)
        vl.addWidget(self._build_nav_bar())
        hl.addWidget(right, 1)

        self._update_ui()

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_blur)

    def _apply_blur(self) -> None:
        handle = self.windowHandle()
        if handle:
            from ui.blur_helper import enable_blur
            enable_blur(handle)

    # ── sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sidebar = _PanelWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        vl = QVBoxLayout(sidebar)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setStyleSheet("background: transparent; padding: 18px 0 6px 0;")
        px = QPixmap(str(_ASSETS / 'xero_logo.png'))
        if not px.isNull():
            logo_lbl.setPixmap(
                px.scaled(108, 108, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        vl.addWidget(logo_lbl)

        s = QLabel("Xero's Arch ARM Flasher")
        s.setObjectName("app-subtitle")
        s.setAlignment(Qt.AlignCenter)
        vl.addWidget(s)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"QFrame {{ color: {C_BORDER}; background: transparent; }}")
        vl.addWidget(sep)

        for i, name in enumerate(STEPS):
            if self._dist_enabled and i == self._USER_IDX:
                name = "Configuration"
            lbl = StepLabel(f"  {i+1}.  {name}")
            self._step_labels.append(lbl)
            vl.addWidget(lbl)

        vl.addStretch(1)
        return sidebar

    # ── nav bar ───────────────────────────────────────────────────────────────

    def _build_nav_bar(self) -> QWidget:
        bar = _PanelWidget()
        bar.setObjectName("nav-bar")
        bar.setFixedHeight(56)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(16, 0, 16, 0)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setObjectName("btn-cancel")
        self._btn_cancel.clicked.connect(self.close)

        self._btn_back = QPushButton("← Back")
        self._btn_back.setObjectName("btn-back")
        self._btn_back.clicked.connect(self._go_back)

        self._btn_next = QPushButton("Next →")
        self._btn_next.setObjectName("btn-next")
        self._btn_next.clicked.connect(self._go_next)

        hl.addWidget(self._btn_cancel)
        hl.addStretch(1)
        hl.addWidget(self._btn_back)
        hl.addSpacing(8)
        hl.addWidget(self._btn_next)
        return bar

    # ── navigation ────────────────────────────────────────────────────────────

    _DEVICE_IDX   = 1
    _USER_IDX     = 2
    _WIFI_IDX     = 3
    _PACKAGES_IDX = 4
    _CONFIRM_IDX  = 5
    _FLASH_IDX    = 6
    _DONE_IDX     = 7

    def _skipped_pages(self) -> set[int]:
        skipped: set[int] = set()
        is_flash_image = self._state.flash_mode == 'flash_image'
        if self._dist_enabled and not is_flash_image:
            skipped.add(self._DEVICE_IDX)
            skipped.add(self._WIFI_IDX)
        if is_flash_image:
            skipped.update({self._USER_IDX, self._WIFI_IDX, self._PACKAGES_IDX})
        return skipped

    def _go_next(self) -> None:
        page = self._pages[self._current]

        if hasattr(page, 'is_ready'):
            ok, msg = page.is_ready()
            if not ok:
                self._show_nav_error(msg)
                return

        if self._current < len(self._pages) - 1:
            nxt = self._current + 1
            skipped = self._skipped_pages()
            while nxt in skipped and nxt < len(self._pages) - 1:
                nxt += 1

            if nxt == self._CONFIRM_IDX:
                self._pages[self._CONFIRM_IDX].populate()

            self._current = nxt
            self._update_ui()

            if self._current == self._FLASH_IDX:
                self._flash_done = False
                self._runner = FlashRunner(self._state, parent=self)
                self._pages[self._FLASH_IDX].start_flash(self._runner)

    def _go_back(self) -> None:
        if self._current > 0:
            prv = self._current - 1
            skipped = self._skipped_pages()
            while prv in skipped and prv > 0:
                prv -= 1
            self._current = prv
            self._update_ui()

    def _on_flash_done(self, success: bool, msg: str) -> None:
        self._flash_done = True
        self._runner = None
        # Populate Done page, then reveal the Next button
        self._pages[self._DONE_IDX].set_result(success, msg)
        self._btn_next.setVisible(True)
        self._btn_next.setText("Next →")

    def _show_nav_error(self, msg: str) -> None:
        mb = QMessageBox(self)
        mb.setWindowTitle("Cannot proceed")
        mb.setText(msg)
        mb.setIcon(QMessageBox.Warning)
        mb.exec()

    def _update_ui(self) -> None:
        self._stack.setCurrentIndex(self._current)
        skipped = self._skipped_pages()

        for i, lbl in enumerate(self._step_labels):
            lbl.setVisible(i not in skipped)
            if i in skipped:
                continue
            lbl.set_active(i == self._current)
            lbl.set_done(i < self._current)

        self._btn_back.setEnabled(self._current > 0 and self._current != self._FLASH_IDX)

        is_last  = self._current == len(self._pages) - 1
        is_flash = self._current == self._FLASH_IDX
        # On Flash page: hide Next until flash_done; then it becomes visible via _on_flash_done
        self._btn_next.setVisible(not is_flash or self._flash_done)
        if is_last:
            self._btn_next.setText("Close")
            try:
                self._btn_next.clicked.disconnect()
            except RuntimeError:
                pass
            self._btn_next.clicked.connect(self.close)
        else:
            self._btn_next.setText("Next →")

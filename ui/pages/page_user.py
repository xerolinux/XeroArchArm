from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QTextEdit, QFrame, QGridLayout, QCheckBox, QStackedWidget,
)
from core.state import AppState
from ui.pages._page_base_style import BASE_STYLE

_SECTION = "color: #5b9bd5; font-size: 12px; font-weight: bold; padding-top: 12px;"
_NOTE    = "color: #888890; font-size: 11px; background: transparent;"
_DISTRIB_BANNER = (
    "Distribution mode: no credentials are baked into the image. "
    "Configure which prompts the first-boot setup wizard shows the end user."
)
_DISTRIB_BANNER_STYLE = (
    "color: #d4813a; font-size: 12px; "
    "background: rgba(45, 35, 20, 180); "
    "border: 1px solid rgba(212, 129, 58, 140); padding: 8px 12px;"
)


class UserPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self.setStyleSheet(BASE_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.setSpacing(10)

        self._title = QLabel("User Account")
        self._title.setObjectName("page-title")
        outer.addWidget(self._title)
        outer.addWidget(_sep())

        # Mode-switching stack
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_personal())    # 0
        self._stack.addWidget(self._build_distribution())  # 1
        outer.addWidget(self._stack)
        outer.addStretch(1)

    # ── Personal mode panel ───────────────────────────────────────────────────

    def _build_personal(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        desc = QLabel("Credentials are BAKED INTO the image.")
        desc.setStyleSheet(_NOTE)
        layout.addWidget(desc)

        sec1 = QLabel("USER")
        sec1.setStyleSheet(_SECTION)
        layout.addWidget(sec1)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("Username:"), 0, 0)
        self._username = QLineEdit()
        self._username.setPlaceholderText("e.g. pi")
        self._username.textChanged.connect(self._on_username_changed)
        grid.addWidget(self._username, 0, 1)

        grid.addWidget(QLabel("Password:"), 1, 0)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("leave blank to skip")
        self._password.textChanged.connect(self._on_password_changed)
        grid.addWidget(self._password, 1, 1)

        layout.addLayout(grid)

        self._root_same_pw = QCheckBox("Use same password for root account")
        self._root_same_pw.setEnabled(False)
        self._root_same_pw.toggled.connect(lambda v: setattr(self._state, 'root_same_password', v))
        layout.addWidget(self._root_same_pw)

        self._wheel_check = QCheckBox("Add user to wheel group (sudo)")
        self._wheel_check.setEnabled(False)
        self._wheel_check.toggled.connect(lambda v: setattr(self._state, 'wheel', v))
        layout.addWidget(self._wheel_check)

        sec2 = QLabel("NETWORK")
        sec2.setStyleSheet(_SECTION)
        layout.addWidget(sec2)

        grid2 = QGridLayout()
        grid2.setColumnStretch(1, 1)
        grid2.setHorizontalSpacing(12)
        grid2.addWidget(QLabel("Hostname:"), 0, 0)
        self._hostname = QLineEdit()
        self._hostname.setPlaceholderText("e.g. archpi")
        self._hostname.textChanged.connect(lambda t: setattr(self._state, 'hostname', t))
        grid2.addWidget(self._hostname, 0, 1)
        layout.addLayout(grid2)

        sec3 = QLabel("SSH")
        sec3.setStyleSheet(_SECTION)
        layout.addWidget(sec3)

        layout.addWidget(QLabel("Authorized public key:"))
        self._ssh_key = QTextEdit()
        self._ssh_key.setPlaceholderText("Paste SSH public key here…")
        self._ssh_key.setFixedHeight(72)
        self._ssh_key.textChanged.connect(
            lambda: setattr(self._state, 'ssh_key', self._ssh_key.toPlainText())
        )
        layout.addWidget(self._ssh_key)

        layout.addStretch(1)
        return w

    # ── Distribution mode panel (Configuration) ───────────────────────────────

    def _build_distribution(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        banner = QLabel(_DISTRIB_BANNER)
        banner.setStyleSheet(_DISTRIB_BANNER_STYLE)
        banner.setWordWrap(True)
        layout.addWidget(banner)

        # ── USER ACCOUNT section ──────────────────────────────────────────────
        sec_user = QLabel("USER ACCOUNT")
        sec_user.setStyleSheet(_SECTION)
        layout.addWidget(sec_user)

        note = QLabel(
            "Tick the prompts you want the end user to see during first-boot setup. "
            "No credentials from this screen are stored in the image."
        )
        note.setStyleSheet(_NOTE)
        note.setWordWrap(True)
        layout.addWidget(note)

        self._d_ask_user = QCheckBox("Prompt: create a new user account")
        self._d_ask_user.setChecked(self._state.dist_ask_user)
        self._d_ask_user.toggled.connect(self._on_dist_ask_user)
        layout.addWidget(self._d_ask_user)

        self._d_ask_wheel = QCheckBox("Prompt: offer wheel/sudo group membership")
        self._d_ask_wheel.setChecked(self._state.dist_ask_wheel)
        self._d_ask_wheel.toggled.connect(lambda v: setattr(self._state, 'dist_ask_wheel', v))
        layout.addWidget(self._d_ask_wheel)

        self._d_ask_hostname = QCheckBox("Prompt: set a custom hostname")
        self._d_ask_hostname.setChecked(self._state.dist_ask_hostname)
        self._d_ask_hostname.toggled.connect(lambda v: setattr(self._state, 'dist_ask_hostname', v))
        layout.addWidget(self._d_ask_hostname)

        self._d_ask_ssh = QCheckBox("Prompt: add an SSH authorized key")
        self._d_ask_ssh.setChecked(self._state.dist_ask_ssh_key)
        self._d_ask_ssh.toggled.connect(lambda v: setattr(self._state, 'dist_ask_ssh_key', v))
        layout.addWidget(self._d_ask_ssh)

        layout.addWidget(_sep())

        # ── WIFI & NETWORK section ────────────────────────────────────────────
        sec_wifi = QLabel("WIFI & NETWORK")
        sec_wifi.setStyleSheet(_SECTION)
        layout.addWidget(sec_wifi)

        wifi_banner = QLabel(
            "No WiFi credentials are baked into the image. "
            "Toggle whether the first-boot wizard asks the end user for WiFi details."
        )
        wifi_banner.setStyleSheet(_DISTRIB_BANNER_STYLE)
        wifi_banner.setWordWrap(True)
        layout.addWidget(wifi_banner)

        self._d_ask_wifi = QCheckBox("Show WiFi setup prompt during first-boot setup wizard")
        self._d_ask_wifi.setChecked(self._state.dist_ask_wifi)
        self._d_ask_wifi.toggled.connect(lambda v: setattr(self._state, 'dist_ask_wifi', v))
        layout.addWidget(self._d_ask_wifi)

        wifi_note = QLabel(
            "If unticked, the end user will need Ethernet on first boot. "
            "WiFi can still be configured manually afterwards."
        )
        wifi_note.setStyleSheet(_NOTE)
        wifi_note.setWordWrap(True)
        layout.addWidget(wifi_note)

        self._d_ask_static = QCheckBox("Show static IP configuration prompt during first-boot setup wizard")
        self._d_ask_static.setChecked(self._state.use_static_ip)
        self._d_ask_static.toggled.connect(lambda v: setattr(self._state, 'use_static_ip', v))
        layout.addWidget(self._d_ask_static)

        static_note = QLabel(
            "If enabled, the first-boot wizard offers static IP setup. The end user can accept or skip."
        )
        static_note.setStyleSheet(_NOTE)
        static_note.setWordWrap(True)
        layout.addWidget(static_note)

        layout.addStretch(1)
        return w

    def _on_dist_ask_user(self, v: bool) -> None:
        self._state.dist_ask_user = v
        self._d_ask_wheel.setEnabled(v)
        self._d_ask_ssh.setEnabled(v)
        if not v:
            self._d_ask_wheel.setChecked(False)
            self._d_ask_ssh.setChecked(False)

    # ── show-event refresh ────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        is_dist = self._state.mode == 'distribution'
        self._stack.setCurrentIndex(1 if is_dist else 0)
        self._title.setText("Configuration" if is_dist else "User Account")

    def _on_username_changed(self, text: str) -> None:
        self._state.username = text
        self._wheel_check.setEnabled(bool(text))
        if not text:
            self._wheel_check.setChecked(False)
            self._state.wheel = False

    def _on_password_changed(self, text: str) -> None:
        self._state.password = text
        self._root_same_pw.setEnabled(bool(text))
        if not text:
            self._root_same_pw.setChecked(False)
            self._state.root_same_password = False


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

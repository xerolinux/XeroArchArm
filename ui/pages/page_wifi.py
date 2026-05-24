from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QFrame, QGridLayout, QCheckBox, QStackedWidget, QSpinBox,
)
from core.state import AppState
from ui.pages._page_base_style import BASE_STYLE, WARNING_BOX

_SECTION = "color: #5b9bd5; font-size: 12px; font-weight: bold; padding-top: 12px;"
_NOTE    = "color: #888890; font-size: 11px; background: transparent;"

_PERSONAL_WARN = (
    "⚠  The WiFi password is stored in PLAINTEXT inside this image. "
    "Do NOT share or distribute a Personal-mode image after configuring WiFi."
)
_DISTRIB_BANNER = (
    "Distribution mode: no WiFi credentials are baked into the image. "
    "Toggle whether the first-boot setup wizard asks the end user for WiFi details."
)
_DISTRIB_BANNER_STYLE = (
    "color: #d4813a; font-size: 12px; "
    "background: rgba(45, 35, 20, 180); "
    "border: 1px solid rgba(212, 129, 58, 140); padding: 8px 12px;"
)


class WifiPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self.setStyleSheet(BASE_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 36)
        outer.setSpacing(10)

        self._title = QLabel("Network")
        self._title.setObjectName("page-title")
        outer.addWidget(self._title)
        outer.addWidget(_sep())

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_personal())       # 0
        self._stack.addWidget(self._build_distribution())   # 1
        outer.addWidget(self._stack)
        outer.addStretch(1)

    # ── Personal panel ────────────────────────────────────────────────────────

    def _build_personal(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        desc = QLabel(
            "Leave blank to skip : use Ethernet on first boot.\n"
            "If filled, a NetworkManager profile (mode 600) is written into the image."
        )
        desc.setObjectName("page-desc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._pw_warning = QLabel(_PERSONAL_WARN)
        self._pw_warning.setStyleSheet(WARNING_BOX)
        self._pw_warning.setWordWrap(True)
        self._pw_warning.setVisible(False)
        layout.addWidget(self._pw_warning)

        sec = QLabel("NETWORK")
        sec.setStyleSheet(_SECTION)
        layout.addWidget(sec)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("SSID:"), 0, 0)
        self._ssid = QLineEdit()
        self._ssid.setPlaceholderText("Network name")
        self._ssid.textChanged.connect(self._on_ssid_changed)
        grid.addWidget(self._ssid, 0, 1)

        grid.addWidget(QLabel("Password:"), 1, 0)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("WPA2 passphrase")
        self._password.textChanged.connect(lambda t: setattr(self._state, 'wifi_password', t))
        grid.addWidget(self._password, 1, 1)

        grid.addWidget(QLabel("Country code:"), 2, 0)
        self._country = QLineEdit()
        self._country.setText(self._state.wifi_country)
        self._country.setMaxLength(2)
        self._country.setPlaceholderText("e.g. US")
        self._country.textChanged.connect(self._on_country_changed)
        grid.addWidget(self._country, 2, 1)

        layout.addLayout(grid)

        hint = QLabel("Country code required for Pi WiFi radio (ISO 3166-1 alpha-2, e.g. US GB DE).")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        # ── WiFi Static IP ────────────────────────────────────────────────────
        self._static_check = QCheckBox("Use static IP for WiFi")
        self._static_check.setChecked(self._state.use_static_ip)
        self._static_check.toggled.connect(self._on_static_toggled)
        layout.addWidget(self._static_check)

        self._static_box = QWidget()
        self._static_box.setStyleSheet("QWidget { background: transparent; }")
        sb = QGridLayout(self._static_box)
        sb.setContentsMargins(16, 4, 0, 0)
        sb.setHorizontalSpacing(12)
        sb.setVerticalSpacing(6)
        sb.setColumnStretch(1, 1)

        sb.addWidget(QLabel("IP address:"), 0, 0)
        self._sip = QLineEdit()
        self._sip.setPlaceholderText("e.g. 192.168.1.100")
        self._sip.setText(self._state.static_ip)
        self._sip.textChanged.connect(lambda t: setattr(self._state, 'static_ip', t.strip()))
        sb.addWidget(self._sip, 0, 1)

        sb.addWidget(QLabel("Prefix length:"), 1, 0)
        self._sprefix = QSpinBox()
        self._sprefix.setRange(1, 32)
        self._sprefix.setValue(self._state.static_prefix)
        self._sprefix.valueChanged.connect(lambda v: setattr(self._state, 'static_prefix', v))
        sb.addWidget(self._sprefix, 1, 1)

        sb.addWidget(QLabel("Gateway:"), 2, 0)
        self._sgw = QLineEdit()
        self._sgw.setPlaceholderText("e.g. 192.168.1.1")
        self._sgw.setText(self._state.static_gateway)
        self._sgw.textChanged.connect(lambda t: setattr(self._state, 'static_gateway', t.strip()))
        sb.addWidget(self._sgw, 2, 1)

        sb.addWidget(QLabel("DNS:"), 3, 0)
        self._sdns = QLineEdit()
        self._sdns.setPlaceholderText("e.g. 1.1.1.1")
        self._sdns.setText(self._state.static_dns)
        self._sdns.textChanged.connect(lambda t: setattr(self._state, 'static_dns', t.strip()))
        sb.addWidget(self._sdns, 3, 1)

        self._static_box.setVisible(self._state.use_static_ip)
        layout.addWidget(self._static_box)

        # ── Ethernet Static IP ────────────────────────────────────────────────
        sec_eth = QLabel("ETHERNET")
        sec_eth.setStyleSheet(_SECTION)
        layout.addWidget(sec_eth)

        self._eth_static_check = QCheckBox("Use static IP for Ethernet")
        self._eth_static_check.setChecked(self._state.use_eth_static_ip)
        self._eth_static_check.toggled.connect(self._on_eth_static_toggled)
        layout.addWidget(self._eth_static_check)

        self._eth_static_box = QWidget()
        self._eth_static_box.setStyleSheet("QWidget { background: transparent; }")
        esb = QGridLayout(self._eth_static_box)
        esb.setContentsMargins(16, 4, 0, 0)
        esb.setHorizontalSpacing(12)
        esb.setVerticalSpacing(6)
        esb.setColumnStretch(1, 1)

        esb.addWidget(QLabel("IP address:"), 0, 0)
        self._eth_sip = QLineEdit()
        self._eth_sip.setPlaceholderText("e.g. 192.168.1.100")
        self._eth_sip.setText(self._state.eth_static_ip)
        self._eth_sip.textChanged.connect(lambda t: setattr(self._state, 'eth_static_ip', t.strip()))
        esb.addWidget(self._eth_sip, 0, 1)

        esb.addWidget(QLabel("Prefix length:"), 1, 0)
        self._eth_sprefix = QSpinBox()
        self._eth_sprefix.setRange(1, 32)
        self._eth_sprefix.setValue(self._state.eth_static_prefix)
        self._eth_sprefix.valueChanged.connect(lambda v: setattr(self._state, 'eth_static_prefix', v))
        esb.addWidget(self._eth_sprefix, 1, 1)

        esb.addWidget(QLabel("Gateway:"), 2, 0)
        self._eth_sgw = QLineEdit()
        self._eth_sgw.setPlaceholderText("e.g. 192.168.1.1")
        self._eth_sgw.setText(self._state.eth_static_gateway)
        self._eth_sgw.textChanged.connect(lambda t: setattr(self._state, 'eth_static_gateway', t.strip()))
        esb.addWidget(self._eth_sgw, 2, 1)

        esb.addWidget(QLabel("DNS:"), 3, 0)
        self._eth_sdns = QLineEdit()
        self._eth_sdns.setPlaceholderText("e.g. 1.1.1.1")
        self._eth_sdns.setText(self._state.eth_static_dns)
        self._eth_sdns.textChanged.connect(lambda t: setattr(self._state, 'eth_static_dns', t.strip()))
        esb.addWidget(self._eth_sdns, 3, 1)

        self._eth_static_box.setVisible(self._state.use_eth_static_ip)
        layout.addWidget(self._eth_static_box)

        layout.addStretch(1)
        return w

    # ── Distribution panel ────────────────────────────────────────────────────

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

        sec = QLabel("FIRST-BOOT WIZARD")
        sec.setStyleSheet(_SECTION)
        layout.addWidget(sec)

        self._d_ask_wifi = QCheckBox(
            "Show WiFi setup prompt during first-boot setup wizard"
        )
        self._d_ask_wifi.setChecked(self._state.dist_ask_wifi)
        self._d_ask_wifi.toggled.connect(lambda v: setattr(self._state, 'dist_ask_wifi', v))
        layout.addWidget(self._d_ask_wifi)

        wifi_note = QLabel(
            "If unticked, the end user will need Ethernet on first boot. "
            "WiFi can still be configured manually after the system is running."
        )
        wifi_note.setStyleSheet(_NOTE)
        wifi_note.setWordWrap(True)
        layout.addWidget(wifi_note)

        self._d_ask_static = QCheckBox(
            "Show static IP configuration prompt during first-boot setup wizard"
        )
        self._d_ask_static.setChecked(self._state.use_static_ip)
        self._d_ask_static.toggled.connect(lambda v: setattr(self._state, 'use_static_ip', v))
        layout.addWidget(self._d_ask_static)

        static_note = QLabel(
            "If enabled, the first-boot wizard offers static IP setup. "
            "The end user can accept or skip it."
        )
        static_note.setStyleSheet(_NOTE)
        static_note.setWordWrap(True)
        layout.addWidget(static_note)

        layout.addStretch(1)
        return w

    # ── show-event refresh ────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        is_dist = self._state.mode == 'distribution'
        self._stack.setCurrentIndex(1 if is_dist else 0)
        self._title.setText(
            "Network  (First-boot config)" if is_dist
            else "Network  (Optional)"
        )

    def _on_static_toggled(self, checked: bool) -> None:
        self._state.use_static_ip = checked
        self._static_box.setVisible(checked)

    def _on_eth_static_toggled(self, checked: bool) -> None:
        self._state.use_eth_static_ip = checked
        self._eth_static_box.setVisible(checked)

    def _on_ssid_changed(self, text: str) -> None:
        self._state.wifi_ssid = text
        self._pw_warning.setVisible(bool(text))

    def _on_country_changed(self, text: str) -> None:
        upper = text.upper()
        self._state.wifi_country = upper
        self._country.blockSignals(True)
        self._country.setText(upper)
        self._country.blockSignals(False)


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

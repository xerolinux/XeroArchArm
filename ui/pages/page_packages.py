from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QFrame, QCheckBox, QScrollArea,
)
from core.state import AppState
from ui.pages._page_base_style import BASE_STYLE

_BANNER_STYLE = (
    "color: #f0ad4e; font-size: 11px; font-weight: bold; "
    "background: rgba(45, 42, 30, 180); "
    "border: 1px solid rgba(240, 173, 78, 140); padding: 6px 12px;"
)
_HOW_IT_WORKS_STYLE = (
    "color: #9ab8d4; font-size: 11px; "
    "background: rgba(20, 26, 36, 180); "
    "border: 1px solid rgba(91, 155, 213, 70); "
    "border-left: 3px solid #5b9bd5; "
    "padding: 7px 12px;"
)
_DISTRIB_NOTE_STYLE = (
    "color: #d4813a; font-size: 11px; "
    "background: rgba(45, 35, 20, 180); "
    "border: 1px solid rgba(212, 129, 58, 140); padding: 6px 12px;"
)
_SECTION = (
    "color: #5b9bd5; font-size: 11px; font-weight: bold; letter-spacing: 1px; "
    "padding-top: 8px; padding-bottom: 2px; background: transparent;"
)
_LOCKED_STYLE = (
    "QCheckBox { color: #888890; }"
    "QCheckBox::indicator { border: 1px solid #444450; background: rgba(91,155,213,60); }"
    "QCheckBox::indicator:checked { background: rgba(91,155,213,90); border: 1px solid #5b9bd5; }"
)

# ── Forced (always installed, not user-removable) ─────────────────────────────

_PI4_PLATFORM: list[tuple[str, str]] = [
    ("raspberrypi-bootloader", "VideoCore GPU firmware files in /boot"),
    ("wireless-regdb",         "WiFi regulatory domain — required for wifi_country"),
]

_CORE: list[tuple[str, str]] = [
    ("openssh",        "SSH server"),
    ("networkmanager", "NetworkManager — WiFi and Ethernet"),
    ("git",            "Git version control"),
    ("nano",           "Nano text editor"),
    ("htop",           "Interactive process monitor"),
    ("rsync",          "File sync and transfer"),
    ("wget",           "HTTP downloader"),
    ("curl",           "HTTP client library"),
    ("docker",         "Docker container runtime"),
    ("docker-compose", "Docker Compose — multi-container apps"),
    ("fail2ban",       "SSH bruteforce protection"),
    ("base-devel",     "Build tools — gcc, make, pkg-config"),
    ("sudo",           "Sudo privilege escalation"),
]

# ── Optional packages grouped by category ─────────────────────────────────────
# (category, package, description, checked-by-default)

_OPTIONAL: list[tuple[str, str, str, bool]] = [
    # Shell & Editors
    ("Shell & Editors", "vim",    "Vim text editor",                          False),
    ("Shell & Editors", "zsh",    "Z shell",                                  False),
    ("Shell & Editors", "tmux",   "Terminal multiplexer",                     False),
    ("Shell & Editors", "screen", "Screen terminal session manager",          False),

    # Monitoring
    ("Monitoring", "btop",          "Resource monitor — CPU, RAM, disk, net", False),
    ("Monitoring", "glances",       "All-in-one resource monitor (TUI)",      False),
    ("Monitoring", "ncdu",          "Disk usage analyser (TUI)",              False),
    ("Monitoring", "iotop",         "Disk I/O monitor per process",           False),
    ("Monitoring", "nethogs",       "Network bandwidth per process",          False),
    ("Monitoring", "lsof",          "List open files and ports",              False),
    ("Monitoring", "strace",        "System call tracer",                     False),
    ("Monitoring", "smartmontools", "Disk S.M.A.R.T. health monitor",         False),
    ("Monitoring", "lm_sensors",    "Hardware temperature sensors",           False),

    # Network Tools
    ("Network Tools", "nmap",       "Network scanner",                        False),
    ("Network Tools", "iperf3",     "Network bandwidth tester",               False),
    ("Network Tools", "mtr",        "Traceroute and ping combined",           False),
    ("Network Tools", "tcpdump",    "Packet capture",                         False),
    ("Network Tools", "bind-tools", "DNS tools — dig, nslookup",             False),
    ("Network Tools", "nload",      "Real-time network bandwidth display",    False),
    ("Network Tools", "net-tools",  "Classic tools — ifconfig, netstat",      False),

    # VPN & Tunneling
    ("VPN & Tunneling", "tailscale",       "Tailscale mesh VPN",              False),
    ("VPN & Tunneling", "wireguard-tools", "WireGuard VPN tools",             False),
    ("VPN & Tunneling", "openvpn",         "OpenVPN client and server",       False),

    # File Sharing
    ("File Sharing", "samba",     "SMB/CIFS sharing — Windows compatible",   False),
    ("File Sharing", "nfs-utils", "NFS server and client",                   False),
    ("File Sharing", "rclone",    "Cloud storage sync — S3, GDrive, B2",     False),

    # Security
    ("Security", "ufw",      "Uncomplicated Firewall",                        False),
    ("Security", "lynis",    "Security audit and hardening scanner",          False),
    ("Security", "rkhunter", "Rootkit hunter",                                False),
    ("Security", "aide",     "File integrity and intrusion detection",        False),
    ("Security", "nftables", "Modern nftables firewall framework",            False),

    # Containers
    ("Containers", "podman",  "Daemonless OCI container runtime",             False),
    ("Containers", "buildah", "OCI container image builder",                  False),

    # Web & Proxy
    ("Web & Proxy", "nginx",   "Nginx web server and reverse proxy",          False),
    ("Web & Proxy", "caddy",   "Caddy web server with automatic TLS",         False),
    ("Web & Proxy", "haproxy", "HAProxy TCP/HTTP load balancer",              False),

    # Databases
    ("Databases", "mariadb",    "MariaDB — MySQL-compatible database",        False),
    ("Databases", "postgresql", "PostgreSQL relational database",             False),
    ("Databases", "redis",      "Redis in-memory data store and cache",       False),
    ("Databases", "sqlite",     "SQLite lightweight embedded database",       False),

    # Homelab
    ("Homelab", "mosquitto",     "MQTT message broker",                       False),
    ("Homelab", "grafana",       "Metrics and log dashboard",                 False),
    ("Homelab", "prometheus",    "Metrics collection and alerting",           False),
    ("Homelab", "node_exporter", "Prometheus system metrics exporter",        False),
    ("Homelab", "avahi",         "mDNS / Bonjour network discovery",         False),
    ("Homelab", "cronie",        "Cron daemon",                               False),

    # Utilities
    ("Utilities", "fastfetch", "System info display",                         False),
    ("Utilities", "fzf",       "Fuzzy finder",                               False),
    ("Utilities", "bat",       "Cat with syntax highlighting",                False),
    ("Utilities", "ripgrep",   "Fast grep replacement (rg)",                  False),
    ("Utilities", "fd",        "Fast find replacement",                       False),
    ("Utilities", "jq",        "JSON processor and formatter",                False),
    ("Utilities", "p7zip",     "7-Zip archive tool",                          False),
    ("Utilities", "mc",        "Midnight Commander file manager (TUI)",       False),
    ("Utilities", "ranger",    "Ranger file manager (TUI)",                   False),
]


class PackagesPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._optional_checks: list[tuple[str, QCheckBox]] = []
        self.setStyleSheet(BASE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 28, 40, 28)
        layout.setSpacing(8)

        title = QLabel("Packages")
        title.setObjectName("page-title")
        layout.addWidget(title)
        layout.addWidget(_sep())

        banner = QLabel(
            "Headless server image — packages install on first boot via pacman."
        )
        banner.setStyleSheet(_BANNER_STYLE)
        layout.addWidget(banner)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: rgba(18,18,22,160); "
            "border: 1px solid rgba(62,62,72,120); }"
        )

        check_widget = QWidget()
        check_widget.setStyleSheet("QWidget { background: transparent; }")
        check_layout = QVBoxLayout(check_widget)
        check_layout.setContentsMargins(10, 8, 10, 8)
        check_layout.setSpacing(2)

        # Pi 4 platform (locked)
        check_layout.addWidget(_sec_label("PI 4 PLATFORM  —  forced, not removable"))
        for pkg, desc in _PI4_PLATFORM:
            check_layout.addWidget(_locked_cb(pkg, desc))

        # Server core (locked)
        check_layout.addWidget(_sec_label("SERVER CORE  —  always installed"))
        for pkg, desc in _CORE:
            check_layout.addWidget(_locked_cb(pkg, desc))

        # Optional grouped by category
        current_cat = None
        for cat, pkg, desc, default in _OPTIONAL:
            if cat != current_cat:
                current_cat = cat
                check_layout.addWidget(_sec_label(cat.upper()))
            cb = QCheckBox(f"  {pkg}  ·  {desc}")
            cb.setChecked(default)
            cb.toggled.connect(lambda _v: self._sync_packages())
            self._optional_checks.append((pkg, cb))
            check_layout.addWidget(cb)

        check_layout.addStretch(1)
        scroll.setWidget(check_widget)
        layout.addWidget(scroll, 1)

        note = QLabel(
            "Packages install on first boot via pacman -Sy (Pi needs internet). "
            "The service self-removes after completion. "
            "If offline on first boot, install manually with pacman later."
        )
        note.setStyleSheet(_HOW_IT_WORKS_STYLE)
        note.setWordWrap(True)
        layout.addWidget(note)

        self._dist_note = QLabel(
            "Distribution mode: this list is a DEFAULT — the end user can accept, modify, or skip it."
        )
        self._dist_note.setStyleSheet(_DISTRIB_NOTE_STYLE)
        self._dist_note.setWordWrap(True)
        self._dist_note.setVisible(False)
        layout.addWidget(self._dist_note)

        self._sync_packages()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._dist_note.setVisible(self._state.mode == 'distribution')

    def _sync_packages(self) -> None:
        core     = [pkg for pkg, _ in _CORE]
        optional = [pkg for pkg, cb in self._optional_checks if cb.isChecked()]
        self._state.packages = core + optional


def _sec_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_SECTION)
    return lbl


def _locked_cb(pkg: str, desc: str) -> QCheckBox:
    cb = QCheckBox(f"  {pkg}  ·  {desc}")
    cb.setChecked(True)
    cb.setEnabled(False)
    cb.setStyleSheet(_LOCKED_STYLE)
    return cb


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

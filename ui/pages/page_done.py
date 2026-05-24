from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QTextEdit, QPushButton, QHBoxLayout, QApplication,
)
from core.state import AppState
from ui.pages._page_base_style import BASE_STYLE, EJECT_BOX

_USB_BOOT_NOTE = (
    "USB boot note: Booting a Raspberry Pi 4/400 from a USB SSD or drive requires "
    "the Pi's bootloader/firmware to support USB boot. Modern Pi 4/400 units ship "
    "with suitable firmware; older units may need a bootloader update and "
    "boot-order change first (run raspi-config or rpi-eeprom-update on an "
    "existing SD-card install, or see the official Raspberry Pi documentation)."
)
_FIRSTBOOT_NOTE_PERSONAL = (
    "ℹ  First boot takes longer: SSH host keys regenerate and packages install via pacman. Pi needs internet."
)
_FIRSTBOOT_NOTE_DISTRIB = (
    "ℹ  First boot takes longer: SSH host keys regenerate, interactive setup wizard runs, "
    "then packages install via pacman. Pi needs internet."
)

_INFO_STYLE = "color: #888890; font-size: 12px; background: transparent;"
_USB_STYLE  = (
    "color: #5b9bd5; font-size: 12px; "
    "background: rgba(20, 30, 45, 180); "
    "border: 1px solid rgba(91, 155, 213, 120); padding: 10px 14px;"
)
_CHECKLIST_STYLE = (
    "font-family: monospace; font-size: 12px; "
    "background: rgba(16, 16, 18, 200); color: #c0c0c8; "
    "border: 1px solid rgba(62, 62, 72, 160); padding: 10px;"
)
_SECTION = "color: #5b9bd5; font-size: 12px; font-weight: bold; background: transparent;"


class DonePage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self.setStyleSheet(BASE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(10)

        self._title = QLabel("Flash Complete")
        self._title.setStyleSheet("color: #5cb85c; font-size: 22px; font-weight: bold; background: transparent;")
        layout.addWidget(self._title)

        layout.addWidget(_sep())

        self._summary = QLabel("The image was written successfully.")
        self._summary.setStyleSheet("color: #e8e8e8; font-size: 13px; background: transparent;")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        self._eject = QLabel(
            "⏏  Safe to remove: the device has been synced and unmounted.\n"
            "Remove it before powering up the Raspberry Pi."
        )
        self._eject.setStyleSheet(EJECT_BOX)
        self._eject.setWordWrap(True)
        layout.addWidget(self._eject)

        self._firstboot_label = QLabel(_FIRSTBOOT_NOTE_PERSONAL)
        self._firstboot_label.setStyleSheet(_INFO_STYLE)
        self._firstboot_label.setWordWrap(True)
        layout.addWidget(self._firstboot_label)

        self._usb_label = QLabel(_USB_BOOT_NOTE)
        self._usb_label.setStyleSheet(_USB_STYLE)
        self._usb_label.setWordWrap(True)
        self._usb_label.setVisible(False)
        layout.addWidget(self._usb_label)

        # ── post-flash checklist (personal mode, success only) ────────────────
        self._checklist_section = QWidget()
        self._checklist_section.setStyleSheet("QWidget { background: transparent; }")
        cl_layout = QVBoxLayout(self._checklist_section)
        cl_layout.setContentsMargins(0, 6, 0, 0)
        cl_layout.setSpacing(8)

        cl_title = QLabel("WHAT'S NEXT")
        cl_title.setStyleSheet(_SECTION)
        cl_layout.addWidget(cl_title)

        self._checklist = QTextEdit()
        self._checklist.setReadOnly(True)
        self._checklist.setStyleSheet(_CHECKLIST_STYLE)
        self._checklist.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        cl_layout.addWidget(self._checklist, 1)

        copy_row = QHBoxLayout()
        copy_btn = QPushButton("Copy all commands")
        copy_btn.clicked.connect(self._copy_checklist)
        copy_row.addWidget(copy_btn)
        copy_row.addStretch(1)
        cl_layout.addLayout(copy_row)

        self._checklist_section.setVisible(False)
        layout.addWidget(self._checklist_section, 1)

    # ── public API ────────────────────────────────────────────────────────────

    def set_result(self, success: bool, message: str = '') -> None:
        is_dist = self._state.mode == 'distribution'

        if is_dist and success:
            self._title.setText("Image Built")
            self._title.setStyleSheet(
                "color: #5cb85c; font-size: 22px; font-weight: bold; background: transparent;"
            )
            out = self._state.shrink_output_path
            if out and not out.endswith('.img.xz'):
                out += '.img.xz'
            self._summary.setText(
                f"Distribution image saved to:\n{out}" if out
                else "Distribution image built successfully."
            )
            self._eject.setVisible(False)
        elif is_dist and not success:
            self._title.setText("Build Failed")
            self._title.setStyleSheet(
                "color: #d9534f; font-size: 22px; font-weight: bold; background: transparent;"
            )
            self._summary.setText(f"Image build did not complete.\n{message}")
            self._eject.setVisible(False)
        elif success:
            self._title.setText("Flash Complete")
            self._title.setStyleSheet(
                "color: #5cb85c; font-size: 22px; font-weight: bold; background: transparent;"
            )
            self._summary.setText(
                "The image was written successfully." + (f"\n{message}" if message else "")
            )
            self._eject.setVisible(True)
        else:
            self._title.setText("Flash Failed")
            self._title.setStyleSheet(
                "color: #d9534f; font-size: 22px; font-weight: bold; background: transparent;"
            )
            self._summary.setText(f"Flash did not complete successfully.\n{message}")
            self._eject.setVisible(False)

        is_flash_image = not is_dist and self._state.flash_mode == 'flash_image'

        d = self._state.target_device
        self._usb_label.setVisible(bool(d and d.bus_type == 'USB disk' and success and not is_dist))

        self._firstboot_label.setVisible(not is_flash_image)
        if not is_flash_image:
            note = (_FIRSTBOOT_NOTE_DISTRIB if is_dist else _FIRSTBOOT_NOTE_PERSONAL)
            self._firstboot_label.setText(note)

        show_checklist = success and not is_dist and not is_flash_image
        self._checklist_section.setVisible(show_checklist)
        if show_checklist:
            self._checklist.setPlainText(self._build_checklist())

    # ── checklist builder ─────────────────────────────────────────────────────

    def _build_checklist(self) -> str:
        s = self._state
        user  = s.username or 'alarm'
        host  = s.hostname or 'alarmpi'
        ip    = s.static_ip if s.use_static_ip else f'{host}.local'
        pkgs  = s.packages + ([p for p in s.extra_packages.split() if p])

        lines = []

        lines += [
            "─" * 56,
            " 1.  INSERT SD/USB CARD AND POWER ON THE PI",
            "─" * 56,
            "",
            " Wait ~2 min for first boot to complete.",
            " Packages install automatically once online.",
            "",
            "─" * 56,
            " 2.  SSH INTO YOUR PI",
            "─" * 56,
            "",
        ]
        if s.use_static_ip:
            lines += [
                f"  ssh {user}@{ip}",
                f"  # or by hostname (if avahi is enabled):",
                f"  ssh {user}@{host}.local",
            ]
        else:
            lines += [
                f"  ssh {user}@{host}.local",
                f"  # if mDNS fails, scan for IP:",
                f"  nmap -sn 192.168.1.0/24 | grep -A2 Raspberry",
            ]

        lines += [
            "",
            "─" * 56,
            " 3.  VERIFY SERVICES",
            "─" * 56,
            "",
            "  systemctl status sshd NetworkManager",
            "  systemctl status xeropi-firstboot   # package install log",
            "",
        ]

        if 'docker' in pkgs or 'docker-compose' in pkgs:
            lines += [
                "─" * 56,
                " 4.  VERIFY DOCKER",
                "─" * 56,
                "",
                "  docker run --rm hello-world",
                "  docker ps",
                "  docker compose version",
                "",
            ]

        lines += [
            "─" * 56,
            " 5.  UPDATE THE SYSTEM",
            "─" * 56,
            "",
            "  sudo pacman -Syu",
            "",
            "─" * 56,
            " 6.  CHANGE ROOT PASSWORD  (if not already done)",
            "─" * 56,
            "",
            "  sudo passwd root",
            "",
            "─" * 56,
            " RESOURCES",
            "─" * 56,
            "",
            "  XeroLinux  :  https://xerolinux.xyz",
            "  Arch ARM   :  https://archlinuxarm.org",
            "  Pi docs    :  https://www.raspberrypi.com/documentation",
            "",
        ]

        return '\n'.join(lines)

    def _copy_checklist(self) -> None:
        QApplication.clipboard().setText(self._checklist.toPlainText())


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFrame,
)

from core.device_detect import list_disks
from core.state import AppState, DiskInfo
from ui.pages._page_base_style import BASE_STYLE, WARNING_BOX

_USB_NOTE = (
    "ℹ  USB SSD/drive targets: your Pi 4/400 may need a bootloader update "
    "and USB-boot order set before it can boot from USB. See the Done screen for details."
)

_COLOR_SYSTEM   = QColor("#555558")
_COLOR_ELIGIBLE = QColor("#e8e8e8")
_COLOR_SELECTED = QColor("#5b9bd5")


class DevicePage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._disks: list[DiskInfo] = []
        self._detect_error: str = ''
        self.setStyleSheet(BASE_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(14)

        title = QLabel("Select Target Device")
        title.setObjectName("page-title")
        layout.addWidget(title)
        layout.addWidget(_sep())

        desc = QLabel(
            "Only SD cards and USB drives are shown. "
            "Internal disks are hidden for safety."
        )
        desc.setObjectName("page-desc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._warning = QLabel(
            "⚠  All data on the selected device will be permanently erased."
        )
        self._warning.setStyleSheet(WARNING_BOX)
        self._warning.setWordWrap(True)
        layout.addWidget(self._warning)

        self._usb_note = QLabel(_USB_NOTE)
        self._usb_note.setStyleSheet(
            "color: #888890; font-size: 11px; background: transparent;"
        )
        self._usb_note.setWordWrap(True)
        self._usb_note.setVisible(False)
        layout.addWidget(self._usb_note)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Available devices:"))
        hdr.addStretch(1)
        self._btn_refresh = QPushButton("⟳  Refresh")
        self._btn_refresh.clicked.connect(self.refresh)
        hdr.addWidget(self._btn_refresh)
        layout.addLayout(hdr)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, 1)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #d9534f; font-size: 12px; background: transparent;")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        self.refresh()

    # ── device refresh ────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._list.clear()
        self._disks = []
        self._state.target_device = None
        self._error_label.setVisible(False)
        self._usb_note.setVisible(False)

        try:
            all_disks = list_disks()
        except RuntimeError as e:
            self._error_label.setText(
                f"⛔  FAIL SAFE : Cannot determine system disk:\n{e}\n\n"
                "Refusing to list devices. Fix the detection issue before proceeding."
            )
            self._error_label.setVisible(True)
            return

        # Only show SD cards and USB drives : hide internal NVMe/SATA entirely
        disks = [d for d in all_disks if d.bus_type in ('SD card', 'USB disk')]

        if not disks:
            item = QListWidgetItem("No SD cards or USB drives detected. Insert a device and refresh.")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(_COLOR_SYSTEM)
            self._list.addItem(item)
            return

        for disk in disks:
            self._disks.append(disk)
            item = self._make_item(disk)
            self._list.addItem(item)

    def _make_item(self, disk: DiskInfo) -> QListWidgetItem:
        if disk.is_system:
            line1 = f"{disk.dev}  :  {disk.model}"
            line2 = f"  {disk.size_human}  ·  {disk.bus_type}  ·  SYSTEM DISK : protected"
            text = f"{line1}\n{line2}"
            item = QListWidgetItem(text)
            item.setFlags(Qt.NoItemFlags)   # genuinely unselectable
            item.setForeground(_COLOR_SYSTEM)
        else:
            line1 = f"{disk.dev}  :  {disk.model}"
            line2 = f"  {disk.size_human}  ·  {disk.bus_type}"
            text = f"{line1}\n{line2}"
            item = QListWidgetItem(text)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item.setForeground(_COLOR_ELIGIBLE)

        # stash DiskInfo on the item
        item.setData(Qt.UserRole, disk)
        return item

    def _on_selection_changed(self) -> None:
        items = self._list.selectedItems()
        if not items:
            self._state.target_device = None
            self._usb_note.setVisible(False)
            return
        disk: DiskInfo = items[0].data(Qt.UserRole)
        self._state.target_device = disk
        self._usb_note.setVisible(disk.bus_type == 'USB disk')

    # ── validation for wizard nav ─────────────────────────────────────────────

    def is_ready(self) -> tuple[bool, str]:
        if self._error_label.isVisible():
            return False, "System disk detection failed : cannot proceed safely."
        if not self._state.target_device:
            return False, "No device selected."
        if self._state.target_device.is_system:
            return False, "Cannot select the system disk."
        return True, ''


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QGridLayout, QCheckBox, QPushButton, QFileDialog, QScrollArea,
)
from core.state import AppState
from ui.pages._page_base_style import BASE_STYLE, DANGER_BOX
from ui.pages._flash_anim import FlashAnimWidget

_CONFIRM_HINT = "color: #888890; font-size: 11px; background: transparent;"
_PURIFY_WARNING = (
    "⚠  DISTRIBUTION MODE: SSH host keys, machine-id, logs, DHCP leases and "
    "network connections will be PURIFIED before writing. No credentials will be "
    "in the final image. End user runs interactive setup on first boot."
)
_PURIFY_STYLE = (
    "color: #d4813a; font-size: 11px; "
    "background: rgba(45, 35, 20, 200); "
    "border: 1px solid rgba(212, 129, 58, 160); padding: 6px 12px;"
)


class ConfirmPage(QWidget):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self.setStyleSheet(BASE_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── fixed header (title + separator) ─────────────────────────────────
        header = QWidget()
        header.setStyleSheet("QWidget { background: transparent; }")
        hdr_layout = QVBoxLayout(header)
        hdr_layout.setContentsMargins(40, 22, 40, 0)
        hdr_layout.setSpacing(8)
        title = QLabel("Confirm Flash Operation")
        title.setObjectName("page-title")
        hdr_layout.addWidget(title)
        hdr_layout.addWidget(_sep())
        outer.addWidget(header)

        # ── scrollable body ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(400)
        self._scroll = scroll
        outer.addWidget(scroll)

        self._anim = FlashAnimWidget()
        outer.addWidget(self._anim, 1)

        body = QWidget()
        body.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(40, 5, 40, 8)
        layout.setSpacing(5)
        scroll.setWidget(body)

        danger = QLabel("⛔  ALL DATA ON THE TARGET DEVICE WILL BE PERMANENTLY DESTROYED. This cannot be undone.")
        danger.setStyleSheet(DANGER_BOX)
        danger.setWordWrap(True)
        layout.addWidget(danger)

        # Purify warning : Distribution only
        self._purify_warn = QLabel(_PURIFY_WARNING)
        self._purify_warn.setStyleSheet(_PURIFY_STYLE)
        self._purify_warn.setWordWrap(True)
        self._purify_warn.setVisible(False)
        layout.addWidget(self._purify_warn)

        # Summary grid — objectName prevents QFrame selector cascading to children
        summary = QFrame()
        summary.setObjectName("summary")
        summary.setFrameShape(QFrame.StyledPanel)
        summary.setStyleSheet(
            "QFrame#summary { background: rgba(22,22,24,180); border: 1px solid rgba(62,62,72,160); }"
        )
        grid = QGridLayout(summary)
        grid.setContentsMargins(12, 4, 12, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(1, 1)

        self._rows: dict[str, tuple[QLabel, QLabel]] = {}
        for i, key in enumerate([
            "Mode:", "Target device:", "Model:", "Size:", "Type:",
            "Tarball:", "Hostname:", "Username:", "Packages:",
        ]):
            k = QLabel(key)
            k.setObjectName("key")
            k.setStyleSheet("color: #888890; font-size: 12px; background: transparent;")
            v = QLabel("—")
            v.setObjectName("value")
            v.setStyleSheet("color: #e8e8e8; font-size: 12px; background: transparent;")
            v.setWordWrap(True)
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)
            self._rows[key] = (k, v)

        layout.addWidget(summary)

        # ── Distribution: shrink for distribution ─────────────────────────────
        self._shrink_section = QWidget()
        self._shrink_section.setStyleSheet("QWidget { background: transparent; }")
        sh_layout = QVBoxLayout(self._shrink_section)
        sh_layout.setContentsMargins(0, 2, 0, 0)
        sh_layout.setSpacing(5)

        shrink_lbl = QLabel("DISTRIBUTION IMAGE")
        shrink_lbl.setStyleSheet(
            "color: #d4813a; font-size: 12px; font-weight: bold; background: transparent;"
        )
        sh_layout.addWidget(shrink_lbl)

        self._shrink_cb = QCheckBox("Shrink image for distribution (.img.xz)")
        sh_layout.addWidget(self._shrink_cb)
        self._shrink_cb.toggled.connect(self._on_shrink_toggled)

        shrink_hint = QLabel("Compressed .img.xz — auto-expands on flash. No device required.")
        shrink_hint.setObjectName("hint")
        shrink_hint.setWordWrap(True)
        sh_layout.addWidget(shrink_hint)

        self._shrink_path_row = QWidget()
        self._shrink_path_row.setStyleSheet("QWidget { background: transparent; }")
        pr_layout = QHBoxLayout(self._shrink_path_row)
        pr_layout.setContentsMargins(0, 0, 0, 0)
        pr_layout.setSpacing(6)
        path_lbl = QLabel("Save as:")
        path_lbl.setStyleSheet("color: #888890; font-size: 12px; background: transparent;")
        pr_layout.addWidget(path_lbl)
        self._shrink_path = QLineEdit()
        self._shrink_path.setPlaceholderText("/home/user/xeropi-dist.img.xz")
        self._shrink_path.textChanged.connect(
            lambda t: setattr(self._state, 'shrink_output_path', t)
        )
        pr_layout.addWidget(self._shrink_path, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_shrink_path)
        pr_layout.addWidget(browse_btn)
        sh_layout.addWidget(self._shrink_path_row)
        self._shrink_path_row.setVisible(False)

        self._shrink_section.setVisible(False)
        layout.addWidget(self._shrink_section)

        self._confirm_hint = QLabel("Type the target device path below to confirm (e.g. /dev/sdb):")
        self._confirm_hint.setStyleSheet(_CONFIRM_HINT)
        layout.addWidget(self._confirm_hint)

        self._confirm_input = QLineEdit()
        self._confirm_input.setPlaceholderText("/dev/…")
        layout.addWidget(self._confirm_input)

        layout.addStretch(1)

    def populate(self) -> None:
        """Call before showing this page to refresh the summary."""
        is_dist        = self._state.mode == 'distribution'
        is_flash_image = self._state.flash_mode == 'flash_image'
        dist_flash     = is_dist and is_flash_image

        # Purify warning: dist build only, not when flashing existing
        self._purify_warn.setVisible(is_dist and not is_flash_image)

        # Device rows: show for personal OR dist+flash_image
        show_device = not is_dist or dist_flash
        for rk in ("Target device:", "Model:", "Size:", "Type:"):
            self._rows[rk][0].setVisible(show_device)
            self._rows[rk][1].setVisible(show_device)

        self._confirm_hint.setVisible(show_device)
        self._confirm_input.setVisible(show_device)

        # Shrink section: dist build only
        show_shrink = is_dist and not is_flash_image
        self._shrink_section.setVisible(show_shrink)
        if show_shrink:
            self._shrink_cb.setChecked(True)
            self._shrink_cb.setEnabled(False)
            self._state.shrink_image = True
            self._shrink_path_row.setVisible(True)
        else:
            self._state.shrink_image = False

        # Scroll area height: dist+flash_image has less content → give graphic more room
        self._scroll.setMinimumHeight(200 if dist_flash else 400)

        # Mode row
        if dist_flash:
            mode_text = "Flash Existing — No Build"
        elif is_dist:
            mode_text = "Distribution : image build only — no flash"
        elif is_flash_image:
            mode_text = "Personal : direct image flash"
        else:
            mode_text = "Personal : credentials baked in"
        self._rows["Mode:"][1].setText(mode_text)

        # Tarball / Image row
        if is_flash_image:
            self._rows["Tarball:"][0].setText("Image:")
            self._rows["Tarball:"][1].setText(self._state.flash_image_path or "(not selected)")
        else:
            self._rows["Tarball:"][0].setText("Tarball:")
            self._rows["Tarball:"][1].setText(self._state.tarball_path or "(not selected)")

        # Device detail rows
        if show_device:
            d = self._state.target_device
            if d:
                self._rows["Target device:"][1].setText(d.dev)
                self._rows["Model:"][1].setText(d.model)
                self._rows["Size:"][1].setText(d.size_human)
                self._rows["Type:"][1].setText(d.bus_type)
            else:
                for rk in ("Target device:", "Model:", "Size:", "Type:"):
                    self._rows[rk][1].setText("(not selected)")

        # Config rows: hidden in flash_image mode
        show_config = not is_flash_image
        for rk in ("Hostname:", "Username:", "Packages:"):
            self._rows[rk][0].setVisible(show_config)
            self._rows[rk][1].setVisible(show_config)

        if show_config:
            if is_dist:
                self._rows["Hostname:"][1].setText("(set by end user at first boot)")
                self._rows["Username:"][1].setText("(set by end user at first boot)")
            else:
                self._rows["Hostname:"][1].setText(self._state.hostname or "(not set)")
                self._rows["Username:"][1].setText(self._state.username or "(not set)")

            pkgs = (
                self._state.packages
                + (self._state.extra_packages.split() if self._state.extra_packages else [])
                + self._state.user_added_packages
            )
            pkg_text = ", ".join(pkgs) if pkgs else "(none)"
            if is_dist:
                pkg_text += "  (default — end user may modify)"
            self._rows["Packages:"][1].setText(pkg_text)

        self._confirm_input.clear()

    def is_ready(self) -> tuple[bool, str]:
        is_dist        = self._state.mode == 'distribution'
        is_flash_image = self._state.flash_mode == 'flash_image'

        if is_dist and not is_flash_image:
            if not self._state.shrink_output_path.strip():
                return False, "Specify an output path for the distribution image."
            return True, ''

        # Personal or dist+flash_image — device confirmation required
        d = self._state.target_device
        if not d:
            return False, "No target device selected."
        typed = self._confirm_input.text().strip()
        if typed != d.dev:
            return False, f"Type '{d.dev}' exactly to confirm."

        return True, ''


    def _on_shrink_toggled(self, checked: bool) -> None:
        self._state.shrink_image = checked
        self._shrink_path_row.setVisible(checked)

    def _browse_shrink_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save distribution image as",
            str(Path.home()),
            "Compressed images (*.img.xz);;All files (*)",
        )
        if path:
            if not path.endswith('.img.xz'):
                path += '.img.xz'
            self._shrink_path.setText(path)
            self._state.shrink_output_path = path


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

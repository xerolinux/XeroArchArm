from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QProgressBar, QFileDialog, QButtonGroup,
)

from core.state import AppState
from core.tarball_validate import validate_tarball
from ui.pages._page_base_style import BASE_STYLE
from ui.pages._pi_image import PiImageWidget
from ui.workers.downloader import DownloadWorker

_STATUS_OK  = "color: #5cb85c; font-size: 12px; background: transparent;"
_STATUS_ERR = "color: #d9534f; font-size: 12px; background: transparent;"
_STATUS_INF = "color: #888890; font-size: 12px; background: transparent;"
_SECTION    = "color: #5b9bd5; font-size: 12px; font-weight: bold; padding-top: 4px;"

_MODE_PERSONAL = (
    "Personal : credentials baked into the image. "
    "Ready on first boot. For your own devices only. "
    "Do NOT share or distribute."
)
_MODE_DISTRIB = (
    "Distribution : image is purified (no baked credentials). "
    "An interactive setup wizard runs on the end user's first boot. "
    "Safe to share or distribute."
)
_FLASH_BUILD_DESC = (
    "Compile & Flash : customize an Arch ARM tarball (user, hostname, packages, WiFi) "
    "then write to your device."
)
_FLASH_IMG_DESC = (
    "Flash Existing : write a pre-compiled .img or .img.xz directly to your device. "
    "Skips all customization steps."
)

_MODE_BTN = """
QPushButton#mode-btn {{
    background: rgba(48, 48, 58, 200);
    color: #a0a0a8;
    border: 1px solid rgba(100, 100, 118, 220);
    padding: 10px 24px;
    font-size: 13px;
    font-weight: bold;
}}
QPushButton#mode-btn:checked {{
    background: {accent};
    color: #ffffff;
    border: 1px solid {accent};
}}
QPushButton#mode-btn:hover:!checked {{
    background: rgba(64, 64, 76, 220);
    color: #e8e8e8;
    border: 1px solid rgba(120, 120, 140, 220);
}}
"""
_PERSONAL_ACCENT = "#5b9bd5"
_DISTRIB_ACCENT  = "#d4813a"

_CARD_STYLE = """
QFrame#info-card {
    background: rgba(18, 42, 60, 200);
    border-left: 4px solid #2a9d8f;
    border-top: 1px solid rgba(42, 157, 143, 80);
    border-right: 1px solid rgba(42, 157, 143, 40);
    border-bottom: 1px solid rgba(42, 157, 143, 40);
    padding: 0px;
}
QLabel#card-title {
    color: #2a9d8f;
    font-size: 13px;
    font-weight: bold;
    background: transparent;
}
QLabel#card-body {
    color: #a8ddd8;
    font-size: 12px;
    background: transparent;
}
"""

_CARD_BODY = (
    "Flashes a base <b>Arch Linux ARM aarch64</b> image to your SD card or USB drive "
    "for Raspberry Pi 4/400.<br><br>"
    "The result is a <b>minimal headless server</b> : no desktop environment "
    "(KDE, GNOME, etc.) and no GUI applications. "
    "Pre-configured with Docker, SSH, NetworkManager, and your choice of server tools. "
    "Accessible via SSH on first boot."
)


class TarballPage(QWidget):
    def __init__(self, state: AppState, dist_enabled: bool = False, parent=None):
        super().__init__(parent)
        self._state = state
        self._dist_enabled = dist_enabled
        self._worker: DownloadWorker | None = None
        _init_accent = _DISTRIB_ACCENT if dist_enabled else _PERSONAL_ACCENT
        self.setStyleSheet(BASE_STYLE + _CARD_STYLE + _MODE_BTN.format(accent=_init_accent))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.setSpacing(14)

        title = QLabel("Home")
        title.setObjectName("page-title")
        layout.addWidget(title)
        layout.addWidget(_sep())

        # ── INFO CARD ─────────────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("info-card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 14)
        card_layout.setSpacing(6)

        card_title = QLabel("Arch Linux ARM : Headless Server for Raspberry Pi 4/400")
        card_title.setObjectName("card-title")
        card_layout.addWidget(card_title)

        card_body = QLabel(_CARD_BODY)
        card_body.setObjectName("card-body")
        card_body.setWordWrap(True)
        card_body.setTextFormat(Qt.RichText)
        card_layout.addWidget(card_body)

        layout.addWidget(card)

        # ── BUILD MODE TOGGLE (--dist only) ───────────────────────────────────
        self._mode_section = QWidget()
        self._mode_section.setStyleSheet("QWidget { background: transparent; }")
        ms_layout = QVBoxLayout(self._mode_section)
        ms_layout.setContentsMargins(0, 0, 0, 0)
        ms_layout.setSpacing(8)

        mode_lbl = QLabel("BUILD MODE")
        mode_lbl.setStyleSheet(_SECTION)
        ms_layout.addWidget(mode_lbl)

        btn_row = QHBoxLayout()
        self._btn_distrib = QPushButton("Distribution")
        self._btn_distrib.setObjectName("mode-btn")
        self._btn_distrib.setCheckable(True)
        self._btn_distrib.setChecked(True)

        self._btn_personal = QPushButton("Personal")
        self._btn_personal.setObjectName("mode-btn")
        self._btn_personal.setCheckable(True)

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._btn_distrib, 1)
        self._mode_group.addButton(self._btn_personal, 0)
        self._mode_group.setExclusive(True)
        self._mode_group.idToggled.connect(self._on_mode_changed)

        btn_row.addWidget(self._btn_distrib)
        if dist_enabled:
            # Flash Existing sits next to Distribution in dist mode
            self._btn_flash_existing = QPushButton("Flash Existing")
            self._btn_flash_existing.setObjectName("mode-btn")
            self._btn_flash_existing.setCheckable(True)
            self._mode_group.addButton(self._btn_flash_existing, 2)
            btn_row.addWidget(self._btn_flash_existing)
        else:
            btn_row.addWidget(self._btn_personal)
        btn_row.addStretch(1)
        ms_layout.addLayout(btn_row)

        self._mode_desc = QLabel(_MODE_PERSONAL)
        self._mode_desc.setStyleSheet(_STATUS_INF)
        self._mode_desc.setWordWrap(True)
        ms_layout.addWidget(self._mode_desc)

        self._mode_section.setVisible(dist_enabled)
        layout.addWidget(self._mode_section)

        if dist_enabled:
            self._state.mode = 'distribution'
            self._mode_desc.setText(_MODE_DISTRIB)
            layout.addWidget(_sep())

        # ── FLASH MODE TOGGLE (personal mode only) ────────────────────────────
        self._flash_mode_section = QWidget()
        self._flash_mode_section.setStyleSheet("QWidget { background: transparent; }")
        fm_layout = QVBoxLayout(self._flash_mode_section)
        fm_layout.setContentsMargins(0, 0, 0, 0)
        fm_layout.setSpacing(8)

        fm_lbl = QLabel("FLASH MODE")
        fm_lbl.setStyleSheet(_SECTION)
        fm_layout.addWidget(fm_lbl)

        fm_btn_row = QHBoxLayout()
        self._btn_build = QPushButton("Compile & Flash")
        self._btn_build.setObjectName("mode-btn")
        self._btn_build.setCheckable(True)
        self._btn_build.setChecked(True)

        self._btn_flash_img = QPushButton("Flash Existing")
        self._btn_flash_img.setObjectName("mode-btn")
        self._btn_flash_img.setCheckable(True)

        self._flash_mode_group = QButtonGroup(self)
        self._flash_mode_group.addButton(self._btn_build, 0)
        self._flash_mode_group.addButton(self._btn_flash_img, 1)
        self._flash_mode_group.setExclusive(True)
        self._flash_mode_group.idToggled.connect(self._on_flash_mode_changed)

        fm_btn_row.addWidget(self._btn_build)
        fm_btn_row.addWidget(self._btn_flash_img)
        fm_btn_row.addStretch(1)
        fm_layout.addLayout(fm_btn_row)

        self._flash_mode_desc = QLabel(_FLASH_BUILD_DESC)
        self._flash_mode_desc.setStyleSheet(_STATUS_INF)
        self._flash_mode_desc.setWordWrap(True)
        fm_layout.addWidget(self._flash_mode_desc)

        self._flash_mode_section.setVisible(not dist_enabled)
        layout.addWidget(self._flash_mode_section)

        # ── TARBALL SECTION (build mode) ──────────────────────────────────────
        self._tarball_section = QWidget()
        self._tarball_section.setStyleSheet("QWidget { background: transparent; }")
        tb_layout = QVBoxLayout(self._tarball_section)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(8)

        sec = QLabel("DOWNLOAD LATEST  (Pi 4/400 aarch64)")
        sec.setStyleSheet(_SECTION)
        tb_layout.addWidget(sec)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Save to:"))
        self._dest_edit = QLineEdit()
        self._dest_edit.setText(str(Path.home() / "Downloads"))
        self._dest_edit.setReadOnly(True)
        btn_dest = QPushButton("Change…")
        btn_dest.clicked.connect(self._pick_dest)
        dest_row.addWidget(self._dest_edit, 1)
        dest_row.addWidget(btn_dest)
        tb_layout.addLayout(dest_row)

        dl_row = QHBoxLayout()
        self._btn_download = QPushButton("Download")
        self._btn_download.clicked.connect(self._start_download)
        self._btn_cancel_dl = QPushButton("Cancel")
        self._btn_cancel_dl.clicked.connect(self._cancel_download)
        self._btn_cancel_dl.setEnabled(False)
        dl_row.addWidget(self._btn_download)
        dl_row.addWidget(self._btn_cancel_dl)
        dl_row.addStretch(1)
        tb_layout.addLayout(dl_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        tb_layout.addWidget(self._progress)

        self._dl_status = QLabel("")
        self._dl_status.setStyleSheet(_STATUS_INF)
        self._dl_status.setWordWrap(True)
        tb_layout.addWidget(self._dl_status)

        layout.addWidget(self._tarball_section)

        # ── IMAGE SECTION (flash_image mode) ──────────────────────────────────
        self._image_section = QWidget()
        self._image_section.setStyleSheet("QWidget { background: transparent; }")
        img_layout = QVBoxLayout(self._image_section)
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.setSpacing(8)

        img_lbl = QLabel("EXISTING IMAGE  (.img or .img.xz)")
        img_lbl.setStyleSheet(_SECTION)
        img_layout.addWidget(img_lbl)

        img_hint = QLabel(
            "Select a pre-compiled image file. "
            "Compressed .img.xz files are decompressed on the fly during flash."
        )
        img_hint.setStyleSheet(_STATUS_INF)
        img_hint.setWordWrap(True)
        img_layout.addWidget(img_hint)

        img_path_row = QHBoxLayout()
        self._img_path_edit = QLineEdit()
        self._img_path_edit.setPlaceholderText("/path/to/image.img  or  image.img.xz")
        self._img_path_edit.setReadOnly(True)
        img_browse_btn = QPushButton("Browse…")
        img_browse_btn.clicked.connect(self._pick_image)
        img_path_row.addWidget(self._img_path_edit, 1)
        img_path_row.addWidget(img_browse_btn)
        img_layout.addLayout(img_path_row)

        self._img_status = QLabel("")
        self._img_status.setStyleSheet(_STATUS_INF)
        self._img_status.setWordWrap(True)
        img_layout.addWidget(self._img_status)

        self._image_section.setVisible(False)
        layout.addWidget(self._image_section)

        pi_row = QHBoxLayout()
        pi_row.setContentsMargins(0, 0, 0, 0)
        pi_row.addStretch(1)
        pi_row.addWidget(PiImageWidget(), 4)
        pi_row.addStretch(1)
        layout.addLayout(pi_row, 1)

        # Check for existing tarball in current dest folder
        self._check_existing(self._dest_edit.text())

    # ── build mode toggle ─────────────────────────────────────────────────────

    def _on_mode_changed(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        if btn_id == 1:  # Distribution
            self._state.mode = 'distribution'
            self._state.flash_mode = 'build'
            self._mode_desc.setText(_MODE_DISTRIB)
            self.setStyleSheet(BASE_STYLE + _CARD_STYLE + _MODE_BTN.format(accent=_DISTRIB_ACCENT))
            self._tarball_section.setVisible(True)
            self._image_section.setVisible(False)
        elif btn_id == 2:  # Flash Existing (dist mode only)
            self._state.mode = 'distribution'
            self._state.flash_mode = 'flash_image'
            self._mode_desc.setText(_FLASH_IMG_DESC)
            self.setStyleSheet(BASE_STYLE + _CARD_STYLE + _MODE_BTN.format(accent=_DISTRIB_ACCENT))
            self._tarball_section.setVisible(False)
            self._image_section.setVisible(True)
        else:  # Personal (btn_id == 0)
            self._state.mode = 'personal'
            self._state.flash_mode = 'build'
            self._mode_desc.setText(_MODE_PERSONAL)
            self.setStyleSheet(BASE_STYLE + _CARD_STYLE + _MODE_BTN.format(accent=_PERSONAL_ACCENT))
            self._tarball_section.setVisible(True)
            self._image_section.setVisible(False)

    # ── flash mode toggle ─────────────────────────────────────────────────────

    def _on_flash_mode_changed(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        if btn_id == 0:  # Build & Flash
            self._state.flash_mode = 'build'
            self._flash_mode_desc.setText(_FLASH_BUILD_DESC)
            self._tarball_section.setVisible(True)
            self._image_section.setVisible(False)
        else:  # Flash Image
            self._state.flash_mode = 'flash_image'
            self._flash_mode_desc.setText(_FLASH_IMG_DESC)
            self._tarball_section.setVisible(False)
            self._image_section.setVisible(True)

    # ── existing tarball detection ────────────────────────────────────────────

    def _check_existing(self, folder: str) -> None:
        from ui.workers.downloader import FILENAME
        candidate = Path(folder) / FILENAME
        if not candidate.exists():
            return
        ok, msg = validate_tarball(str(candidate))
        if ok:
            self._state.tarball_path = str(candidate)
            self._dl_status.setStyleSheet(_STATUS_OK)
            self._dl_status.setText(
                f"✓ Image already downloaded : no download needed.\n{candidate}"
            )
            self._btn_download.setText("Re-download")

    # ── destination ───────────────────────────────────────────────────────────

    def _pick_dest(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Download destination", self._dest_edit.text()
        )
        if folder:
            self._dest_edit.setText(folder)
            self._check_existing(folder)

    # ── image picker ──────────────────────────────────────────────────────────

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select image file",
            str(Path.home()),
            "Image files (*.img *.img.xz);;All files (*)",
        )
        if path:
            self._img_path_edit.setText(path)
            self._state.flash_image_path = path
            self._img_status.setStyleSheet(_STATUS_OK)
            self._img_status.setText(f"✓ {Path(path).name}")

    # ── download ──────────────────────────────────────────────────────────────

    def _start_download(self) -> None:
        dest = self._dest_edit.text()
        if not dest or not Path(dest).is_dir():
            self._dl_status.setStyleSheet(_STATUS_ERR)
            self._dl_status.setText("✗ Destination folder does not exist.")
            return

        self._btn_download.setEnabled(False)
        self._btn_download.setText("Downloading…")
        self._btn_cancel_dl.setEnabled(True)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._dl_status.setStyleSheet(_STATUS_INF)
        self._dl_status.setText("Starting…")

        self._worker = DownloadWorker(dest)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_dl_finished)
        self._worker.failed.connect(self._on_dl_failed)
        self._worker.start()

    def _cancel_download(self) -> None:
        if self._worker:
            self._worker.cancel()

    def _on_progress(self, pct: int, status: str) -> None:
        self._progress.setValue(pct)
        self._dl_status.setText(status)

    def _on_dl_finished(self, path: str) -> None:
        self._reset_dl_ui()
        ok, msg = validate_tarball(path)
        if ok:
            self._dl_status.setStyleSheet(_STATUS_OK)
            self._dl_status.setText("✓ Download complete : checksum verified.")
            self._state.tarball_path = path
        else:
            self._dl_status.setStyleSheet(_STATUS_ERR)
            self._dl_status.setText(f"✗ Download OK but validation failed: {msg}")
            self._state.tarball_path = ''

    def _on_dl_failed(self, msg: str) -> None:
        self._reset_dl_ui()
        self._dl_status.setStyleSheet(_STATUS_ERR)
        self._dl_status.setText(f"✗ {msg}")

    def _reset_dl_ui(self) -> None:
        self._btn_download.setEnabled(True)
        self._btn_download.setText("Download")
        self._btn_cancel_dl.setEnabled(False)
        self._progress.setVisible(False)
        self._worker = None

    # ── nav gate ──────────────────────────────────────────────────────────────

    def is_ready(self) -> tuple[bool, str]:
        if self._state.flash_mode == 'flash_image':
            p = self._state.flash_image_path
            if not p:
                return False, "Select an image file to flash."
            if not Path(p).exists():
                return False, f"Image file not found:\n{p}"
            return True, ''
        if not self._state.tarball_path:
            return False, "Download the image first."
        return True, ''


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    return f

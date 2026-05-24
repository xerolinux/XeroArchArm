"""Downloads ArchLinuxARM-rpi-aarch64-latest.tar.gz with MD5 verification."""

import hashlib
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal

TARBALL_URL = "http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-aarch64-latest.tar.gz"
MD5_URL     = "http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-aarch64-latest.tar.gz.md5"
FILENAME    = "ArchLinuxARM-rpi-aarch64-latest.tar.gz"
CHUNK       = 65536


class DownloadWorker(QThread):
    progress = Signal(int, str)   # percent (0-100), "X MB / Y MB · Z MB/s · ETA Ns"
    finished = Signal(str)        # absolute path to verified file
    failed   = Signal(str)        # error message

    def __init__(self, dest_dir: str, parent=None):
        super().__init__(parent)
        self._dest_dir = dest_dir
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        dest = Path(self._dest_dir) / FILENAME
        try:
            self._download(dest)
        except Exception as e:
            _rm(dest)
            self.failed.emit(f"Download failed: {e}")

    def _download(self, dest: Path) -> None:
        # Fetch expected MD5 first (small, fast)
        self.progress.emit(0, "Fetching checksum from mirror…")
        with urllib.request.urlopen(MD5_URL, timeout=30) as r:
            md5_line = r.read().decode().strip()
        expected_md5 = md5_line.split()[0]

        # Download tarball
        self.progress.emit(0, "Connecting…")
        req = urllib.request.Request(
            TARBALL_URL, headers={"User-Agent": "XeroPi4/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            t0 = time.monotonic()
            hasher = hashlib.md5()

            with open(dest, "wb") as f:
                while True:
                    if self._cancelled:
                        _rm(dest)
                        self.failed.emit("Download cancelled.")
                        return

                    chunk = r.read(CHUNK)
                    if not chunk:
                        break

                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)

                    elapsed = time.monotonic() - t0 or 0.001
                    speed = downloaded / elapsed
                    pct = int(downloaded * 100 / total) if total else 0
                    status = (
                        f"{_h(downloaded)}"
                        + (f" / {_h(total)}" if total else "")
                        + f"  ·  {_h(speed)}/s"
                        + (f"  ·  ETA {_eta((total-downloaded)/speed)}" if total and speed > 0 else "")
                    )
                    self.progress.emit(pct, status)

        # Verify
        self.progress.emit(100, "Verifying MD5…")
        actual = hasher.hexdigest()
        if actual != expected_md5:
            _rm(dest)
            self.failed.emit(
                f"Checksum mismatch : file removed, please retry.\n"
                f"  Expected: {expected_md5}\n"
                f"  Got:      {actual}"
            )
            return

        self.finished.emit(str(dest))


def _rm(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def _h(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _eta(secs: float) -> str:
    if secs < 0:
        return ":"
    if secs < 60:
        return f"{int(secs)}s"
    if secs < 3600:
        return f"{int(secs/60)}m {int(secs%60)}s"
    return f"{int(secs/3600)}h {int((secs%3600)/60)}m"

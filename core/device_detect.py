"""
BLOCKLIST device detection.

Identifies disks backing the running OS by reading /proc/mounts,
maps every protected mountpoint to its parent physical disk,
then returns ALL other disks as eligible flash targets.

Raises RuntimeError (fail-safe) if the system disk cannot be
confidently determined.
"""

import os
import re
from pathlib import Path

from core.state import DiskInfo

_PROTECTED_MOUNTS = {'/', '/home', '/boot', '/boot/efi'}
_SKIP_DEVNAME = re.compile(r'^(loop|ram|zram|dm-|sr|fd|md|nbd)')


# ── partition → parent disk ───────────────────────────────────────────────────

def partition_to_disk(part: str) -> str:
    """Map partition device name to parent disk name.

    nvme0n1p2  → nvme0n1
    mmcblk0p2  → mmcblk0
    sda3       → sda
    sda        → sda  (already a disk)
    """
    m = re.match(r'(nvme\d+n\d+)p\d+$', part)
    if m:
        return m.group(1)
    m = re.match(r'(mmcblk\d+)p\d+$', part)
    if m:
        return m.group(1)
    m = re.match(r'([a-z]+)\d+$', part)
    if m:
        return m.group(1)
    return part


# ── system disk detection ─────────────────────────────────────────────────────

def get_system_disks() -> set[str]:
    """Return set of disk device names backing protected mountpoints.

    Raises RuntimeError if / is not found or /proc/mounts is unreadable.
    """
    try:
        mounts_text = Path('/proc/mounts').read_text()
    except OSError as e:
        raise RuntimeError(f"Cannot read /proc/mounts: {e}") from e

    found_root = False
    system_disks: set[str] = set()

    for line in mounts_text.splitlines():
        cols = line.split()
        if len(cols) < 2:
            continue
        device, mountpoint = cols[0], cols[1]
        if mountpoint not in _PROTECTED_MOUNTS:
            continue
        if mountpoint == '/':
            found_root = True
        if not device.startswith('/dev/'):
            continue
        devname = device.removeprefix('/dev/')
        system_disks.add(partition_to_disk(devname))

    if not found_root:
        raise RuntimeError(
            "Root mountpoint '/' not found in /proc/mounts : "
            "cannot safely determine system disk. Refusing to continue."
        )

    return system_disks


# ── per-disk helpers ──────────────────────────────────────────────────────────

def _read_sys(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ''


def _get_bus_type(devname: str) -> str:
    """SD card / USB disk / NVMe / other."""
    try:
        link = os.readlink(f'/sys/block/{devname}')
    except OSError:
        link = ''
    if devname.startswith('mmcblk') or 'mmc' in link:
        return 'SD card'
    if 'usb' in link:
        return 'USB disk'
    if devname.startswith('nvme'):
        return 'NVMe'
    return 'other'


def _size_human(size_bytes: int) -> str:
    n = float(size_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


# ── public API ────────────────────────────────────────────────────────────────

def list_disks() -> list[DiskInfo]:
    """Return list of all physical disks.

    System disks have is_system=True and MUST NOT be written to.
    Raises RuntimeError (fail-safe) if system disk cannot be determined.
    """
    system_disk_names = get_system_disks()

    disks: list[DiskInfo] = []
    for dev_path in sorted(Path('/sys/block').iterdir()):
        devname = dev_path.name
        if _SKIP_DEVNAME.match(devname):
            continue

        size_str = _read_sys(f'/sys/block/{devname}/size')
        if not size_str:
            continue
        try:
            size_sectors = int(size_str)
        except ValueError:
            continue
        if size_sectors == 0:
            continue

        size_bytes = size_sectors * 512
        model = _read_sys(f'/sys/block/{devname}/device/model') or 'Unknown model'
        bus_type = _get_bus_type(devname)
        is_system = devname in system_disk_names

        disks.append(DiskInfo(
            dev=f'/dev/{devname}',
            model=model.strip(),
            size_bytes=size_bytes,
            size_human=_size_human(size_bytes),
            bus_type=bus_type,
            is_system=is_system,
        ))

    return disks

"""Validates a .tar.gz file as an ArchLinuxARM rootfs (non-destructive peek)."""

import tarfile
from pathlib import Path

# bin is a symlink (not a real dir) on modern Arch : don't require it
_REQUIRED_DIRS = {'etc', 'usr', 'boot'}
_MAX_MEMBERS_TO_PEEK = 5000


def validate_tarball(path: str) -> tuple[bool, str]:
    """Returns (ok, error_message). error_message is '' when ok=True."""
    p = Path(path)

    if not p.exists():
        return False, "File not found."

    if not (p.name.endswith('.tar.gz') or p.name.endswith('.tgz')):
        return False, "File must be a .tar.gz archive."

    try:
        with tarfile.open(path, 'r:gz') as tf:
            top_dirs: set[str] = set()
            for i, member in enumerate(tf):
                if i >= _MAX_MEMBERS_TO_PEEK:
                    break
                parts = member.name.lstrip('./').split('/')
                if parts and parts[0]:
                    top_dirs.add(parts[0])
                # Early exit once all required dirs confirmed
                if _REQUIRED_DIRS.issubset(top_dirs):
                    break

        missing = _REQUIRED_DIRS - top_dirs
        if missing:
            return False, (
                f"Archive does not look like an ArchLinuxARM rootfs.\n"
                f"Missing top-level dirs: {', '.join(sorted(missing))}"
            )
    except tarfile.TarError as e:
        return False, f"Cannot read archive: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"

    return True, ''

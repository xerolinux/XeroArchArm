#!/usr/bin/env python3
"""Privileged flash worker : executed as root via pkexec.

Protocol: one JSON object per stdout line.
  {"type": "log",      "msg": "..."}
  {"type": "progress", "pct": N, "msg": "..."}
  {"type": "error",    "msg": "..."}          # fatal : worker exits 1 after this
  {"type": "done",     "success": true/false, "msg": "..."}
"""
import sys
import os
import json
import subprocess
import tempfile
import shutil
import time
import datetime
import uuid as _uuid
from pathlib import Path

# Project root on sys.path so we can reuse core.device_detect
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.device_detect import get_system_disks


# ── Pi 4 package policy ───────────────────────────────────────────────────────

# Always installed on every image regardless of user selection.
# Compatible with linux-aarch64 (mainline) kernel.
_PI4_FORCED_PACKAGES: list[str] = [
    'raspberrypi-bootloader',   # VideoCore firmware files in /boot
    'wireless-regdb',           # WiFi regulatory domain — required for wifi_country
]

# Packages that break or are useless on linux-aarch64 mainline.
# Filtered out of the install list; removed from image if somehow present.
_PI4_INCOMPATIBLE: set[str] = {
    'raspberrypi-eeprom',   # mailbox interface broken on mainline
    'raspberrypi-utils',    # vcgencmd broken on mainline
    'linux-rpi',            # RPi Foundation kernel — different boot chain, breaks U-Boot
    'linux-rpi-headers',    # headers for linux-rpi, wrong for linux-aarch64
}


# ── distro rebranding ─────────────────────────────────────────────────────────

_OS_RELEASE_FIELDS = {
    'NAME':              'XeroPi',
    'PRETTY_NAME':       'XeroPi : Arch Linux ARM for Raspberry Pi 4/400',
    'HOME_URL':          'https://xerolinux.xyz',
    'DOCUMENTATION_URL': 'https://xerolinux.xyz',
    'SUPPORT_URL':       'https://xerolinux.xyz',
    'BUG_REPORT_URL':    'https://xerolinux.xyz',
    'LOGO':              'xeropi',
}

_LSB_RELEASE_FIELDS = {
    'DISTRIB_ID':          'XeroPi',
    'DISTRIB_DESCRIPTION': 'XeroPi : Arch Linux ARM for Raspberry Pi 4/400',
}


def _patch_release_file(path: Path, replacements: dict) -> None:
    """Replace specific KEY="value" lines; leave everything else untouched."""
    if not path.exists():
        return
    lines = path.read_text().splitlines()
    out = []
    for line in lines:
        for key, val in replacements.items():
            if line.startswith(f'{key}='):
                line = f'{key}="{val}"'
                break
        out.append(line)
    path.write_text('\n'.join(out) + '\n')


def _rebrand(root_mnt: str) -> None:
    base = Path(root_mnt) / 'etc'
    _patch_release_file(base / 'os-release',  _OS_RELEASE_FIELDS)
    _patch_release_file(base / 'lsb-release', _LSB_RELEASE_FIELDS)


def _ensure_pacman_arch(base: Path) -> None:
    path = base / 'etc/pacman.conf'
    if not path.exists():
        return
    def t(line):
        s = line.lstrip('# ').lstrip()
        if s.startswith('Architecture'):
            return 'Architecture = aarch64'
        return line
    _sed_lines(path, t)


def _patch_pacman_conf(base: Path) -> None:
    """Uncomment/set misc options in [options] section of pacman.conf."""
    path = base / 'etc/pacman.conf'
    if not path.exists():
        return

    # key → value (None = bare flag, no value)
    want = {
        'Color':                  None,
        'ILoveCandy':             None,
        'VerbosePkgLists':        None,
        'DownloadUser':           'alpm',
        'DisableDownloadTimeout': None,
        'ParallelDownloads':      '25',
    }

    lines = path.read_text().splitlines()
    out = []
    in_options = False
    handled: set = set()

    for line in lines:
        stripped = line.strip()

        if stripped == '[options]':
            in_options = True
            out.append(line)
            continue

        if stripped.startswith('[') and in_options:
            # Leaving [options] — append anything not yet seen
            for key, val in want.items():
                if key not in handled:
                    out.append(f'{key} = {val}' if val else key)
            in_options = False
            out.append(line)
            continue

        if in_options:
            matched = False
            for key, val in want.items():
                s = stripped.lstrip('#').strip()
                if s == key or s.startswith(key + ' ') or s.startswith(key + '='):
                    out.append(f'{key} = {val}' if val else key)
                    handled.add(key)
                    matched = True
                    break
            if not matched:
                out.append(line)
        else:
            out.append(line)

    # [options] was the last section
    if in_options:
        for key, val in want.items():
            if key not in handled:
                out.append(f'{key} = {val}' if val else key)

    path.write_text('\n'.join(out) + '\n')


def _patch_mkinitcpio_conf(base: Path) -> None:
    """Remove aarch64-irrelevant hooks (microcode, kms) to suppress mkinitcpio warnings."""
    path = base / 'etc/mkinitcpio.conf'
    if not path.exists():
        return
    remove = {'microcode', 'kms'}
    lines = path.read_text().splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('HOOKS='):
            # Parse hook list preserving surrounding syntax: HOOKS=(a b c)
            import re as _re
            m = _re.match(r'^(HOOKS=\()(.+)(\).*)$', stripped)
            if m:
                hooks = [h for h in m.group(2).split() if h not in remove]
                out.append(f'{m.group(1)}{" ".join(hooks)}{m.group(3)}')
            else:
                out.append(line)
        else:
            out.append(line)
    path.write_text('\n'.join(out) + '\n')


def _patch_boot_device_refs(root_mnt: str) -> None:
    """Replace hardcoded /dev/mmcblk0pN refs with LABEL= so image boots on any device.

    ALARM aarch64 Pi 4 uses U-Boot with boot.txt/boot.scr — root device is set via
    PARTUUID U-Boot variable, no /dev/ refs to patch there.  This function handles
    cmdline.txt-based setups only; quiet/loglevel patching is done by _patch_quiet_bootargs.
    """
    import re as _re

    for cmdline in [
        Path(root_mnt) / 'boot/cmdline.txt',
        Path(root_mnt) / 'cmdline.txt',
    ]:
        if cmdline.exists():
            text = cmdline.read_text()
            patched = _re.sub(r'root=/dev/\S+', 'root=LABEL=ROOT', text)
            if 'rootwait' not in patched:
                patched = patched.rstrip() + ' rootwait'
            patched = patched.rstrip() + '\n'
            if patched != text:
                cmdline.write_text(patched)
                _log(f'Patched {cmdline.name}: root=LABEL=ROOT rootwait')

    # fstab: Arch ARM tarball hardcodes /dev/mmcblk0p1 (boot) and /dev/mmcblk0p2 (root)
    # Replace both with LABEL= so fstab works on any device type
    fstab = Path(root_mnt) / 'etc/fstab'
    if fstab.exists():
        text = fstab.read_text()
        patched = text
        patched = _re.sub(r'/dev/mmcblk0p1\b', 'LABEL=BOOT', patched)
        patched = _re.sub(r'/dev/mmcblk0p2\b', 'LABEL=ROOT', patched)
        if patched != text:
            fstab.write_text(patched)
            _log('Patched /etc/fstab: replaced mmcblk0pN with LABEL=')


# ── personal-mode configuration helpers ──────────────────────────────────────

def _hash_password(password: str) -> str:
    try:
        r = subprocess.run(
            ['openssl', 'passwd', '-6', password],
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip()
    except Exception:
        try:
            import crypt
            return crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
        except Exception:
            return '!'


def _sed_lines(path: Path, transform) -> None:
    if not path.exists():
        return
    path.write_text('\n'.join(transform(l) for l in path.read_text().splitlines()) + '\n')


def _rename_user_in_passwd(path: Path, old: str, new: str) -> None:
    def t(line):
        if line.startswith(old + ':'):
            return line.replace(old + ':', new + ':', 1).replace(f'/home/{old}', f'/home/{new}')
        return line
    _sed_lines(path, t)


def _rename_user_in_shadow(path: Path, old: str, new: str, pw_hash: str) -> None:
    today = (datetime.date.today() - datetime.date(1970, 1, 1)).days
    def t(line):
        if line.startswith(old + ':'):
            parts = line.split(':')
            parts[0] = new
            parts[1] = pw_hash
            parts[2] = str(today)
            return ':'.join(parts)
        return line
    _sed_lines(path, t)


def _rename_user_in_group(path: Path, old: str, new: str) -> None:
    def t(line):
        parts = line.split(':')
        if len(parts) != 4:
            return line
        if parts[0] == old:
            parts[0] = new
        members = [new if m == old else m for m in parts[3].split(',') if m]
        parts[3] = ','.join(members)
        return ':'.join(parts)
    _sed_lines(path, t)


def _rename_user_in_gshadow(path: Path, old: str, new: str) -> None:
    def t(line):
        parts = line.split(':')
        if len(parts) != 4:
            return line
        if parts[0] == old:
            parts[0] = new
        members = [new if m == old else m for m in parts[3].split(',') if m]
        parts[3] = ','.join(members)
        return ':'.join(parts)
    _sed_lines(path, t)


def _add_user_to_group(path: Path, group: str, username: str) -> None:
    def t(line):
        parts = line.split(':')
        if len(parts) != 4 or parts[0] != group:
            return line
        members = [m for m in parts[3].split(',') if m]
        if username not in members:
            members.append(username)
        parts[3] = ','.join(members)
        return ':'.join(parts)
    _sed_lines(path, t)


def _set_shadow_password(path: Path, username: str, pw_hash: str) -> None:
    today = (datetime.date.today() - datetime.date(1970, 1, 1)).days
    def t(line):
        if line.startswith(username + ':'):
            parts = line.split(':')
            parts[1] = pw_hash
            parts[2] = str(today)
            return ':'.join(parts)
        return line
    _sed_lines(path, t)


def _enable_wheel_sudo(base: Path) -> None:
    # Write a sudoers.d drop-in — survives whether or not sudo is pre-installed in the tarball.
    # sudo reads /etc/sudoers.d/ automatically; drop-in takes effect the moment sudo is installed.
    sudoers_d = base / 'etc/sudoers.d'
    sudoers_d.mkdir(parents=True, exist_ok=True)
    drop_in = sudoers_d / '10-wheel'
    drop_in.write_text('%wheel ALL=(ALL:ALL) ALL\n')
    os.chmod(drop_in, 0o440)

    # Also patch main sudoers if it happens to exist in the tarball
    path = base / 'etc/sudoers'
    if not path.exists():
        return
    def t(line):
        stripped = line.lstrip('# ').lstrip()
        if stripped.startswith('%wheel ALL=(ALL'):
            return stripped
        return line
    _sed_lines(path, t)


def _patch_hosts(base: Path, hostname: str) -> None:
    path = base / 'etc/hosts'
    entry = f'127.0.1.1\t{hostname}.localdomain\t{hostname}'
    if not path.exists():
        path.write_text(f'127.0.0.1\tlocalhost\n::1\t\tlocalhost\n{entry}\n')
        return
    text = path.read_text()
    if '127.0.1.1' in text:
        def t(line):
            return entry if line.startswith('127.0.1.1') else line
        _sed_lines(path, t)
    else:
        path.write_text(text.rstrip() + f'\n{entry}\n')


def _ipv4_section(static: bool, ip: str, prefix: int, gw: str, dns: str) -> str:
    if static and ip and gw:
        return (
            f'[ipv4]\nmethod=manual\n'
            f'address1={ip}/{prefix},{gw}\n'
            f'dns={dns};\n'
        )
    return '[ipv4]\nmethod=auto\n'


def _nm_wifi_keyfile(ssid: str, password: str, country: str,
                     static: bool = False, ip: str = '', prefix: int = 24,
                     gw: str = '', dns: str = '1.1.1.1') -> str:
    conn_id = str(_uuid.uuid4())
    security_section = (
        f'\n[wifi-security]\nkey-mgmt=wpa-psk\npsk={password}\n' if password else ''
    )
    security_ref = '\nsecurity=wpa-psk' if password else ''
    ipv4 = _ipv4_section(static, ip, prefix, gw, dns)
    return (
        f'[connection]\nid={ssid}\nuuid={conn_id}\ntype=wifi\nautoconnect=true\n'
        f'\n[wifi]\nmode=infrastructure\nssid={ssid}{security_ref}\n'
        f'{security_section}'
        f'\n{ipv4}'
        f'\n[ipv6]\naddr-gen-mode=default\nmethod=auto\n'
    )


def _nm_ethernet_keyfile(static: bool, ip: str, prefix: int,
                         gw: str, dns: str) -> str:
    conn_id = str(_uuid.uuid4())
    ipv4 = _ipv4_section(static, ip, prefix, gw, dns)
    return (
        f'[connection]\nid=Ethernet\nuuid={conn_id}\ntype=ethernet\nautoconnect=true\n'
        f'\n[ethernet]\n'
        f'\n{ipv4}'
        f'\n[ipv6]\naddr-gen-mode=default\nmethod=auto\n'
    )


def _enable_services(base: Path, services: list) -> None:
    wants = base / 'etc/systemd/system/multi-user.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    for svc in services:
        name = svc if svc.endswith('.service') else f'{svc}.service'
        link = wants / name
        if not link.exists():
            try:
                # Custom units live in /etc/systemd/system; package units in /usr/lib
                custom = base / 'etc/systemd/system' / name
                target = (f'/etc/systemd/system/{name}' if custom.exists()
                          else f'/usr/lib/systemd/system/{name}')
                link.symlink_to(target)
            except OSError:
                pass


def _write_firstboot_pkg_service(base: Path, packages: list,
                                  post_cmds: list | None = None) -> None:
    if not packages:
        return
    pkg_str = ' '.join(packages)

    auto_cmds: list[str] = list(post_cmds or [])

    # Samba needs manual config before it can usefully run — disable on install,
    # print instructions so the user knows what to do.
    if 'samba' in packages:
        auto_cmds += [
            'if pacman -Q samba >/dev/null 2>&1; then',
            '    systemctl disable smb nmb 2>/dev/null || true',
            '    echo ""',
            '    echo "NOTE: Samba installed but NOT auto-started."',
            '    echo "  Configure /etc/samba/smb.conf then run:"',
            '    echo "  systemctl enable --now smb nmb"',
            'fi',
        ]

    post_block = '\n'.join(auto_cmds) + '\n' if auto_cmds else ''

    script = f'''\
#!/bin/bash
# XeroPi first-boot package installer — runs once, then reboots
# exec MUST be first: redirects all output to tty1 before anything else runs
exec > /dev/tty1 2>&1

clear
echo "============================================"
echo "  XeroPi -- First Boot Setup"
echo "  Setting up your Pi. This happens once."
echo "============================================"
echo ""

# Step 1: network
echo "[ 1/3 ] Waiting for network..."
NET_OK=0
for i in $(seq 1 30); do
    if getent hosts archlinuxarm.org >/dev/null 2>&1; then
        NET_OK=1
        break
    fi
    printf "        attempt %d/30...\\r" "$i"
    sleep 2
done
echo ""
if [[ "$NET_OK" == "0" ]]; then
    echo ""
    echo "ERROR: No network after 60 seconds."
    echo "  Connect Ethernet and reboot to retry."
    echo "  (Setup will run again on next boot.)"
    echo ""
    printf "Press Enter to reboot... "
    read -r -t 60 || true
    systemctl --no-block reboot
    exit 0
fi
echo "        Network: OK"
echo ""

# Step 2: keyring
echo "[ 2/3 ] Initialising pacman keyring (may take 1-2 min)..."
pacman-key --init
pacman-key --populate archlinuxarm
echo "        Keyring: OK"
echo ""

# Remove packages incompatible with linux-aarch64 mainline kernel (if present)
INCOMPAT="raspberrypi-eeprom raspberrypi-utils linux-rpi linux-rpi-headers"
TO_REMOVE=""
for pkg in $INCOMPAT; do
    if pacman -Q "$pkg" >/dev/null 2>&1; then
        TO_REMOVE="$TO_REMOVE $pkg"
    fi
done
if [[ -n "$TO_REMOVE" ]]; then
    echo "Removing incompatible packages:$TO_REMOVE"
    pacman -Rns --noconfirm $TO_REMOVE || true
fi

# Step 3: packages
echo "[ 3/3 ] Installing packages..."
echo "        {pkg_str}"
echo ""
if pacman -Sy --noconfirm {pkg_str}; then
    {post_block}
    rm -f /etc/xeropi-firstboot-pending
    systemctl disable xeropi-firstboot.service 2>/dev/null || true
    rm -f /etc/systemd/system/xeropi-firstboot.service
    rm -f /etc/systemd/system/multi-user.target.wants/xeropi-firstboot.service
    echo ""
    echo "============================================"
    echo "  Setup complete! Rebooting in 5 seconds..."
    echo "============================================"
    sleep 5
else
    echo ""
    echo "ERROR: Package install failed (see above)."
    echo "  Setup will retry on next boot."
    printf "Press Enter to reboot... "
    read -r -t 60 || true
fi
systemctl --no-block reboot
'''

    script_dir = base / 'usr/local/bin'
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / 'xeropi-firstboot.sh'
    script_path.write_text(script)
    os.chmod(script_path, 0o755)

    # No After=network.target — that made the service start too late (or never if
    # no Ethernet on first boot), so getty.target was never held. The script's
    # NET_OK loop handles waiting for connectivity internally.
    svc = (
        '[Unit]\n'
        'Description=XeroPi first-boot package installation\n'
        'Before=getty.target getty@tty1.service\n'
        'Conflicts=getty@tty1.service\n'
        'ConditionPathExists=/etc/xeropi-firstboot-pending\n'
        '\n[Service]\n'
        'Type=oneshot\n'
        'RemainAfterExit=yes\n'
        'ExecStart=/usr/local/bin/xeropi-firstboot.sh\n'
        'StandardOutput=journal\n'
        'StandardError=journal\n'
        '\n[Install]\n'
        'WantedBy=multi-user.target\n'
    )
    (base / 'etc/xeropi-firstboot-pending').write_text(pkg_str + '\n')
    svc_path = base / 'etc/systemd/system/xeropi-firstboot.service'
    svc_path.write_text(svc)
    os.chmod(svc_path, 0o644)
    _enable_services(base, ['xeropi-firstboot'])


def _patch_quiet_bootargs(base: Path) -> None:
    """Add quiet loglevel=3 to kernel boot arguments.

    ALARM aarch64 Pi 4 uses U-Boot: boot args live in boot.txt (setenv bootargs …)
    and must be recompiled into boot.scr via mkimage.  Falls back to cmdline.txt
    for non-U-Boot setups.
    """
    import re as _re

    boot_txt = base / 'boot/boot.txt'
    if boot_txt.exists():
        text = boot_txt.read_text()
        def _add_flags(m: '_re.Match') -> str:
            line = m.group(0)
            if 'quiet' not in line:
                line = line.rstrip() + ' quiet'
            if 'loglevel=' not in line:
                line = line.rstrip() + ' loglevel=3'
            return line
        patched = _re.sub(r'^setenv bootargs .*', _add_flags, text, flags=_re.MULTILINE)
        if patched != text:
            boot_txt.write_text(patched)
            _log('boot.txt: added quiet loglevel=3')
        # Recompile boot.scr — mkimage from uboot-tools required on host
        boot_scr = base / 'boot/boot.scr'
        mkimage = shutil.which('mkimage')
        if not mkimage:
            _log('WARNING: mkimage not found — install uboot-tools on host to recompile boot.scr')
        else:
            r = subprocess.run(
                [mkimage, '-A', 'arm', '-T', 'script', '-C', 'none',
                 '-n', 'Boot Script', '-d', str(boot_txt), str(boot_scr)],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                _log('boot.scr recompiled from boot.txt')
            else:
                _log(f'WARNING: mkimage failed: {r.stderr.strip()}')
        return

    # Fallback: plain cmdline.txt (non-U-Boot targets)
    for _cmdline in [base / 'boot/cmdline.txt', base / 'cmdline.txt']:
        if _cmdline.exists():
            _text = _cmdline.read_text()
            _p = _text
            if 'quiet' not in _p:
                _p = _p.rstrip() + ' quiet'
            if 'loglevel=' not in _p:
                _p = _p.rstrip() + ' loglevel=3'
            _p = _p.rstrip() + '\n'
            if _p != _text:
                _cmdline.write_text(_p)
                _log(f'cmdline.txt: added quiet loglevel=3')


def _apply_always(base: Path) -> None:
    """Items that must run for BOTH personal and distribution modes."""
    # Force headless default target — Arch ARM tarball defaults to graphical.target
    default_target = base / 'etc/systemd/system/default.target'
    default_target.unlink(missing_ok=True)
    try:
        default_target.symlink_to('/usr/lib/systemd/system/multi-user.target')
    except OSError:
        pass

    # Ensure HDMI console login prompt — Arch ARM may not have this enabled by default
    getty_wants = base / 'etc/systemd/system/getty.target.wants'
    getty_wants.mkdir(parents=True, exist_ok=True)
    getty_link = getty_wants / 'getty@tty1.service'
    getty_link.unlink(missing_ok=True)
    try:
        getty_link.symlink_to('/usr/lib/systemd/system/getty@.service')
    except OSError:
        pass

    # Mask NetworkManager-wait-online — blocks boot for ~2 min when no network available
    nm_wait = base / 'etc/systemd/system/NetworkManager-wait-online.service'
    nm_wait.unlink(missing_ok=True)
    try:
        nm_wait.symlink_to('/dev/null')
    except OSError:
        pass

    # Regenerate SSH host keys on first boot
    svc = (
        '[Unit]\n'
        'Description=Regenerate SSH host keys on first boot\n'
        'Before=sshd.service\n'
        'ConditionPathExistsGlob=!/etc/ssh/ssh_host_*_key\n'
        '\n[Service]\n'
        'Type=oneshot\n'
        'RemainAfterExit=yes\n'
        "ExecStart=/bin/bash -c 'ssh-keygen -A && systemctl disable regenerate-ssh-host-keys.service'\n"
        '\n[Install]\n'
        'WantedBy=multi-user.target\n'
    )
    svc_path = base / 'etc/systemd/system/regenerate-ssh-host-keys.service'
    svc_path.write_text(svc)
    os.chmod(svc_path, 0o644)
    _enable_services(base, ['regenerate-ssh-host-keys', 'sshd', 'NetworkManager'])

    # Suppress systemd service status lines on TTY — only show failures
    sysconf_d = base / 'etc/systemd/system.conf.d'
    sysconf_d.mkdir(parents=True, exist_ok=True)
    (sysconf_d / '99-quiet.conf').write_text('[Manager]\nShowStatus=error\n')

    # Suppress kernel printk to console (belt+braces with cmdline loglevel=3)
    sysctl_d = base / 'etc/sysctl.d'
    sysctl_d.mkdir(parents=True, exist_ok=True)
    (sysctl_d / '99-quiet.conf').write_text('kernel.printk = 3 3 3 3\n')

    # Suppress kernel console output: patch boot args + recompile boot.scr (U-Boot),
    # or patch cmdline.txt directly for non-U-Boot setups.
    _patch_quiet_bootargs(base)

    # Empty machine-id so systemd regenerates it on first boot
    mid = base / 'etc/machine-id'
    mid.write_text('')


def _configure_personal(root_mnt: str, cfg: dict) -> list:
    base         = Path(root_mnt)
    username     = cfg.get('username', '').strip()
    password     = cfg.get('password', '')
    hostname     = cfg.get('hostname', '').strip()
    ssh_key      = cfg.get('ssh_key', '').strip()
    wheel        = cfg.get('wheel', False)
    wifi_ssid    = cfg.get('wifi_ssid', '').strip()
    wifi_pass    = cfg.get('wifi_password', '')
    wifi_country = cfg.get('wifi_country', 'US').strip().upper()
    use_static   = cfg.get('use_static_ip', False)
    static_ip    = cfg.get('static_ip', '').strip()
    static_pfx   = int(cfg.get('static_prefix', 24))
    static_gw    = cfg.get('static_gateway', '').strip()
    static_dns   = cfg.get('static_dns', '1.1.1.1').strip()
    use_eth_static = cfg.get('use_eth_static_ip', False)
    eth_ip       = cfg.get('eth_static_ip', '').strip()
    eth_pfx      = int(cfg.get('eth_static_prefix', 24))
    eth_gw       = cfg.get('eth_static_gateway', '').strip()
    eth_dns      = cfg.get('eth_static_dns', '1.1.1.1').strip()
    packages     = cfg.get('packages', [])

    if hostname:
        _log(f'Setting hostname: {hostname}')
        (base / 'etc/hostname').write_text(hostname + '\n')
        _patch_hosts(base, hostname)

    root_same_password = cfg.get('root_same_password', False)

    if username:
        _log(f'Configuring user: {username}')
        pw_hash = _hash_password(password) if password else '!'
        # Rename default 'alarm' user to desired username
        _rename_user_in_passwd  (base / 'etc/passwd',   'alarm', username)
        _rename_user_in_shadow  (base / 'etc/shadow',   'alarm', username, pw_hash)
        _rename_user_in_group   (base / 'etc/group',    'alarm', username)
        _rename_user_in_gshadow (base / 'etc/gshadow',  'alarm', username)

        if root_same_password and password:
            _log('Setting root password to match user password')
            _set_shadow_password(base / 'etc/shadow', 'root', pw_hash)

        # Rename home directory
        old_home = base / 'home/alarm'
        new_home = base / f'home/{username}'
        if old_home.exists() and not new_home.exists():
            old_home.rename(new_home)
        new_home.mkdir(parents=True, exist_ok=True)
        os.chown(new_home, 1000, 1000)
        os.chmod(new_home, 0o700)

        if wheel:
            _log('Adding user to wheel group, enabling sudo')
            _add_user_to_group(base / 'etc/group', 'wheel', username)
            _enable_wheel_sudo(base)

        if ssh_key:
            _log('Installing SSH authorized key')
            ssh_dir = new_home / '.ssh'
            ssh_dir.mkdir(exist_ok=True)
            os.chown(ssh_dir, 1000, 1000)
            os.chmod(ssh_dir, 0o700)
            ak = ssh_dir / 'authorized_keys'
            ak.write_text(ssh_key + '\n')
            os.chown(ak, 1000, 1000)
            os.chmod(ak, 0o600)

    nm_dir = base / 'etc/NetworkManager/system-connections'
    nm_dir.mkdir(parents=True, exist_ok=True)

    if wifi_ssid:
        _log(f'Configuring WiFi SSID: {wifi_ssid}')
        conn = nm_dir / f'{wifi_ssid}.nmconnection'
        conn.write_text(_nm_wifi_keyfile(
            wifi_ssid, wifi_pass, wifi_country,
            static=use_static, ip=static_ip, prefix=static_pfx,
            gw=static_gw, dns=static_dns,
        ))
        os.chmod(conn, 0o600)

    if use_eth_static and eth_ip and eth_gw:
        _log(f'Writing static Ethernet profile: {eth_ip}/{eth_pfx}')
        eth = nm_dir / 'Ethernet.nmconnection'
        eth.write_text(_nm_ethernet_keyfile(True, eth_ip, eth_pfx, eth_gw, eth_dns))
        os.chmod(eth, 0o600)

    # Enable base services + any package-dependent ones
    # (symlinks created now; dangling until package installs on first boot — systemd resolves at runtime)
    always_on = []
    svc_map = {
        'docker':    'docker',
        'tailscale': 'tailscaled',
        'fail2ban':  'fail2ban',
        'cronie':    'cronie',
        'avahi':     'avahi-daemon',
        'samba':     'smb',
    }
    for pkg, svc in svc_map.items():
        if pkg in packages:
            always_on.append(svc)
    _enable_services(base, always_on)
    _log(f'Enabled services: {", ".join(always_on)}')

    # Post-firstboot commands: run after pacman installs packages
    post_cmds = []
    if 'docker' in packages and username:
        post_cmds.append(f'usermod -aG docker {username}')
    return post_cmds


# ── distribution-mode helpers ─────────────────────────────────────────────────

def _purify(base: Path) -> None:
    """Strip all credentials and machine identity for distribution."""
    ssh_dir = base / 'etc/ssh'
    if ssh_dir.exists():
        for key in ssh_dir.glob('ssh_host_*'):
            key.unlink(missing_ok=True)

    (base / 'etc/machine-id').write_text('')

    log_dir = base / 'var/log'
    if log_dir.exists():
        for f in log_dir.rglob('*'):
            if f.is_file():
                try:
                    f.write_text('')
                except OSError:
                    pass
        journal = log_dir / 'journal'
        if journal.exists():
            shutil.rmtree(journal, ignore_errors=True)
            journal.mkdir(exist_ok=True)

    pkg_cache = base / 'var/cache/pacman/pkg'
    if pkg_cache.exists():
        shutil.rmtree(pkg_cache, ignore_errors=True)
        pkg_cache.mkdir(parents=True, exist_ok=True)

    for hist in [
        base / 'root/.bash_history',
        base / 'root/.zsh_history',
        base / 'home/alarm/.bash_history',
        base / 'home/alarm/.zsh_history',
    ]:
        hist.unlink(missing_ok=True)

    for lease_dir in [base / 'var/lib/dhcpcd', base / 'var/lib/dhcp']:
        if lease_dir.exists():
            for f in lease_dir.iterdir():
                if f.is_file():
                    f.unlink(missing_ok=True)

    nm_state = base / 'var/lib/NetworkManager'
    if nm_state.exists():
        shutil.rmtree(nm_state, ignore_errors=True)
        nm_state.mkdir(parents=True, exist_ok=True)

    nm_conn = base / 'etc/NetworkManager/system-connections'
    if nm_conn.exists():
        for f in nm_conn.iterdir():
            if f.is_file():
                f.unlink()


def _write_dist_setup_script(base: Path, cfg: dict) -> None:
    ask_hostname = '1' if cfg.get('dist_ask_hostname', True) else '0'
    ask_user     = '1' if cfg.get('dist_ask_user',     True) else '0'
    ask_wheel    = '1' if cfg.get('dist_ask_wheel',    True) else '0'
    ask_ssh_key  = '1' if cfg.get('dist_ask_ssh_key',  True) else '0'
    ask_wifi     = '1' if cfg.get('dist_ask_wifi',     True) else '0'
    ask_static   = '1' if cfg.get('use_static_ip',     False) else '0'
    all_pkgs = (
        cfg.get('packages', [])
        + cfg.get('user_added_packages', [])
        + [p for p in cfg.get('extra_packages', '').split() if p]
    )
    default_pkgs = ' '.join(all_pkgs)

    lines = [
        '#!/bin/bash',
        '# XeroPi Distribution First-Boot Setup Wizard',
        'set -e',
        'exec > /dev/tty1 < /dev/tty1 2>&1',
        '',
        f'ASK_HOSTNAME="{ask_hostname}"',
        f'ASK_USER="{ask_user}"',
        f'ASK_WHEEL="{ask_wheel}"',
        f'ASK_SSH_KEY="{ask_ssh_key}"',
        f'ASK_WIFI="{ask_wifi}"',
        f'ASK_STATIC="{ask_static}"',
        f'DEFAULT_PKGS="{default_pkgs}"',
        '',
        'clear',
        'echo "============================================"',
        'echo "  XeroPi First-Boot Setup"',
        'echo "============================================"',
        'echo ""',
        '',
        '# Hostname',
        'HOSTNAME_VAL="alarmpi"',
        'if [[ "$ASK_HOSTNAME" == "1" ]]; then',
        '    printf "Enter hostname [alarmpi]: "',
        '    read HOSTNAME_VAL',
        '    HOSTNAME_VAL="${HOSTNAME_VAL:-alarmpi}"',
        '    echo "$HOSTNAME_VAL" > /etc/hostname',
        '    if grep -q "127\\.0\\.1\\.1" /etc/hosts; then',
        r'        sed -i "s/127\.0\.1\.1.*/127.0.1.1\t${HOSTNAME_VAL}.localdomain\t${HOSTNAME_VAL}/" /etc/hosts',
        '    else',
        r'        printf "127.0.1.1\t%s.localdomain\t%s\n" "$HOSTNAME_VAL" "$HOSTNAME_VAL" >> /etc/hosts',
        '    fi',
        '    hostnamectl set-hostname "$HOSTNAME_VAL" 2>/dev/null || true',
        '    echo "  Hostname: $HOSTNAME_VAL"',
        'fi',
        '',
        '# User account',
        'NEW_USER=""',
        'if [[ "$ASK_USER" == "1" ]]; then',
        '    echo ""',
        '    while true; do',
        '        printf "Enter username: "',
        '        read NEW_USER',
        '        [[ -n "$NEW_USER" ]] && break',
        '        echo "Username cannot be empty."',
        '    done',
        '    useradd -m -s /bin/bash "$NEW_USER" 2>/dev/null || true',
        '    echo "Set password for $NEW_USER:"',
        '    while ! passwd "$NEW_USER"; do echo "Try again."; done',
        '    if [[ "$ASK_WHEEL" == "1" ]]; then',
        '        echo ""',
        '        printf "Add %s to wheel group (sudo)? [y/N]: " "$NEW_USER"',
        '        read ADD_WHEEL',
        '        if [[ "$ADD_WHEEL" =~ ^[Yy] ]]; then',
        '            usermod -aG wheel "$NEW_USER"',
        '            grep -q "^%wheel" /etc/sudoers || echo "%wheel ALL=(ALL:ALL) ALL" >> /etc/sudoers',
        '            echo "  Added $NEW_USER to wheel."',
        '        fi',
        '    fi',
        '    if [[ "$ASK_SSH_KEY" == "1" ]]; then',
        '        echo ""',
        '        printf "Paste SSH public key (Enter to skip): "',
        '        read SSH_PUB_KEY',
        '        if [[ -n "$SSH_PUB_KEY" ]]; then',
        '            SSH_DIR="/home/$NEW_USER/.ssh"',
        '            mkdir -p "$SSH_DIR"',
        '            echo "$SSH_PUB_KEY" >> "$SSH_DIR/authorized_keys"',
        '            chown -R "$NEW_USER:$NEW_USER" "$SSH_DIR"',
        '            chmod 700 "$SSH_DIR" && chmod 600 "$SSH_DIR/authorized_keys"',
        '            echo "  SSH key installed."',
        '        fi',
        '    fi',
        '    usermod -L alarm 2>/dev/null || true',
        '    usermod -s /usr/bin/nologin alarm 2>/dev/null || true',
        'fi',
        '',
        '# WiFi',
        'if [[ "$ASK_WIFI" == "1" ]]; then',
        '    echo ""',
        '    printf "Configure WiFi? [y/N]: "',
        '    read CONF_WIFI',
        '    if [[ "$CONF_WIFI" =~ ^[Yy] ]]; then',
        '        printf "SSID: "',
        '        read WIFI_SSID',
        '        printf "Password (blank for open): "',
        '        read -s WIFI_PASS',
        '        echo ""',
        '        printf "Country code [US]: "',
        '        read WIFI_COUNTRY',
        '        WIFI_COUNTRY="${WIFI_COUNTRY:-US}"',
        '        NM_DIR="/etc/NetworkManager/system-connections"',
        '        mkdir -p "$NM_DIR"',
        '        CONN_UUID=$(cat /proc/sys/kernel/random/uuid)',
        '        CONN_FILE="$NM_DIR/${WIFI_SSID}.nmconnection"',
        '        {',
        '            echo "[connection]"',
        '            echo "id=${WIFI_SSID}"',
        '            echo "uuid=${CONN_UUID}"',
        '            echo "type=wifi"',
        '            echo "autoconnect=true"',
        '            echo ""',
        '            echo "[wifi]"',
        '            echo "mode=infrastructure"',
        '            echo "ssid=${WIFI_SSID}"',
        '            if [[ -n "$WIFI_PASS" ]]; then',
        '                echo "security=wpa-psk"',
        '                echo ""',
        '                echo "[wifi-security]"',
        '                echo "key-mgmt=wpa-psk"',
        '                echo "psk=${WIFI_PASS}"',
        '            fi',
        '            echo ""',
        '            echo "[ipv4]"',
        '            echo "method=auto"',
        '            echo ""',
        '            echo "[ipv6]"',
        '            echo "addr-gen-mode=default"',
        '            echo "method=auto"',
        '        } > "$CONN_FILE"',
        '        chmod 600 "$CONN_FILE"',
        '        echo "  WiFi profile written."',
        '    fi',
        'fi',
        '',
        '# Static IP',
        'if [[ "$ASK_STATIC" == "1" ]]; then',
        '    echo ""',
        '    printf "Configure static IP? [y/N]: "',
        '    read CONF_STATIC',
        '    if [[ "$CONF_STATIC" =~ ^[Yy] ]]; then',
        '        printf "IP address (e.g. 192.168.1.100): "',
        '        read SIP',
        '        printf "Prefix length [24]: "',
        '        read SPFX',
        '        SPFX="${SPFX:-24}"',
        '        printf "Gateway: "',
        '        read SGW',
        '        printf "DNS server [1.1.1.1]: "',
        '        read SDNS',
        '        SDNS="${SDNS:-1.1.1.1}"',
        '        NM_DIR="/etc/NetworkManager/system-connections"',
        '        mkdir -p "$NM_DIR"',
        '        ETH_UUID=$(cat /proc/sys/kernel/random/uuid)',
        '        {',
        '            echo "[connection]"',
        '            echo "id=Ethernet"',
        '            echo "uuid=${ETH_UUID}"',
        '            echo "type=ethernet"',
        '            echo "autoconnect=true"',
        '            echo ""',
        '            echo "[ethernet]"',
        '            echo ""',
        '            echo "[ipv4]"',
        '            echo "method=manual"',
        '            echo "address1=${SIP}/${SPFX},${SGW}"',
        '            echo "dns=${SDNS};"',
        '            echo ""',
        '            echo "[ipv6]"',
        '            echo "addr-gen-mode=default"',
        '            echo "method=auto"',
        '        } > "$NM_DIR/Ethernet.nmconnection"',
        '        chmod 600 "$NM_DIR/Ethernet.nmconnection"',
        '        echo "  Static IP profile written."',
        '    fi',
        'fi',
        '',
        '# Packages',
        'if [[ -n "$DEFAULT_PKGS" ]]; then',
        '    echo ""',
        '    echo "Default packages: $DEFAULT_PKGS"',
        '    printf "Install these packages? [Y/n]: "',
        '    read INST_PKGS',
        '    if [[ ! "$INST_PKGS" =~ ^[Nn] ]]; then',
        '        printf "Extra packages to add (space-separated, Enter to skip): "',
        '        read EXTRA_PKGS',
        '        echo "Initializing pacman keyring..."',
        '        pacman-key --init',
        '        pacman-key --populate archlinuxarm',
        '        echo "Installing packages (requires internet)..."',
        '        # shellcheck disable=SC2086',
        '        pacman -Sy --noconfirm $DEFAULT_PKGS $EXTRA_PKGS || echo "Warning: some packages failed."',
        '        if pacman -Qq docker &>/dev/null && [[ -n "$NEW_USER" ]]; then',
        '            usermod -aG docker "$NEW_USER"',
        '            echo "  Added $NEW_USER to docker group."',
        '        fi',
        '        if pacman -Qq tailscale &>/dev/null; then',
        '            systemctl enable --now tailscaled 2>/dev/null || true',
        '            echo "  Tailscale service enabled."',
        '        fi',
        '    fi',
        'fi',
        'rm -f /etc/xeropi-firstboot-pending',
        '',
        '# Done',
        'echo ""',
        'echo "============================================"',
        'echo "  Setup complete!"',
        'echo "============================================"',
        '[[ -n "$NEW_USER" ]] && echo "  User     : $NEW_USER"',
        '[[ "$HOSTNAME_VAL" != "alarmpi" ]] && echo "  Hostname : $HOSTNAME_VAL"',
        'echo ""',
        'systemctl disable xeropi-distsetup.service 2>/dev/null || true',
        'rm -f /etc/systemd/system/xeropi-distsetup.service',
        'rm -f /usr/local/bin/xeropi-setup.sh',
        'echo "Rebooting in 10 seconds (Ctrl+C to cancel)..."',
        'sleep 10',
        'reboot',
    ]

    script_dir = base / 'usr/local/bin'
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / 'xeropi-setup.sh'
    script_path.write_text('\n'.join(lines) + '\n')
    os.chmod(script_path, 0o755)


def _write_dist_setup_service(base: Path) -> None:
    svc = (
        '[Unit]\n'
        'Description=XeroPi Distribution First-Boot Setup Wizard\n'
        'DefaultDependencies=no\n'
        'After=local-fs.target systemd-remount-fs.service\n'
        'Before=network.target getty.target\n'
        'ConditionPathExists=/usr/local/bin/xeropi-setup.sh\n'
        '\n[Service]\n'
        'Type=oneshot\n'
        'RemainAfterExit=yes\n'
        'ExecStart=/usr/local/bin/xeropi-setup.sh\n'
        'StandardInput=tty\n'
        'StandardOutput=tty\n'
        'StandardError=tty\n'
        'TTYPath=/dev/tty1\n'
        'TTYReset=yes\n'
        'TTYVHangup=yes\n'
        'TTYVTDisallocate=yes\n'
        '\n[Install]\n'
        'WantedBy=multi-user.target\n'
    )
    svc_path = base / 'etc/systemd/system/xeropi-distsetup.service'
    svc_path.write_text(svc)
    os.chmod(svc_path, 0o644)
    _enable_services(base, ['xeropi-distsetup'])


def _write_autoexpand_service(base: Path) -> None:
    """Write a firstboot service that expands root partition to fill the drive."""
    script = '\n'.join([
        '#!/bin/bash',
        'set -e',
        'ROOT_DEV=$(findmnt -n -o SOURCE /)',
        'DISK=$(lsblk -no PKNAME "$ROOT_DEV")',
        'PARTNUM=$(cat "/sys/class/block/$(basename "$ROOT_DEV")/partition")',
        'parted -s "/dev/$DISK" resizepart "$PARTNUM" 100%',
        'resize2fs "$ROOT_DEV"',
        'systemctl disable xeropi-autoexpand.service 2>/dev/null || true',
        'rm -f /etc/systemd/system/xeropi-autoexpand.service',
        'rm -f /usr/local/bin/xeropi-autoexpand.sh',
    ]) + '\n'

    script_dir = base / 'usr/local/bin'
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / 'xeropi-autoexpand.sh'
    script_path.write_text(script)
    os.chmod(script_path, 0o755)

    svc = (
        '[Unit]\n'
        'Description=XeroPi auto-expand root partition on first boot\n'
        'DefaultDependencies=no\n'
        'After=local-fs-pre.target\n'
        'Before=local-fs.target\n'
        'ConditionPathExists=/usr/local/bin/xeropi-autoexpand.sh\n'
        '\n[Service]\n'
        'Type=oneshot\n'
        'RemainAfterExit=yes\n'
        'ExecStart=/usr/local/bin/xeropi-autoexpand.sh\n'
        '\n[Install]\n'
        'WantedBy=local-fs.target\n'
    )
    svc_path = base / 'etc/systemd/system/xeropi-autoexpand.service'
    svc_path.write_text(svc)
    os.chmod(svc_path, 0o644)
    # Enable in local-fs.target.wants (runs very early, before network)
    wants = base / 'etc/systemd/system/local-fs.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    link = wants / 'xeropi-autoexpand.service'
    if not link.exists():
        try:
            link.symlink_to('/etc/systemd/system/xeropi-autoexpand.service')
        except OSError:
            pass



def _create_dist_image(root_mnt: str, boot_mnt: str, output_path: str) -> None:
    """Create shrunk .img.xz for distribution. root_mnt and boot_mnt must still be mounted."""
    import re as _re

    if output_path.endswith('.img.xz'):
        xz_path = output_path
        img_path = output_path[:-3]
    elif output_path.endswith('.img'):
        img_path = output_path
        xz_path  = output_path + '.xz'
    else:
        img_path = output_path + '.img'
        xz_path  = img_path   + '.xz'

    # Estimate size from actual used bytes
    du_root = subprocess.run(['du', '-sb', '--exclude=' + boot_mnt, root_mnt],
                             capture_output=True, text=True)
    du_boot = subprocess.run(['du', '-sb', boot_mnt], capture_output=True, text=True)
    root_used = int(du_root.stdout.split()[0]) if du_root.returncode == 0 else 2 * 1024**3
    _boot_used = int(du_boot.stdout.split()[0]) if du_boot.returncode == 0 else 512 * 1024**2

    BOOT_MIB = 2049
    root_mib  = max(512, int(root_used * 1.35 / (1024**2)) + 256)
    total_mib = BOOT_MIB + root_mib + 4

    _log(f'Creating {total_mib} MiB image file at {img_path}…')
    subprocess.run(['truncate', '-s', f'{total_mib}M', img_path], check=True, capture_output=True)

    lo = subprocess.run(
        ['losetup', '--find', '--show', '--partscan', img_path],
        capture_output=True, text=True, check=True,
    )
    loop_dev = lo.stdout.strip()
    _log(f'Loop device: {loop_dev}')

    new_total_mib = total_mib

    try:
        subprocess.run([
            'parted', '-s', loop_dev,
            'mklabel', 'msdos',
            'mkpart', 'primary', 'fat32', '1MiB', '2049MiB',
            'set', '1', 'boot', 'on',
            'mkpart', 'primary', 'ext4', '2049MiB', '100%',
        ], check=True, capture_output=True)
        subprocess.run(['partprobe', loop_dev], capture_output=True)
        time.sleep(1)

        lp1 = _part(loop_dev, 1)
        lp2 = _part(loop_dev, 2)
        for _ in range(20):
            if os.path.exists(lp1) and os.path.exists(lp2):
                break
            time.sleep(0.25)

        subprocess.run(['mkfs.vfat', '-F', '32', '-n', 'BOOT', lp1], check=True, capture_output=True)
        subprocess.run(['mkfs.ext4', '-F', '-L', 'ROOT', lp2], check=True, capture_output=True)

        img_root = tempfile.mkdtemp(prefix='xeropi4-imgroot-')
        img_boot = os.path.join(img_root, 'boot')
        subprocess.run(['mount', lp2, img_root], check=True, capture_output=True)
        os.makedirs(img_boot, exist_ok=True)
        subprocess.run(['mount', lp1, img_boot], check=True, capture_output=True)

        try:
            _log('Copying rootfs to image (rsync)…')
            r = subprocess.run([
                'rsync', '-aAX', '--one-file-system', '--exclude=/boot',
                f'{root_mnt}/', f'{img_root}/',
            ], capture_output=True, text=True)
            if r.returncode not in (0, 24):  # 24 = vanished files (harmless)
                _log(f'rsync rootfs stderr: {r.stderr.strip()[-400:]}')
                raise subprocess.CalledProcessError(r.returncode, 'rsync rootfs')
            _log('Copying boot partition to image (rsync)…')
            r2 = subprocess.run([
                'rsync', '-rlt', '--ignore-missing-args',
                f'{boot_mnt}/', f'{img_boot}/',
            ], capture_output=True, text=True)
            # 23 = partial transfer (includes vanished files); 24 = pure vanished — both OK for boot
            if r2.returncode not in (0, 23, 24):
                _log(f'rsync boot stderr: {r2.stderr.strip()[-400:]}')
                raise subprocess.CalledProcessError(r2.returncode, 'rsync boot')
        finally:
            subprocess.run(['umount', '-lf', img_boot], capture_output=True)
            subprocess.run(['umount', '-lf', img_root],  capture_output=True)
            shutil.rmtree(img_root, ignore_errors=True)

        # Shrink root filesystem to minimum
        _log('Shrinking root filesystem (e2fsck + resize2fs)…')
        subprocess.run(['e2fsck', '-f', '-y', lp2], capture_output=True)
        subprocess.run(['resize2fs', '-M', lp2], check=True, capture_output=True)

        # Calculate actual new size and truncate
        info = subprocess.run(['resize2fs', '-P', lp2], capture_output=True, text=True)
        m = _re.search(r':\s*(\d+)', info.stdout)
        if m:
            min_blocks = int(m.group(1))
            tl = subprocess.run(['tune2fs', '-l', lp2], capture_output=True, text=True)
            bsm = _re.search(r'Block size:\s+(\d+)', tl.stdout)
            block_size = int(bsm.group(1)) if bsm else 4096
            new_root_bytes  = min_blocks * block_size + 32 * 1024 * 1024  # 32 MiB pad
            new_root_blocks = (new_root_bytes + block_size - 1) // block_size
            subprocess.run(['resize2fs', lp2, str(new_root_blocks)], capture_output=True)
            new_root_mib  = (new_root_bytes + 1024 * 1024 - 1) // (1024 * 1024)
            new_total_mib = BOOT_MIB + new_root_mib + 4
            subprocess.run([
                'parted', '-s', loop_dev,
                'resizepart', '2', f'{new_total_mib - 1}MiB',
            ], capture_output=True)

    finally:
        subprocess.run(['losetup', '-d', loop_dev], capture_output=True)

    # Truncate image to actual used size then compress
    if new_total_mib < total_mib:
        subprocess.run(['truncate', '-s', f'{new_total_mib}M', img_path],
                       check=True, capture_output=True)

    _log(f'Compressing image with xz (this may take several minutes)…')
    subprocess.run(['xz', '--threads=0', '-9', img_path], check=True)
    _log(f'Distribution image ready: {xz_path}')


# ── output helpers ────────────────────────────────────────────────────────────

def _out(type_: str, msg: str = '', **kw) -> None:
    print(json.dumps({'type': type_, 'msg': msg, **kw}), flush=True)

def _log(msg: str)          -> None: _out('log',      msg)
def _progress(pct, msg='')  -> None: _out('progress', msg, pct=pct)
def _fatal(msg: str)        -> None:
    _out('error', msg)
    sys.exit(1)


# ── partition naming ──────────────────────────────────────────────────────────

def _part(dev: str, n: int) -> str:
    """Return partition device path. /dev/sdb→sdb1, /dev/mmcblk0→mmcblk0p1."""
    base = dev.removeprefix('/dev/')
    if base.startswith(('mmcblk', 'nvme', 'loop')):
        return f'/dev/{base}p{n}'
    return f'/dev/{base}{n}'


# ── subprocess helper ─────────────────────────────────────────────────────────

def _run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if os.geteuid() != 0:
        _fatal('flash_worker must run as root (use pkexec).')

    if len(sys.argv) < 2:
        _fatal('Usage: flash_worker.py <config.json>')

    cfg_path = Path(sys.argv[1])
    if not cfg_path.exists():
        _fatal(f'Config file not found: {cfg_path}')

    try:
        cfg = json.loads(cfg_path.read_text())
    except Exception as e:
        _fatal(f'Cannot read config: {e}')

    target     = cfg.get('target_dev', '')
    tarball    = cfg.get('tarball_path', '')
    flash_mode = cfg.get('flash_mode', 'build')

    # ── Direct image flash (flash_image mode) ─────────────────────────────────
    if flash_mode == 'flash_image':
        flash_image_path = cfg.get('flash_image_path', '').strip()
        if not flash_image_path or not Path(flash_image_path).exists():
            _fatal(f'Image file not found: {flash_image_path}')
        if not target:
            _fatal('No target device specified for image flash.')

        _log(f'Verifying {target} is not a system disk…')
        try:
            system_disks = get_system_disks()
        except RuntimeError as e:
            _fatal(f'System disk detection failed: {e}')
        if target.removeprefix('/dev/') in system_disks:
            _fatal(f'SAFETY BLOCK: {target} is the system disk. Refusing to write.')
        _progress(5, 'Safety check passed.')

        _log(f'Unmounting partitions on {target}…')
        try:
            for line in Path('/proc/mounts').read_text().splitlines():
                cols = line.split()
                if len(cols) >= 2 and cols[0].startswith(target):
                    r = subprocess.run(['umount', '-f', cols[1]], capture_output=True)
                    if r.returncode == 0:
                        _log(f'  Unmounted {cols[1]}')
        except OSError:
            pass

        try:
            size_bytes = Path(flash_image_path).stat().st_size
            size_str = (f'{size_bytes / 1024**3:.1f} GB' if size_bytes > 1024**3
                        else f'{size_bytes / 1024**2:.0f} MB')
            _log(f'Image size: {size_str}')
        except Exception:
            pass

        _progress(10, f'Writing image to {target} (this may take several minutes)…')
        _log(f'Source: {flash_image_path}')

        try:
            if flash_image_path.endswith('.img.xz'):
                _log('Decompressing .img.xz on the fly and writing to device…')
                xz_proc = subprocess.Popen(
                    ['xz', '-d', '--stdout', flash_image_path],
                    stdout=subprocess.PIPE,
                )
                dd_proc = subprocess.Popen(
                    ['dd', f'of={target}', 'bs=4M', 'conv=fsync', 'status=none'],
                    stdin=xz_proc.stdout,
                )
                xz_proc.stdout.close()
                dd_rc = dd_proc.wait()
                xz_rc = xz_proc.wait()
                if xz_rc != 0 or dd_rc != 0:
                    _fatal(f'Image write failed (xz exit={xz_rc}, dd exit={dd_rc})')
            else:
                _log(f'Writing image with dd…')
                r = subprocess.run(
                    ['dd', f'if={flash_image_path}', f'of={target}',
                     'bs=4M', 'conv=fsync', 'status=none'],
                    capture_output=True,
                )
                if r.returncode != 0:
                    _fatal(f'dd failed: {r.stderr.decode().strip()}')
        except Exception as e:
            _fatal(str(e))

        _progress(95, 'Syncing…')
        subprocess.run(['sync'], check=True)
        _progress(100, 'Done.')
        _out('done', success=True, msg=f'Image flashed to {target} successfully.')
        return

    if not tarball or not Path(tarball).exists():
        _fatal(f'Tarball not found: {tarball}')

    # ── Image-only build (dist mode, no physical device) ─────────────────────
    if not target:
        output_path = cfg.get('shrink_output_path', '').strip()
        if not output_path:
            _fatal('shrink_output_path required for image-only build.')

        _progress(5, 'Image-only build — no device flash.')

        root_mnt = tempfile.mkdtemp(prefix='xeropi4-root-')
        boot_mnt = os.path.join(root_mnt, 'boot')
        os.makedirs(boot_mnt, exist_ok=True)

        def _cleanup_img():
            shutil.rmtree(root_mnt, ignore_errors=True)

        try:
            _progress(10, 'Extracting rootfs (this may take several minutes)…')
            _log(f'bsdtar -xpf {tarball} -C {root_mnt}')
            proc = subprocess.run(
                ['bsdtar', '-xpf', tarball, '-C', root_mnt],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                _cleanup_img()
                _fatal(f'bsdtar extraction failed: {proc.stderr.strip()}')

            _progress(72, 'Rebranding OS release files…')
            _rebrand(root_mnt)
            _ensure_pacman_arch(Path(root_mnt))
            _patch_pacman_conf(Path(root_mnt))
            _patch_mkinitcpio_conf(Path(root_mnt))
            if cfg.get('target_bus_type', '') != 'SD card':
                _log('Non-SD target: patching cmdline.txt + fstab to use LABEL= refs…')
                _patch_boot_device_refs(root_mnt)

            _progress(74, 'Applying always-on configuration…')
            _apply_always(Path(root_mnt))

            _progress(76, 'Purifying distribution image…')
            _purify(Path(root_mnt))

            _progress(78, 'Writing interactive first-boot setup wizard…')
            _write_dist_setup_script(Path(root_mnt), cfg)
            _write_dist_setup_service(Path(root_mnt))

            all_pkgs = (
                cfg.get('packages', [])
                + cfg.get('user_added_packages', [])
                + [p for p in cfg.get('extra_packages', '').split() if p]
            )
            if all_pkgs:
                (Path(root_mnt) / 'etc/xeropi-firstboot-pending').write_text(
                    ' '.join(all_pkgs) + '\n'
                )

            _progress(80, 'Writing auto-expand service…')
            _write_autoexpand_service(Path(root_mnt))

            _progress(82, 'Creating distribution image (this will take a while)…')
            _create_dist_image(root_mnt, boot_mnt, output_path)

        except Exception as e:
            _cleanup_img()
            _fatal(str(e))

        _cleanup_img()
        xz_path = output_path if output_path.endswith('.img.xz') else output_path + '.img.xz'
        _progress(100, 'Done.')
        _out('done', success=True, msg=f'Distribution image saved to {xz_path}.')
        return

    # ── safety: re-verify target is not a system disk ─────────────────────────
    _log(f'Verifying {target} is not a system disk…')
    try:
        system_disks = get_system_disks()
    except RuntimeError as e:
        _fatal(f'System disk detection failed: {e}')

    devname = target.removeprefix('/dev/')
    if devname in system_disks:
        _fatal(f'SAFETY BLOCK: {target} is the system disk. Refusing to write.')

    _progress(2, 'Safety check passed.')

    # ── unmount all partitions on target ──────────────────────────────────────
    _log(f'Unmounting partitions on {target}…')
    try:
        mounts = Path('/proc/mounts').read_text()
        for line in mounts.splitlines():
            cols = line.split()
            if len(cols) < 2:
                continue
            dev, mnt = cols[0], cols[1]
            if dev.startswith(target):
                result = subprocess.run(['umount', '-f', mnt], capture_output=True)
                if result.returncode == 0:
                    _log(f'  Unmounted {mnt}')
    except OSError:
        pass

    _progress(5, f'Wiping {target}…')

    # ── wipe existing partition signatures ────────────────────────────────────
    try:
        _run(['wipefs', '-a', target])
    except subprocess.CalledProcessError as e:
        _fatal(f'wipefs failed: {e.stderr.strip()}')

    # ── partition: msdos, 200 MiB FAT32 boot + remaining ext4 root ───────────
    _progress(8, 'Creating partition table…')
    _log('Partitioning: msdos / 2048 MiB FAT32 boot + ext4 root…')
    try:
        _run([
            'parted', '-s', target,
            'mklabel', 'msdos',
            'mkpart', 'primary', 'fat32', '1MiB', '2049MiB',
            'set', '1', 'boot', 'on',
            'mkpart', 'primary', 'ext4', '2049MiB', '100%',
        ])
    except subprocess.CalledProcessError as e:
        _fatal(f'parted failed: {e.stderr.strip()}')

    subprocess.run(['partprobe', target], capture_output=True)
    subprocess.run(['udevadm', 'settle', '--timeout=10'], capture_output=True)

    p1 = _part(target, 1)
    p2 = _part(target, 2)

    # Wait for partition nodes to appear (udevadm settle may return early)
    for _ in range(20):
        if os.path.exists(p1) and os.path.exists(p2):
            break
        time.sleep(0.25)
    else:
        _fatal(f'Partition devices {p1} / {p2} did not appear after 5 s.')

    # ── format ────────────────────────────────────────────────────────────────
    _progress(12, f'Formatting {p1} as FAT32…')
    _log(f'mkfs.vfat -F 32 -n BOOT {p1}')
    try:
        _run(['mkfs.vfat', '-F', '32', '-n', 'BOOT', p1])
    except subprocess.CalledProcessError as e:
        _fatal(f'mkfs.vfat failed: {e.stderr.strip()}')

    _progress(16, f'Formatting {p2} as ext4…')
    _log(f'mkfs.ext4 -F -L ROOT {p2}')
    try:
        _run(['mkfs.ext4', '-F', '-L', 'ROOT', p2])
    except subprocess.CalledProcessError as e:
        _fatal(f'mkfs.ext4 failed: {e.stderr.strip()}')

    # ── mount ─────────────────────────────────────────────────────────────────
    _progress(20, 'Mounting partitions…')
    root_mnt = tempfile.mkdtemp(prefix='xeropi4-root-')
    boot_mnt = os.path.join(root_mnt, 'boot')

    def _cleanup():
        subprocess.run(['umount', '-lf', boot_mnt], capture_output=True)
        subprocess.run(['umount', '-lf', root_mnt],  capture_output=True)
        shutil.rmtree(root_mnt, ignore_errors=True)

    try:
        _log(f'Mounting ROOT ({p2}) at {root_mnt}…')
        _run(['mount', p2, root_mnt])

        os.makedirs(boot_mnt, exist_ok=True)

        _log(f'Mounting BOOT ({p1}) at {boot_mnt}…')
        _run(['mount', p1, boot_mnt])

        # ── extract rootfs ────────────────────────────────────────────────────
        tarball_size = Path(tarball).stat().st_size
        _progress(25, 'Extracting rootfs (this may take several minutes)…')
        _log(f'Source tarball: {tarball_size / 1024**2:.0f} MB')
        _log(f'bsdtar -xpf {tarball} -C {root_mnt}')

        t0 = time.time()
        proc = subprocess.run(
            ['bsdtar', '-xpf', tarball, '-C', root_mnt],
            capture_output=True, text=True,
        )
        elapsed = time.time() - t0
        if proc.returncode != 0:
            _cleanup()
            _fatal(f'bsdtar extraction failed: {proc.stderr.strip()}')

        # Measure what actually landed on disk — catches silent extraction failures
        du = subprocess.run(
            ['du', '-sb', '--exclude=' + boot_mnt, root_mnt],
            capture_output=True, text=True,
        )
        written_bytes = int(du.stdout.split()[0]) if du.returncode == 0 else 0
        written_mb = written_bytes / 1024**2
        _log(f'Extraction done in {elapsed:.0f}s — {written_mb:.0f} MB written to {p2}')
        if written_mb < 100:
            _cleanup()
            _fatal(f'Rootfs appears nearly empty after extraction ({written_mb:.0f} MB). Tarball may be corrupt or wrong format.')

        _progress(78, 'Rebranding OS release files…')
        _log('Patching /etc/os-release and /etc/lsb-release…')
        _rebrand(root_mnt)
        _log('Locking pacman to aarch64 architecture…')
        _ensure_pacman_arch(Path(root_mnt))
        _patch_pacman_conf(Path(root_mnt))
        _patch_mkinitcpio_conf(Path(root_mnt))
        if cfg.get('target_bus_type', '') != 'SD card':
            _log(f'Non-SD target ({cfg.get("target_bus_type","unknown")}): patching cmdline.txt + fstab for LABEL= boot…')
            _patch_boot_device_refs(root_mnt)
        _progress(79, 'Applying always-on configuration…')
        _log('Writing SSH key regen service, clearing machine-id, enabling sshd/NM…')
        _apply_always(Path(root_mnt))

        mode = cfg.get('mode', 'personal')
        raw_pkgs = (
            cfg.get('packages', [])
            + cfg.get('user_added_packages', [])
            + [p for p in cfg.get('extra_packages', '').split() if p]
        )
        filtered = [p for p in raw_pkgs if p not in _PI4_INCOMPATIBLE]
        if len(filtered) != len(raw_pkgs):
            dropped = [p for p in raw_pkgs if p in _PI4_INCOMPATIBLE]
            _log(f'Dropped incompatible packages: {", ".join(dropped)}')
        # Prepend forced Pi4 packages; deduplicate preserving order
        seen: set[str] = set()
        all_pkgs: list[str] = []
        for p in _PI4_FORCED_PACKAGES + filtered:
            if p not in seen:
                seen.add(p)
                all_pkgs.append(p)
        _log(f'Pi4 forced packages prepended: {", ".join(_PI4_FORCED_PACKAGES)}')

        if mode == 'distribution':
            _progress(80, 'Purifying distribution image…')
            _log('Stripping SSH keys, logs, pacman cache, histories, leases…')
            _purify(Path(root_mnt))

            _progress(82, 'Writing interactive first-boot setup wizard…')
            _write_dist_setup_script(Path(root_mnt), cfg)
            _write_dist_setup_service(Path(root_mnt))

            if all_pkgs:
                (Path(root_mnt) / 'etc/xeropi-firstboot-pending').write_text(
                    ' '.join(all_pkgs) + '\n'
                )
        else:
            _progress(80, 'Applying personal configuration…')
            post_cmds = _configure_personal(root_mnt, cfg)
            if all_pkgs:
                _progress(88, 'Writing first-boot package service…')
                _write_firstboot_pkg_service(Path(root_mnt), all_pkgs, post_cmds)

        if cfg.get('shrink_image'):
            _progress(84, 'Writing auto-expand service…')
            _write_autoexpand_service(Path(root_mnt))

        if cfg.get('shrink_image') and cfg.get('shrink_output_path'):
            _progress(90, 'Creating shrunk distribution image (this will take a while)…')
            _create_dist_image(root_mnt, boot_mnt, cfg['shrink_output_path'])

        _progress(95, 'Syncing…')
        _log('sync…')
        subprocess.run(['sync'], check=True)

        # ── unmount ───────────────────────────────────────────────────────────
        _progress(96, 'Unmounting…')
        _log(f'Unmounting {boot_mnt}…')
        try:
            _run(['umount', boot_mnt])
        except subprocess.CalledProcessError as e:
            _cleanup()
            _fatal(f'umount boot failed: {e.stderr.strip()}')

        _log(f'Unmounting {root_mnt}…')
        try:
            _run(['umount', root_mnt])
        except subprocess.CalledProcessError as e:
            _cleanup()
            _fatal(f'umount root failed: {e.stderr.strip()}')

    except Exception as e:
        _cleanup()
        _fatal(str(e))

    shutil.rmtree(root_mnt, ignore_errors=True)

    # ── Verify flash ──────────────────────────────────────────────────────────
    _progress(97, 'Verifying flash…')
    _log('Re-probing partitions and checking filesystem labels…')
    subprocess.run(['partprobe', target], capture_output=True)
    subprocess.run(['udevadm', 'settle', '--timeout=5'], capture_output=True)
    time.sleep(0.5)

    verify_ok = True
    for part, expected in [(p1, 'BOOT'), (p2, 'ROOT')]:
        r = subprocess.run(
            ['blkid', '-o', 'value', '-s', 'LABEL', part],
            capture_output=True, text=True,
        )
        found = r.stdout.strip()
        if found == expected:
            _log(f'  {part}: LABEL={expected} ✓')
        else:
            _log(f'  {part}: expected LABEL={expected}, got "{found or "(none)"}" ✗')
            verify_ok = False

    if verify_ok:
        _log('Flash verified — both partitions readable with correct labels.')
    else:
        _log('WARNING: Verification failed. The media may be faulty or the write was interrupted.')

    _progress(100, 'Done.')
    _out('done', success=True, msg=f'Successfully flashed {target}.')


if __name__ == '__main__':
    main()

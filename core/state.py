from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiskInfo:
    dev: str
    model: str
    size_bytes: int
    size_human: str
    bus_type: str        # "SD card", "USB disk", "NVMe", "other"
    is_system: bool


@dataclass
class AppState:
    # ── build mode ────────────────────────────────────────────────────────────
    mode: str = 'personal'          # 'personal' | 'distribution'

    # ── tarball ───────────────────────────────────────────────────────────────
    tarball_path: str = ''

    # ── target device ─────────────────────────────────────────────────────────
    target_device: Optional[DiskInfo] = None

    # ── personal mode: baked credentials ─────────────────────────────────────
    username: str = ''
    password: str = ''
    hostname: str = ''
    ssh_key: str = ''
    wheel: bool = False
    root_same_password: bool = False

    # ── personal mode: baked WiFi ─────────────────────────────────────────────
    wifi_ssid: str = ''
    wifi_password: str = ''
    wifi_country: str = 'US'

    # ── distribution mode: first-boot wizard toggles ──────────────────────────
    dist_ask_user: bool = True
    dist_ask_wheel: bool = True
    dist_ask_hostname: bool = True
    dist_ask_ssh_key: bool = True
    dist_ask_wifi: bool = True

    # ── personal mode: WiFi static IP ────────────────────────────────────────
    use_static_ip: bool = False
    static_ip: str = ''
    static_prefix: int = 24
    static_gateway: str = ''
    static_dns: str = '1.1.1.1'

    # ── personal mode: Ethernet static IP ────────────────────────────────────
    use_eth_static_ip: bool = False
    eth_static_ip: str = ''
    eth_static_prefix: int = 24
    eth_static_gateway: str = ''
    eth_static_dns: str = '1.1.1.1'

    # ── packages (both modes) ─────────────────────────────────────────────────
    packages: list = field(default_factory=list)
    extra_packages: str = ''
    user_added_packages: list = field(default_factory=list)

    # ── distribution mode: shrink-for-distribution ────────────────────────────
    shrink_image: bool = False
    shrink_output_path: str = ''

    # ── personal mode: flash an existing image directly ───────────────────────
    flash_mode: str = 'build'         # 'build' | 'flash_image'
    flash_image_path: str = ''


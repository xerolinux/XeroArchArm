"""QThread wrapper that runs flash_worker.py via pkexec and forwards its output."""
import json
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.state import AppState

_WORKER_PATH = Path(__file__).resolve().parent.parent.parent / 'worker' / 'flash_worker.py'


def _build_config(state: AppState) -> dict:
    d = state.target_device
    return {
        'target_dev':       d.dev if d else '',
        'target_bus_type':  d.bus_type if d else '',
        'tarball_path':     state.tarball_path,
        'mode':             state.mode,
        'username':         state.username,
        'password':         state.password,
        'hostname':         state.hostname,
        'ssh_key':          state.ssh_key,
        'wheel':            state.wheel,
        'root_same_password': state.root_same_password,
        'wifi_ssid':        state.wifi_ssid,
        'wifi_password':    state.wifi_password,
        'wifi_country':     state.wifi_country,
        'packages':             state.packages,
        'extra_packages':       state.extra_packages,
        'user_added_packages':  state.user_added_packages,
        'use_static_ip':        state.use_static_ip,
        'static_ip':            state.static_ip,
        'static_prefix':        state.static_prefix,
        'static_gateway':       state.static_gateway,
        'static_dns':           state.static_dns,
        'use_eth_static_ip':    state.use_eth_static_ip,
        'eth_static_ip':        state.eth_static_ip,
        'eth_static_prefix':    state.eth_static_prefix,
        'eth_static_gateway':   state.eth_static_gateway,
        'eth_static_dns':       state.eth_static_dns,
        'dist_ask_user':        state.dist_ask_user,
        'dist_ask_wheel':       state.dist_ask_wheel,
        'dist_ask_hostname':    state.dist_ask_hostname,
        'dist_ask_ssh_key':     state.dist_ask_ssh_key,
        'dist_ask_wifi':        state.dist_ask_wifi,
        'shrink_image':         state.shrink_image,
        'shrink_output_path':   state.shrink_output_path,
        'flash_mode':           state.flash_mode,
        'flash_image_path':     state.flash_image_path,
    }


class FlashRunner(QThread):
    log_line = Signal(str)           # plain text log message
    progress = Signal(int, str)      # (pct 0-100, message)
    finished = Signal(bool, str)     # (success, message)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._config_path: str | None = None

    def run(self) -> None:
        worker = str(_WORKER_PATH)

        if not Path(worker).exists():
            self.finished.emit(
                False,
                f'Flash worker not found at {worker}.\nRun worker/install.sh as root first.',
            )
            return

        # Write config to a temp file (root can read files in /tmp)
        cfg = _build_config(self._state)
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False, prefix='xeropi4-cfg-'
            ) as tf:
                json.dump(cfg, tf)
                self._config_path = tf.name
        except OSError as e:
            self.finished.emit(False, f'Cannot write config: {e}')
            return

        try:
            proc = subprocess.Popen(
                ['pkexec', worker, self._config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            for raw in proc.stdout:
                line = raw.rstrip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    t = msg.get('type', '')
                    if t == 'log':
                        self.log_line.emit(msg.get('msg', ''))
                    elif t == 'progress':
                        self.progress.emit(msg.get('pct', 0), msg.get('msg', ''))
                    elif t == 'error':
                        self.log_line.emit(f'ERROR: {msg.get("msg", "")}')
                    elif t == 'done':
                        pass  # outcome resolved below via returncode
                except json.JSONDecodeError:
                    self.log_line.emit(line)

            proc.wait()

            if proc.returncode == 126:
                self.finished.emit(False, 'Authentication cancelled.')
            elif proc.returncode == 127:
                self.finished.emit(False, 'pkexec could not find the flash worker.')
            elif proc.returncode != 0:
                stderr = proc.stderr.read().strip()
                detail = f'\n{stderr}' if stderr else ''
                self.finished.emit(False, f'Worker exited with code {proc.returncode}.{detail}')
            else:
                dev = self._state.target_device
                self.finished.emit(True, f'Flashed {dev.dev} successfully.' if dev else 'Flash complete.')

        except Exception as e:
            self.finished.emit(False, str(e))

        finally:
            if self._config_path:
                Path(self._config_path).unlink(missing_ok=True)
                self._config_path = None

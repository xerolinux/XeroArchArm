import ctypes
import shiboken6
from PySide6.QtGui import QRegion

_fn = None


def _load():
    global _fn
    try:
        lib = ctypes.CDLL("libKF6WindowSystem.so.6")
        _fn = lib["_ZN14KWindowEffects16enableBlurBehindEP7QWindowbRK7QRegion"]
        _fn.restype = None
        _fn.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_void_p]
        return True
    except Exception as e:
        print(f"[blur] load failed: {e}")
        return False


def enable_blur(qwindow, enable: bool = True) -> None:
    global _fn
    if _fn is None and not _load():
        return
    try:
        win_ptr = shiboken6.getCppPointer(qwindow)[0]
        region = QRegion()  # empty = blur entire window
        region_ptr = shiboken6.getCppPointer(region)[0]
        _fn(win_ptr, enable, region_ptr)
    except Exception as e:
        print(f"[blur] call failed: {e}")

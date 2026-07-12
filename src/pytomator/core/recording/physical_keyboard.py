"""Windows physical-key metadata and SendInput support."""

import ctypes
import sys
from ctypes import wintypes


def key_vk(key) -> int | None:
    value = getattr(key, "vk", None)
    if value is None:
        value = getattr(getattr(key, "value", None), "vk", None)
    return int(value) if value is not None else None


if sys.platform == "win32":
    MAPVK_VK_TO_VSC_EX = 4
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008
    INPUT_KEYBOARD = 1
    ULONG_PTR = wintypes.WPARAM
    _user32 = ctypes.windll.user32
    _user32.GetKeyboardLayout.restype = ctypes.c_void_p
    _user32.MapVirtualKeyExW.argtypes = (wintypes.UINT, wintypes.UINT, ctypes.c_void_p)
    _user32.MapVirtualKeyExW.restype = wintypes.UINT

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    def active_keyboard_layout() -> str:
        hwnd = _user32.GetForegroundWindow()
        thread_id = _user32.GetWindowThreadProcessId(hwnd, None) if hwnd else 0
        layout = _user32.GetKeyboardLayout(thread_id)
        return f"0x{int(layout) & ((1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1):x}"

    def physical_metadata(key) -> dict:
        vk = key_vk(key)
        source = getattr(key, "value", key)
        captured_scan = getattr(key, "_scan", None) or getattr(source, "_scan", None)
        captured_flags = getattr(key, "_flags", None) or getattr(source, "_flags", None) or 0
        if vk is None and not captured_scan:
            return {"layout": active_keyboard_layout()}
        layout_value = _user32.GetKeyboardLayout(0)
        mapped = int(captured_scan or _user32.MapVirtualKeyExW(vk, MAPVK_VK_TO_VSC_EX, layout_value))
        prefix = (mapped >> 8) & 0xFF
        return {"vk": vk, "scan_code": mapped & 0xFF,
                "extended": bool(captured_flags & 0x01) or prefix in {0xE0, 0xE1},
                "layout": active_keyboard_layout()}

    def physical_key_flags(*, scan_code, extended=False, key_up=False):
        flags = KEYEVENTF_KEYUP if key_up else 0
        if scan_code:
            flags |= KEYEVENTF_SCANCODE
            if extended: flags |= KEYEVENTF_EXTENDEDKEY
        return flags

    def send_physical_key(*, scan_code: int | None, vk: int | None,
                          extended: bool = False, key_up: bool = False):
        flags = physical_key_flags(scan_code=scan_code, extended=extended, key_up=key_up)
        if scan_code:
            keyboard = KEYBDINPUT(0, int(scan_code), flags, 0, 0)
        elif vk is not None:
            keyboard = KEYBDINPUT(int(vk), 0, flags, 0, 0)
        else:
            raise ValueError("A physical key requires scan_code or vk")
        input_event = INPUT(INPUT_KEYBOARD, INPUT_UNION(ki=keyboard))
        if _user32.SendInput(1, ctypes.byref(input_event), ctypes.sizeof(INPUT)) != 1:
            raise ctypes.WinError()
else:
    def active_keyboard_layout() -> str | None: return None
    def physical_metadata(key) -> dict: return {}
    def send_physical_key(**_): raise RuntimeError("Physical keyboard playback is available only on Windows")
    def physical_key_flags(**_): return 0

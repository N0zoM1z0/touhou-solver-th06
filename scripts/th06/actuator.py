"""Foreground-guarded physical keyboard output. There is no Bomb mapping."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from .model import Action


ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KeybdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class InputUnion(ctypes.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeybdInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", InputUnion)]


class Keyboard:
    SCANCODES = {
        "shoot": (0x2C, False),
        "focus": (0x2A, False),
        "skip": (0x1D, False),
        "up": (0x48, True),
        "down": (0x50, True),
        "left": (0x4B, True),
        "right": (0x4D, True),
    }

    def __init__(self, pid: int):
        self.pid = pid
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.held: set[str] = set()
        self.base_desired: set[str] = set()
        self.auxiliary_desired: set[str] = set()

    def foreground(self) -> bool:
        hwnd = self.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == self.pid

    def _event(self, key: str, down: bool) -> None:
        scan, extended = self.SCANCODES[key]
        flags = 0x0008 | (0x0001 if extended else 0) | (0 if down else 0x0002)
        event = Input(type=1, union=InputUnion(ki=KeybdInput(0, scan, flags, 0, 0)))
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def _sync(self) -> None:
        desired = self.base_desired | self.auxiliary_desired
        for key in sorted(self.held - desired):
            self._event(key, False)
        for key in sorted(desired - self.held):
            self._event(key, True)
        self.held = desired

    def apply(self, action: Action) -> None:
        desired = {"shoot", "focus"}
        if action.dx < 0:
            desired.add("left")
        elif action.dx > 0:
            desired.add("right")
        if action.dy < 0:
            desired.add("up")
        elif action.dy > 0:
            desired.add("down")
        self.base_desired = desired
        self._sync()

    def set_auxiliary(self, key: str, enabled: bool) -> None:
        if key not in self.SCANCODES:
            raise ValueError(f"unsupported auxiliary key: {key}")
        if enabled:
            self.auxiliary_desired.add(key)
        else:
            self.auxiliary_desired.discard(key)
        self._sync()

    def tap(self, key: str, hold_seconds: float = 0.05) -> None:
        if key not in self.SCANCODES:
            raise ValueError(f"unsupported key: {key}")
        if not self.foreground():
            raise RuntimeError("TH06 is not foreground for menu input")
        self._event(key, True)
        time.sleep(hold_seconds)
        self._event(key, False)
        time.sleep(0.12)

    def pulse(self, key: str, release_seconds: float = 0.05) -> None:
        """Create a fresh key-down edge without disturbing other held keys."""
        if key not in self.SCANCODES:
            raise ValueError(f"unsupported key: {key}")
        if not self.foreground():
            raise RuntimeError("TH06 is not foreground for key pulse")
        was_held = key in self.held
        if was_held:
            self._event(key, False)
            time.sleep(release_seconds)
            self._event(key, True)
        else:
            self._event(key, True)
            time.sleep(release_seconds)
            self._event(key, False)

    def release_all(self) -> None:
        for key in sorted(self.held):
            self._event(key, False)
        self.held.clear()
        self.base_desired.clear()
        self.auxiliary_desired.clear()

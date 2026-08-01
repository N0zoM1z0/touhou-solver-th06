"""Exact TH06 1.02h process identity, patching, and native sensing."""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import struct
import time
from ctypes import wintypes
from pathlib import Path

from .model import Bullet, PLAYER_ALIVE, PLAYER_INVULNERABLE, Snapshot


TARGET_EXE = "th06.exe"
TARGET_SHA256 = "9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245"

IMAGE_BASE = 0x400000
ADDR_LIFE_PATCH = 0x428DEC
ADDR_GAME_MANAGER = 0x69BCA0
ADDR_CURRENT_INPUT = 0x69D904
ADDR_PLAYER = 0x6CA628
ADDR_FRAME_MULTIPLIER = 0x6C6EC0
ADDR_BULLET_ARRAY = 0x5AB5F8
ADDR_LASER_ARRAY = 0x691FF8
ADDR_MAIN_MENU = 0x6D46C0
ADDR_GUI = 0x69BC30

GAME_TIME_STOPPED_OFFSET = 0x2C
GAME_FLAGS_OFFSET = 0x181F
GAME_FRAMES_OFFSET = 0x1A30
GAME_STAGE_OFFSET = 0x1A34
PLAYER_POSITION_OFFSET = 0x440
PLAYER_HITBOX_TOP_LEFT_OFFSET = 0x458
PLAYER_HITBOX_BOTTOM_RIGHT_OFFSET = 0x464
PLAYER_STATE_OFFSET = 0x9E0
PLAYER_SPEEDS_OFFSET = 0x9F4

BULLET_COUNT = 640
BULLET_STRIDE = 0x5C4
BULLET_SIZE_OFFSET = 0x550
BULLET_POSITION_OFFSET = 0x560
BULLET_VELOCITY_OFFSET = 0x56C
BULLET_ACCELERATION_OFFSET = 0x578
BULLET_SPEED_OFFSET = 0x584
BULLET_ACCEL_SPEED_OFFSET = 0x588
BULLET_TURN_SPEED_OFFSET = 0x58C
BULLET_EX_FLAGS_OFFSET = 0x5B8
BULLET_STATE_OFFSET = 0x5BE
LASER_COUNT = 64
LASER_STRIDE = 0x270
LASER_IN_USE_OFFSET = 0x258
MAIN_MENU_CURSOR_OFFSET = 0x81A0
MAIN_MENU_STATE_OFFSET = 0x81F0
MAIN_MENU_TIMER_OFFSET = 0x81F4
GUI_IMPL_MSG_OFFSET = 0x2534
GUI_MSG_INDEX_OFFSET = 0x8
GUI_MSG_SKIPPABLE_OFFSET = 0x6A7


def _kernel32():
    if os.name != "nt":
        raise RuntimeError("native TH06 access requires Windows Python")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    api.TerminateProcess.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.ReadProcessMemory.argtypes = [
        wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)
    ]
    api.ReadProcessMemory.restype = wintypes.BOOL
    api.WriteProcessMemory.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.LPCVOID, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)
    ]
    api.WriteProcessMemory.restype = wintypes.BOOL
    api.VirtualProtectEx.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]
    api.VirtualProtectEx.restype = wintypes.BOOL
    api.FlushInstructionCache.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, ctypes.c_size_t]
    api.FlushInstructionCache.restype = wintypes.BOOL
    api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    api.QueryFullProcessImageNameW.restype = wintypes.BOOL
    return api


class NativeProcess:
    def __init__(self, pid: int):
        self.kernel32 = _kernel32()
        access = 0x0001 | 0x0400 | 0x1000 | 0x0010 | 0x0020 | 0x0008
        self.handle = self.kernel32.OpenProcess(access, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.pid = pid

    def close(self) -> None:
        if self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None

    def terminate(self) -> None:
        """Stop only the exact, identity-verified trial process we attached."""
        if not self.handle:
            return
        if not self.kernel32.TerminateProcess(self.handle, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if self.kernel32.WaitForSingleObject(self.handle, 5000) != 0:
            raise RuntimeError(f"TH06 pid {self.pid} did not terminate within 5 seconds")

    def read(self, address: int, size: int) -> bytes:
        buffer = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not self.kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(count)
        ) or count.value != size:
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw

    def patch_lives(self) -> str:
        old = self.read(ADDR_LIFE_PATCH, 1)
        if old == b"\x00":
            return "already-patched"
        if old != b"\x01":
            raise RuntimeError(f"unexpected life-patch byte: {old.hex()}")
        old_protection = wintypes.DWORD()
        if not self.kernel32.VirtualProtectEx(
            self.handle, ctypes.c_void_p(ADDR_LIFE_PATCH), 1, 0x40, ctypes.byref(old_protection)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            data = ctypes.create_string_buffer(b"\x00")
            written = ctypes.c_size_t()
            if not self.kernel32.WriteProcessMemory(
                self.handle, ctypes.c_void_p(ADDR_LIFE_PATCH), data, 1, ctypes.byref(written)
            ) or written.value != 1:
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel32.FlushInstructionCache(self.handle, ctypes.c_void_p(ADDR_LIFE_PATCH), 1):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            restored = wintypes.DWORD()
            self.kernel32.VirtualProtectEx(
                self.handle, ctypes.c_void_p(ADDR_LIFE_PATCH), 1, old_protection.value, ctypes.byref(restored)
            )
        if self.read(ADDR_LIFE_PATCH, 1) != b"\x00":
            raise RuntimeError("life patch did not verify")
        return "patched-01-to-00"


def _process_candidates(exe_name: str) -> list[tuple[int, str]]:
    api = _kernel32()

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    api.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    api.Process32FirstW.restype = wintypes.BOOL
    api.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    api.Process32NextW.restype = wintypes.BOOL
    snapshot = api.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    result: list[tuple[int, str]] = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = api.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() == exe_name.lower():
                handle = api.OpenProcess(0x1000, False, entry.th32ProcessID)
                if handle:
                    try:
                        size = wintypes.DWORD(32768)
                        path = ctypes.create_unicode_buffer(size.value)
                        if api.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                            result.append((entry.th32ProcessID, path.value))
                    finally:
                        api.CloseHandle(handle)
            more = api.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        api.CloseHandle(snapshot)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attach_exact(game_dir: Path, timeout: float = 20.0) -> NativeProcess:
    expected = os.path.normcase(os.path.abspath(str(game_dir / TARGET_EXE)))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        exact = [
            (pid, path)
            for pid, path in _process_candidates(TARGET_EXE)
            if os.path.normcase(os.path.abspath(path)) == expected
        ]
        if len(exact) > 1:
            raise RuntimeError(f"multiple exact TH06 processes: {[pid for pid, _ in exact]}")
        if len(exact) == 1:
            pid, image_path = exact[0]
            if _sha256(Path(image_path)) != TARGET_SHA256:
                raise RuntimeError("TH06 executable SHA-256 mismatch")
            process = NativeProcess(pid)
            try:
                if process.read(IMAGE_BASE, 2) != b"MZ":
                    raise RuntimeError("TH06 image-base verification failed")
                return process
            except Exception:
                process.close()
                raise
        time.sleep(0.25)
    raise RuntimeError(f"exact target not found at {game_dir / TARGET_EXE}")


def read_snapshot(process: NativeProcess) -> Snapshot:
    game = process.read(ADDR_GAME_MANAGER + GAME_FLAGS_OFFSET, GAME_STAGE_OFFSET + 4 - GAME_FLAGS_OFFSET)
    game_menu, retry_menu, gameplay_active, _completed, _practice, demo_mode = game[0:6]
    # Despite its name, GameManager::OnUpdate sets isInMenu=1 during normal
    # gameplay and 0 while its pause/retry menu breaks the calc chain.
    in_menu = bool(game_menu or retry_menu or not gameplay_active or demo_mode)
    frame = struct.unpack_from("<I", game, GAME_FRAMES_OFFSET - GAME_FLAGS_OFFSET)[0]
    stage = struct.unpack_from("<i", game, GAME_STAGE_OFFSET - GAME_FLAGS_OFFSET)[0]
    time_stopped = bool(process.read(ADDR_GAME_MANAGER + GAME_TIME_STOPPED_OFFSET, 1)[0])
    is_replay = bool(struct.unpack("<I", process.read(ADDR_GAME_MANAGER + 0x1C, 4))[0])
    frame_multiplier = struct.unpack("<f", process.read(ADDR_FRAME_MULTIPLIER, 4))[0]
    input_mask = struct.unpack("<H", process.read(ADDR_CURRENT_INPUT, 2))[0]

    player = process.read(ADDR_PLAYER + PLAYER_POSITION_OFFSET, PLAYER_SPEEDS_OFFSET + 16 - PLAYER_POSITION_OFFSET)
    relative = lambda absolute: absolute - PLAYER_POSITION_OFFSET
    x, y = struct.unpack_from("<ff", player, relative(PLAYER_POSITION_OFFSET))
    hit_left, hit_top = struct.unpack_from("<ff", player, relative(PLAYER_HITBOX_TOP_LEFT_OFFSET))
    hit_right, hit_bottom = struct.unpack_from("<ff", player, relative(PLAYER_HITBOX_BOTTOM_RIGHT_OFFSET))
    player_state = player[relative(PLAYER_STATE_OFFSET)]
    normal_speed, focus_speed, normal_diagonal, focus_diagonal = struct.unpack_from(
        "<ffff", player, relative(PLAYER_SPEEDS_OFFSET)
    )
    values = (
        x, y, hit_left, hit_top, hit_right, hit_bottom,
        normal_speed, focus_speed, normal_diagonal, focus_diagonal, frame_multiplier,
    )
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError("non-finite player or timing state")
    half_width = max(0.0, (hit_right - hit_left) / 2.0)
    half_height = max(0.0, (hit_bottom - hit_top) / 2.0)
    active_geometry = (
        0.5 <= half_width <= 8.0
        and 0.5 <= half_height <= 8.0
        and 0.5 <= focus_speed <= 8.0
        and 0.5 <= normal_speed <= 8.0
        and -64.0 <= x <= 448.0
        and -64.0 <= y <= 512.0
    )
    if player_state in (PLAYER_ALIVE, PLAYER_INVULNERABLE) and not active_geometry:
        in_menu = True

    pool = process.read(
        ADDR_BULLET_ARRAY,
        ADDR_LASER_ARRAY + LASER_COUNT * LASER_STRIDE - ADDR_BULLET_ARRAY,
    )
    bullets: list[Bullet] = []
    for index in range(BULLET_COUNT):
        base = index * BULLET_STRIDE
        state = struct.unpack_from("<H", pool, base + BULLET_STATE_OFFSET)[0]
        if state == 0 or state == 5:
            continue
        if state not in (1, 2, 3, 4):
            raise RuntimeError(f"invalid bullet state {state} at slot {index}")
        size_x, size_y = struct.unpack_from("<ff", pool, base + BULLET_SIZE_OFFSET)
        bx, by = struct.unpack_from("<ff", pool, base + BULLET_POSITION_OFFSET)
        vx, vy = struct.unpack_from("<ff", pool, base + BULLET_VELOCITY_OFFSET)
        ax, ay = struct.unpack_from("<ff", pool, base + BULLET_ACCELERATION_OFFSET)
        speed, accel_speed, turn_speed = struct.unpack_from("<fff", pool, base + BULLET_SPEED_OFFSET)
        ex_flags = struct.unpack_from("<H", pool, base + BULLET_EX_FLAGS_OFFSET)[0]
        numbers = (size_x, size_y, bx, by, vx, vy, ax, ay, speed, accel_speed, turn_speed)
        if not all(math.isfinite(value) for value in numbers) or not (
            0.0 < size_x <= 256.0 and 0.0 < size_y <= 256.0
        ):
            raise RuntimeError(f"invalid bullet geometry at slot {index}")
        bullets.append(
            Bullet(
                bx, by, vx, vy, size_x / 2.0, size_y / 2.0, state, ex_flags,
                math.hypot(ax, ay) + abs(accel_speed), speed, turn_speed,
            )
        )

    laser_base = ADDR_LASER_ARRAY - ADDR_BULLET_ARRAY
    active_lasers = sum(
        1
        for index in range(LASER_COUNT)
        if struct.unpack_from("<i", pool, laser_base + index * LASER_STRIDE + LASER_IN_USE_OFFSET)[0]
    )
    return Snapshot(
        frame, stage, player_state, x, y, half_width, half_height,
        normal_speed, focus_speed, normal_diagonal, focus_diagonal,
        frame_multiplier, input_mask, tuple(bullets), active_lasers, in_menu, time_stopped,
        bool(is_replay or demo_mode),
    )


def read_menu_state(process: NativeProcess) -> tuple[int, int, int]:
    block = process.read(
        ADDR_MAIN_MENU + MAIN_MENU_CURSOR_OFFSET,
        MAIN_MENU_TIMER_OFFSET + 4 - MAIN_MENU_CURSOR_OFFSET,
    )
    cursor = struct.unpack_from("<i", block, 0)[0]
    state = struct.unpack_from("<i", block, MAIN_MENU_STATE_OFFSET - MAIN_MENU_CURSOR_OFFSET)[0]
    timer = struct.unpack_from("<i", block, MAIN_MENU_TIMER_OFFSET - MAIN_MENU_CURSOR_OFFSET)[0]
    return state, cursor, timer


def read_dialogue_state(process: NativeProcess) -> tuple[bool, bool]:
    impl = struct.unpack("<I", process.read(ADDR_GUI + 4, 4))[0]
    if impl == 0:
        return False, False
    msg = impl + GUI_IMPL_MSG_OFFSET
    current_index = struct.unpack("<i", process.read(msg + GUI_MSG_INDEX_OFFSET, 4))[0]
    skippable = bool(process.read(msg + GUI_MSG_SKIPPABLE_OFFSET, 1)[0])
    return current_index >= 0, skippable

"""Exact TH06 1.02h process identity, patching, and native sensing."""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import struct
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .model import (
    Bullet,
    BulletPattern,
    EnemyBody,
    EnemyEclContext,
    EnemySpawner,
    EclInstruction,
    Laser,
    PLAYER_ALIVE,
    PLAYER_INVULNERABLE,
    Snapshot,
)


TARGET_EXE = "th06.exe"
TARGET_SHA256 = "9f76483c46256804792399296619c1274363c31cd8f1775fafb55106fb852245"
PROCESS_ACCESS = 0x00100000 | 0x0001 | 0x0400 | 0x1000 | 0x0010 | 0x0020 | 0x0008

IMAGE_BASE = 0x400000
ADDR_LIFE_PATCH = 0x428DEC
ADDR_GAME_MANAGER = 0x69BCA0
ADDR_CURRENT_INPUT = 0x69D904
ADDR_RNG = 0x69D8F8
ADDR_CHAIN = 0x69D918
ADDR_SUPERVISOR = 0x6C6D18
ADDR_PLAYER = 0x6CA628
ADDR_FRAME_MULTIPLIER = 0x6C6EC0
ADDR_ENEMY_MANAGER = 0x4B79C8
ADDR_ECL_EX_TABLE = 0x476220
ADDR_ECL_MANAGER = 0x487E50
ADDR_ENEMY_CALC_CHAIN = 0x5A5FB4
ADDR_BULLET_MANAGER = 0x5A5FF8
ADDR_BULLET_ARRAY = 0x5AB5F8
ADDR_LASER_ARRAY = 0x691FF8
ADDR_MAIN_MENU = 0x6D46C0
ADDR_GUI = 0x69BC30

SUPERVISOR_STATES_OFFSET = 0x188
CHAIN_ROOT_NEXT_OFFSET = 0x14
CHAIN_ELEM_CALLBACK_OFFSET = 0x4
CHAIN_ELEM_NEXT_OFFSET = 0x14
CHAIN_ELEM_ARG_OFFSET = 0x1C
CHAIN_ELEM_SIZE = 0x20
RESULT_SCREEN_ON_UPDATE = 0x42D98E
RESULT_SCREEN_STATE_SIZE = 0x34

GAME_TIME_STOPPED_OFFSET = 0x2C
GAME_DIFFICULTY_OFFSET = 0x10
GAME_FLAGS_OFFSET = 0x181F
GAME_FRAMES_OFFSET = 0x1A30
GAME_STAGE_OFFSET = 0x1A34
GAME_RANK_OFFSET = 0x1A70
PLAYER_POSITION_OFFSET = 0x440
PLAYER_HITBOX_TOP_LEFT_OFFSET = 0x458
PLAYER_HITBOX_BOTTOM_RIGHT_OFFSET = 0x464
PLAYER_STATE_OFFSET = 0x9E0
PLAYER_SPEEDS_OFFSET = 0x9F4

BULLET_COUNT = 640
BULLET_STRIDE = 0x5C4
BULLET_TEMPLATE_COUNT = 16
BULLET_TEMPLATE_STRIDE = 0x560
BULLET_TEMPLATE_SIZE_OFFSET = 0x550
BULLET_SIZE_OFFSET = 0x550
BULLET_POSITION_OFFSET = 0x560
BULLET_VELOCITY_OFFSET = 0x56C
BULLET_ACCELERATION_OFFSET = 0x578
BULLET_SPEED_OFFSET = 0x584
BULLET_ACCEL_SPEED_OFFSET = 0x588
BULLET_TURN_SPEED_OFFSET = 0x58C
BULLET_ANGLE_OFFSET = 0x590
BULLET_CURVE_ANGULAR_VELOCITY_OFFSET = 0x594
BULLET_DIRECTION_ROTATION_OFFSET = 0x598
BULLET_TIMER_SUBFRAME_OFFSET = 0x5A0
BULLET_TIMER_CURRENT_OFFSET = 0x5A4
BULLET_ACCELERATION_DURATION_OFFSET = 0x5A8
BULLET_DIRECTION_INTERVAL_OFFSET = 0x5AC
BULLET_DIRECTION_NUM_TIMES_OFFSET = 0x5B0
BULLET_DIRECTION_MAX_TIMES_OFFSET = 0x5B4
BULLET_EX_FLAGS_OFFSET = 0x5B8
BULLET_STATE_OFFSET = 0x5BE
LASER_COUNT = 64
LASER_STRIDE = 0x270
LASER_POSITION_OFFSET = 0x220
LASER_ANGLE_OFFSET = 0x22C
LASER_START_OFFSET = 0x230
LASER_END_OFFSET = 0x234
LASER_START_LENGTH_OFFSET = 0x238
LASER_WIDTH_OFFSET = 0x23C
LASER_SPEED_OFFSET = 0x240
LASER_START_TIME_OFFSET = 0x244
LASER_HITBOX_START_TIME_OFFSET = 0x248
LASER_DURATION_OFFSET = 0x24C
LASER_DESPAWN_DURATION_OFFSET = 0x250
LASER_HITBOX_END_DELAY_OFFSET = 0x254
LASER_IN_USE_OFFSET = 0x258
LASER_TIMER_SUBFRAME_OFFSET = 0x260
LASER_TIMER_OFFSET = 0x264
LASER_FLAGS_OFFSET = 0x268
LASER_STATE_OFFSET = 0x26C
ENEMY_MANAGER_SIZE = 0xEE5EC
ENEMY_ARRAY_OFFSET = 0xED0
ENEMY_COUNT = 256
ENEMY_STRIDE = 0xEC8
ENEMY_ECL_CONTEXT_OFFSET = 0x990
ENEMY_ECL_CONTEXT_SIZE = 0x4C
ENEMY_ECL_STACK_CAPACITY = 8
ENEMY_ECL_STACK_DEPTH_OFFSET = 0xC3C
ENEMY_POSITION_OFFSET = 0xC6C
ENEMY_HITBOX_OFFSET = 0xC78
ENEMY_AXIS_SPEED_OFFSET = 0xC84
ENEMY_ANGLE_OFFSET = 0xC90
ENEMY_ANGULAR_VELOCITY_OFFSET = 0xC94
ENEMY_SPEED_OFFSET = 0xC98
ENEMY_ACCELERATION_OFFSET = 0xC9C
ENEMY_SHOOT_OFFSET = 0xCA0
ENEMY_MOVE_INTERP_OFFSET = 0xCAC
ENEMY_MOVE_START_OFFSET = 0xCB8
ENEMY_MOVE_TIMER_SUBFRAME_OFFSET = 0xCC8
ENEMY_MOVE_TIMER_OFFSET = 0xCCC
ENEMY_MOVE_START_TIME_OFFSET = 0xCD0
ENEMY_BULLET_RANK_SPEED_LOW_OFFSET = 0xCD4
ENEMY_BULLET_RANK_SPEED_HIGH_OFFSET = 0xCD8
ENEMY_BULLET_RANK_AMOUNT1_LOW_OFFSET = 0xCDC
ENEMY_BULLET_RANK_AMOUNT1_HIGH_OFFSET = 0xCDE
ENEMY_BULLET_RANK_AMOUNT2_LOW_OFFSET = 0xCE0
ENEMY_BULLET_RANK_AMOUNT2_HIGH_OFFSET = 0xCE2
ENEMY_LIFE_OFFSET = 0xCE4
ENEMY_BOSS_TIMER_SUBFRAME_OFFSET = 0xCF4
ENEMY_BOSS_TIMER_OFFSET = 0xCF8
ENEMY_BULLET_PROPS_OFFSET = 0xD00
ENEMY_SHOOT_INTERVAL_OFFSET = 0xD54
ENEMY_SHOOT_TIMER_SUBFRAME_OFFSET = 0xD5C
ENEMY_SHOOT_TIMER_OFFSET = 0xD60
ENEMY_FLAGS_OFFSET = 0xE50
ENEMY_LOWER_MOVE_LIMIT_OFFSET = 0xE60
ENEMY_UPPER_MOVE_LIMIT_OFFSET = 0xE68
ENEMY_LIFE_CALLBACK_THRESHOLD_OFFSET = 0xEA8
ENEMY_LIFE_CALLBACK_SUB_OFFSET = 0xEAC
ENEMY_TIMER_CALLBACK_THRESHOLD_OFFSET = 0xEB0
ENEMY_TIMER_CALLBACK_SUB_OFFSET = 0xEB4
ENEMY_DEATH_CALLBACK_SUB_OFFSET = 0xC44
ECL_EX_COUNT = 17
ECL_PROGRAM_INSTRUCTION_LIMIT = 96
ECL_SUBROUTINE_LIMIT = 512
MAIN_MENU_CURSOR_OFFSET = 0x81A0
MAIN_MENU_STATE_OFFSET = 0x81F0
MAIN_MENU_TIMER_OFFSET = 0x81F4
GUI_IMPL_MSG_OFFSET = 0x2534
GUI_MSG_INDEX_OFFSET = 0x8
GUI_MSG_SKIPPABLE_OFFSET = 0x6A7


@dataclass(frozen=True)
class ResultScreenState:
    address: int
    frame_timer: int
    state: int
    cursor: int
    replay_number: int
    selected_character: int


class NativeDecodeError(RuntimeError):
    def __init__(self, message: str, evidence: dict):
        super().__init__(message)
        self.evidence = evidence


def _decode_bullet_tail(tail: bytes, slot: int) -> Bullet | None:
    relative = lambda absolute: absolute - BULLET_SIZE_OFFSET
    state = struct.unpack_from("<H", tail, relative(BULLET_STATE_OFFSET))[0]
    if state == 0:
        return None
    size_x, size_y = struct.unpack_from("<ff", tail, 0)
    bx, by = struct.unpack_from("<ff", tail, relative(BULLET_POSITION_OFFSET))
    vx, vy = struct.unpack_from("<ff", tail, relative(BULLET_VELOCITY_OFFSET))
    ax, ay = struct.unpack_from("<ff", tail, relative(BULLET_ACCELERATION_OFFSET))
    speed, accel_speed, turn_speed = struct.unpack_from(
        "<fff", tail, relative(BULLET_SPEED_OFFSET)
    )
    angle = struct.unpack_from("<f", tail, relative(BULLET_ANGLE_OFFSET))[0]
    curve_angular_velocity = struct.unpack_from(
        "<f", tail, relative(BULLET_CURVE_ANGULAR_VELOCITY_OFFSET)
    )[0]
    direction_rotation = struct.unpack_from(
        "<f", tail, relative(BULLET_DIRECTION_ROTATION_OFFSET)
    )[0]
    timer_subframe = struct.unpack_from(
        "<f", tail, relative(BULLET_TIMER_SUBFRAME_OFFSET)
    )[0]
    timer = struct.unpack_from("<i", tail, relative(BULLET_TIMER_CURRENT_OFFSET))[0]
    acceleration_duration = struct.unpack_from(
        "<i", tail, relative(BULLET_ACCELERATION_DURATION_OFFSET)
    )[0]
    direction_interval, direction_num_times, direction_max_times = struct.unpack_from(
        "<iii", tail, relative(BULLET_DIRECTION_INTERVAL_OFFSET)
    )
    ex_flags = struct.unpack_from("<H", tail, relative(BULLET_EX_FLAGS_OFFSET))[0]
    numbers = (
        size_x,
        size_y,
        bx,
        by,
        vx,
        vy,
        ax,
        ay,
        speed,
        accel_speed,
        turn_speed,
        angle,
        curve_angular_velocity,
        direction_rotation,
        timer_subframe,
    )
    if state not in (1, 2, 3, 4, 5) or not all(
        math.isfinite(value) for value in numbers
    ) or not (0.0 < size_x <= 256.0 and 0.0 < size_y <= 256.0):
        raise NativeDecodeError(
            f"invalid bullet geometry at slot {slot}",
            {
                "slot": slot,
                "state": state,
                "values": tuple(repr(value) for value in numbers),
                "tail_hex": tail.hex(),
            },
        )
    if state == 1 and ex_flags & 0x1C0 and not (
        timer >= 0
        and direction_interval > 0
        and 0 <= direction_num_times < direction_max_times <= 0x10000
    ):
        raise NativeDecodeError(
            f"invalid bullet direction schedule at slot {slot}",
            {
                "slot": slot,
                "state": state,
                "ex_flags": ex_flags,
                "timer": timer,
                "direction_interval": direction_interval,
                "direction_num_times": direction_num_times,
                "direction_max_times": direction_max_times,
                "tail_hex": tail.hex(),
            },
        )
    invalid_acceleration_duration = (
        ex_flags & 0x10 and not 0 < acceleration_duration <= 99999
    ) or (
        ex_flags & 0x20 and not -99999 <= acceleration_duration <= 99999
    )
    if invalid_acceleration_duration:
        raise NativeDecodeError(
            f"invalid bullet acceleration duration at slot {slot}",
            {
                "slot": slot,
                "state": state,
                "ex_flags": ex_flags,
                "timer": timer,
                "acceleration_duration": acceleration_duration,
                "tail_hex": tail.hex(),
            },
        )
    return Bullet(
        bx,
        by,
        vx,
        vy,
        size_x / 2.0,
        size_y / 2.0,
        state,
        ex_flags=ex_flags,
        acceleration=math.hypot(ax, ay) + abs(accel_speed),
        speed=speed,
        turn_speed=turn_speed,
        acceleration_x=ax,
        acceleration_y=ay,
        angle=angle,
        direction_rotation=direction_rotation,
        timer=timer,
        timer_float=timer + timer_subframe,
        acceleration_duration=acceleration_duration,
        direction_interval=direction_interval,
        direction_num_times=direction_num_times,
        direction_max_times=direction_max_times,
        curve_speed_acceleration=accel_speed,
        curve_angular_velocity=curve_angular_velocity,
        slot=slot,
    )


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
        # SYNCHRONIZE is required to verify TerminateProcess completion with
        # WaitForSingleObject during trial cleanup.
        self.handle = self.kernel32.OpenProcess(PROCESS_ACCESS, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.pid = pid
        self.ecl_instruction_cache: dict[int, EclInstruction] = {}
        self.ecl_cache_stage: int | None = None
        self.ecl_subroutines: tuple[int, ...] = ()

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

    def read_ecl_instruction(self, address: int) -> EclInstruction:
        cached = self.ecl_instruction_cache.get(address)
        if cached is not None:
            return cached
        if not 0x10000 <= address < 0x80000000:
            raise RuntimeError(f"invalid ECL instruction pointer 0x{address:08X}")
        header = self.read(address, 12)
        instruction_time, opcode, offset_to_next = struct.unpack_from(
            "<ihh", header
        )
        if instruction_time < 0:
            raw = header
        elif not 12 <= offset_to_next <= 4096:
            raise RuntimeError(f"invalid ECL instruction size at 0x{address:08X}")
        else:
            raw = self.read(address, offset_to_next)
        instruction = EclInstruction(
            address,
            instruction_time,
            opcode,
            offset_to_next,
            header[9],
            raw.hex(),
        )
        self.ecl_instruction_cache[address] = instruction
        return instruction


def _read_ecl_program(
    process: NativeProcess,
    start_address: int,
) -> tuple[EclInstruction, ...]:
    """Capture a bounded immutable instruction graph, including jump targets."""
    pending = [start_address]
    found: dict[int, EclInstruction] = {}
    while pending and len(found) < ECL_PROGRAM_INSTRUCTION_LIMIT:
        address = pending.pop()
        if not address or address in found:
            continue
        instruction = process.read_ecl_instruction(address)
        found[address] = instruction
        if instruction.time < 0:
            continue
        pending.append(address + instruction.offset_to_next)
        if instruction.opcode in (2, 3, 29, 30, 31, 32, 33, 34):
            raw = bytes.fromhex(instruction.raw_hex)
            jump_offset = struct.unpack_from("<i", raw, 0x10)[0]
            pending.append(address + jump_offset)
        if instruction.opcode == 35 or 37 <= instruction.opcode <= 42:
            raw = bytes.fromhex(instruction.raw_hex)
            sub_id = struct.unpack_from("<i", raw, 0x0C)[0]
            if not 0 <= sub_id < len(process.ecl_subroutines):
                raise RuntimeError(f"invalid ECL subroutine id {sub_id}")
            pending.append(process.ecl_subroutines[sub_id])
        if instruction.opcode in (108, 109, 114, 116):
            raw = bytes.fromhex(instruction.raw_hex)
            sub_id = struct.unpack_from("<i", raw, 0x0C)[0]
            if not 0 <= sub_id < len(process.ecl_subroutines):
                raise RuntimeError(f"invalid ECL callback subroutine id {sub_id}")
            pending.append(process.ecl_subroutines[sub_id])
    return tuple(found[address] for address in sorted(found))


def _read_ecl_subroutines(process: NativeProcess) -> tuple[int, ...]:
    ecl_file, sub_table = struct.unpack(
        "<II", process.read(ADDR_ECL_MANAGER, 8)
    )
    if not ecl_file or not sub_table:
        return ()
    sub_count = struct.unpack("<h", process.read(ecl_file, 2))[0]
    if not 0 <= sub_count <= ECL_SUBROUTINE_LIMIT:
        raise RuntimeError(f"invalid ECL subroutine count {sub_count}")
    addresses = struct.unpack(
        "<" + "I" * sub_count,
        process.read(sub_table, sub_count * 4),
    ) if sub_count else ()
    if any(not 0x10000 <= address < 0x80000000 for address in addresses):
        raise RuntimeError("invalid ECL subroutine pointer")
    return tuple(addresses)


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


def _read_snapshot_once(process: NativeProcess) -> Snapshot:
    game = process.read(ADDR_GAME_MANAGER + GAME_FLAGS_OFFSET, GAME_STAGE_OFFSET + 4 - GAME_FLAGS_OFFSET)
    game_menu, retry_menu, gameplay_active, _completed, _practice, demo_mode = game[0:6]
    # Despite its name, GameManager::OnUpdate sets isInMenu=1 during normal
    # gameplay and 0 while its pause/retry menu breaks the calc chain.
    in_menu = bool(game_menu or retry_menu or not gameplay_active or demo_mode)
    frame = struct.unpack_from("<I", game, GAME_FRAMES_OFFSET - GAME_FLAGS_OFFSET)[0]
    stage = struct.unpack_from("<i", game, GAME_STAGE_OFFSET - GAME_FLAGS_OFFSET)[0]
    if process.ecl_cache_stage != stage:
        process.ecl_instruction_cache.clear()
        process.ecl_cache_stage = stage
        process.ecl_subroutines = _read_ecl_subroutines(process)
    difficulty = struct.unpack(
        "<i", process.read(ADDR_GAME_MANAGER + GAME_DIFFICULTY_OFFSET, 4)
    )[0]
    rank = struct.unpack(
        "<i", process.read(ADDR_GAME_MANAGER + GAME_RANK_OFFSET, 4)
    )[0]
    rng_seed, rng_generation = struct.unpack(
        "<HxxI", process.read(ADDR_RNG, 8)
    )
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
    despawning_bullets: list[Bullet] = []
    bullet_read_retries = 0
    for index in range(BULLET_COUNT):
        base = index * BULLET_STRIDE
        tail = bytes(pool[base + BULLET_SIZE_OFFSET : base + BULLET_STRIDE])
        for attempt in range(4):
            try:
                bullet = _decode_bullet_tail(tail, index)
                break
            except NativeDecodeError as error:
                if attempt == 3:
                    error.evidence["read_retries"] = attempt
                    raise
                # SpawnSingleBullet publishes state before the collision size,
                # position, and velocity. Re-read this exact tail until that
                # short source-defined publication window has closed.
                tail = process.read(
                    ADDR_BULLET_ARRAY + base + BULLET_SIZE_OFFSET,
                    BULLET_STRIDE - BULLET_SIZE_OFFSET,
                )
                bullet_read_retries += 1
        if bullet is None:
            continue
        if bullet.state == 5:
            despawning_bullets.append(bullet)
        else:
            bullets.append(bullet)

    laser_base = ADDR_LASER_ARRAY - ADDR_BULLET_ARRAY
    lasers: list[Laser] = []
    for index in range(LASER_COUNT):
        base = laser_base + index * LASER_STRIDE
        if not struct.unpack_from("<i", pool, base + LASER_IN_USE_OFFSET)[0]:
            continue
        lx, ly = struct.unpack_from("<ff", pool, base + LASER_POSITION_OFFSET)
        angle, start_offset, end_offset, start_length, width, laser_speed = struct.unpack_from(
            "<ffffff", pool, base + LASER_ANGLE_OFFSET
        )
        start_time, hitbox_start_time, duration, despawn_duration, hitbox_end_delay = struct.unpack_from(
            "<iiiii", pool, base + LASER_START_TIME_OFFSET
        )
        timer_subframe = struct.unpack_from("<f", pool, base + LASER_TIMER_SUBFRAME_OFFSET)[0]
        timer = struct.unpack_from("<i", pool, base + LASER_TIMER_OFFSET)[0]
        flags = struct.unpack_from("<H", pool, base + LASER_FLAGS_OFFSET)[0]
        state = pool[base + LASER_STATE_OFFSET]
        laser_numbers = (
            lx,
            ly,
            angle,
            start_offset,
            end_offset,
            start_length,
            width,
            laser_speed,
            timer_subframe,
        )
        laser_times = (
            start_time,
            hitbox_start_time,
            duration,
            despawn_duration,
            hitbox_end_delay,
            timer,
        )
        if (
            not all(math.isfinite(value) for value in laser_numbers)
            or not 0.0 < width <= 1024.0
            or not 0.0 <= start_length <= 4096.0
            or not all(0 <= value < 10_000_000 for value in laser_times)
            or state not in (0, 1, 2)
        ):
            raise RuntimeError(f"invalid laser state at slot {index}")
        lasers.append(
            Laser(
                lx,
                ly,
                angle,
                start_offset,
                end_offset,
                start_length,
                width,
                laser_speed,
                start_time,
                hitbox_start_time,
                duration,
                despawn_duration,
                hitbox_end_delay,
                timer,
                timer + timer_subframe,
                flags,
                state,
                slot=index,
            )
        )

    # EnemyManager ends exactly at its separately mapped calc-chain global:
    # 0x4B79C8 + 0xEE5EC == 0x5A5FB4. The source layout puts the 256 runtime
    # slots after two archive pointers and one 0xEC8-byte template.
    enemy_pool = process.read(
        ADDR_ENEMY_MANAGER + ENEMY_ARRAY_OFFSET,
        ENEMY_COUNT * ENEMY_STRIDE,
    )
    bullet_templates = process.read(
        ADDR_BULLET_MANAGER,
        BULLET_TEMPLATE_COUNT * BULLET_TEMPLATE_STRIDE,
    )
    bullet_sizes = tuple(
        tuple(
            value / 2.0 for value in struct.unpack_from(
                "<ff",
                bullet_templates,
                index * BULLET_TEMPLATE_STRIDE + BULLET_TEMPLATE_SIZE_OFFSET,
            )
        )
        for index in range(BULLET_TEMPLATE_COUNT)
    )
    ex_function_addresses = struct.unpack(
        "<" + "I" * ECL_EX_COUNT,
        process.read(ADDR_ECL_EX_TABLE, ECL_EX_COUNT * 4),
    )
    ex_index_by_address = {
        address: index for index, address in enumerate(ex_function_addresses)
    }
    enemies: list[EnemyBody] = []
    spawners: list[EnemySpawner] = []
    for index in range(ENEMY_COUNT):
        base = index * ENEMY_STRIDE
        flags0, flags1, flags2 = struct.unpack_from(
            "<BBB", enemy_pool, base + ENEMY_FLAGS_OFFSET
        )
        if not flags0 & 0x80:
            continue
        ex, ey = struct.unpack_from("<ff", enemy_pool, base + ENEMY_POSITION_OFFSET)
        velocity_x, velocity_y = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_AXIS_SPEED_OFFSET
        )
        angle, angular_velocity, enemy_speed, enemy_acceleration = struct.unpack_from(
            "<ffff", enemy_pool, base + ENEMY_ANGLE_OFFSET
        )
        move_interp_x, move_interp_y = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_MOVE_INTERP_OFFSET
        )
        move_start_x, move_start_y = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_MOVE_START_OFFSET
        )
        move_subframe = struct.unpack_from(
            "<f", enemy_pool, base + ENEMY_MOVE_TIMER_SUBFRAME_OFFSET
        )[0]
        move_timer = struct.unpack_from(
            "<i", enemy_pool, base + ENEMY_MOVE_TIMER_OFFSET
        )[0]
        move_start_time = struct.unpack_from(
            "<i", enemy_pool, base + ENEMY_MOVE_START_TIME_OFFSET
        )[0]
        movement_mode = flags0 & 0x03
        movement_ease = (flags0 >> 2) & 0x07
        motion_numbers = (
            ex,
            ey,
            velocity_x,
            velocity_y,
            angle,
            angular_velocity,
            enemy_speed,
            enemy_acceleration,
            move_interp_x,
            move_interp_y,
            move_start_x,
            move_start_y,
            move_subframe,
        )
        if (
            not all(math.isfinite(value) for value in motion_numbers)
            or movement_mode == 2 and (
                movement_ease > 4 or move_start_time <= 0 or move_timer < 0
            )
        ):
            raise RuntimeError(f"invalid occupied enemy motion at slot {index}")
        motion = (
            ex,
            ey,
            velocity_x,
            velocity_y,
            angle,
            angular_velocity,
            enemy_speed,
            enemy_acceleration,
            movement_mode,
            movement_ease,
            bool(flags0 & 0x40),
            move_interp_x,
            move_interp_y,
            move_start_x,
            move_start_y,
            move_timer,
            move_timer + move_subframe,
            move_start_time,
        )
        lethal = (
            flags1 & 0x01
            and flags1 & 0x02
            and flags1 & 0x04
            and not flags2 & 0x08
        )
        hitbox_x, hitbox_y = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_HITBOX_OFFSET
        )
        lower_move_x, lower_move_y = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_LOWER_MOVE_LIMIT_OFFSET
        )
        upper_move_x, upper_move_y = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_UPPER_MOVE_LIMIT_OFFSET
        )
        if (
            not math.isfinite(hitbox_x)
            or not math.isfinite(hitbox_y)
            or not 0.0 <= hitbox_x <= 1024.0
            or not 0.0 <= hitbox_y <= 1024.0
        ):
            raise RuntimeError(
                f"invalid occupied enemy geometry at slot {index}"
            )
        if flags2 & 0x01 and (
            not all(math.isfinite(value) for value in (
                lower_move_x, lower_move_y, upper_move_x, upper_move_y
            ))
            or lower_move_x > upper_move_x
            or lower_move_y > upper_move_y
        ):
            raise RuntimeError(
                f"invalid occupied enemy move bounds at slot {index}"
            )
        if lethal:
            enemies.append(EnemyBody(
                ex,
                ey,
                hitbox_x / 3.0,
                hitbox_y / 3.0,
                *motion[2:],
            ))

        life = struct.unpack_from("<i", enemy_pool, base + ENEMY_LIFE_OFFSET)[0]
        boss_timer_subframe = struct.unpack_from(
            "<f", enemy_pool, base + ENEMY_BOSS_TIMER_SUBFRAME_OFFSET
        )[0]
        boss_timer = struct.unpack_from(
            "<i", enemy_pool, base + ENEMY_BOSS_TIMER_OFFSET
        )[0]
        death_callback_sub = struct.unpack_from(
            "<i", enemy_pool, base + ENEMY_DEATH_CALLBACK_SUB_OFFSET
        )[0]
        (
            life_callback_threshold,
            life_callback_sub,
            timer_callback_threshold,
            timer_callback_sub,
        ) = struct.unpack_from(
            "<iiii", enemy_pool, base + ENEMY_LIFE_CALLBACK_THRESHOLD_OFFSET
        )
        bullet_rank_speed_low, bullet_rank_speed_high = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_BULLET_RANK_SPEED_LOW_OFFSET
        )
        (
            bullet_rank_amount1_low,
            bullet_rank_amount1_high,
            bullet_rank_amount2_low,
            bullet_rank_amount2_high,
        ) = struct.unpack_from(
            "<hhhh", enemy_pool, base + ENEMY_BULLET_RANK_AMOUNT1_LOW_OFFSET
        )
        interval = struct.unpack_from(
            "<i", enemy_pool, base + ENEMY_SHOOT_INTERVAL_OFFSET
        )[0]
        shooting_disabled = bool(flags0 & 0x20)
        shoot_offset_x, shoot_offset_y = struct.unpack_from(
            "<ff", enemy_pool, base + ENEMY_SHOOT_OFFSET
        )
        props = base + ENEMY_BULLET_PROPS_OFFSET
        sprite = struct.unpack_from("<h", enemy_pool, props)[0]
        angle1, angle2, speed1, speed2 = struct.unpack_from(
            "<ffff", enemy_pool, props + 0x10
        )
        ex_floats = struct.unpack_from("<ffff", enemy_pool, props + 0x20)
        ex_ints = struct.unpack_from("<iiii", enemy_pool, props + 0x30)
        count1, count2, aim_mode = struct.unpack_from(
            "<hhH", enemy_pool, props + 0x44
        )
        bullet_flags = struct.unpack_from("<I", enemy_pool, props + 0x4C)[0]
        shoot_subframe = struct.unpack_from(
            "<f", enemy_pool, base + ENEMY_SHOOT_TIMER_SUBFRAME_OFFSET
        )[0]
        shoot_timer = struct.unpack_from(
            "<i", enemy_pool, base + ENEMY_SHOOT_TIMER_OFFSET
        )[0]
        pattern_numbers = (
            shoot_offset_x,
            shoot_offset_y,
            angle1,
            angle2,
            speed1,
            speed2,
            *ex_floats,
            shoot_subframe,
        )
        props_valid = (
            all(math.isfinite(value) for value in pattern_numbers)
            and 0 <= sprite < BULLET_TEMPLATE_COUNT
            and 0 <= aim_mode <= 8
            and 0 < count1 <= BULLET_COUNT
            and 0 < count2 <= BULLET_COUNT
            and count1 * count2 <= BULLET_COUNT
        )
        active_periodic = life > 0 and interval > 0 and not shooting_disabled
        if (
            (active_periodic and not props_valid)
            or not -10_000_000 < interval < 10_000_000
            or not 0 <= shoot_timer < 10_000_000
            or active_periodic and shoot_timer > interval
            or not 0.0 <= shoot_subframe < 1.0
        ):
            raise RuntimeError(
                f"invalid periodic bullet shooter at enemy slot {index}"
            )
        bullet_pattern = None
        if props_valid:
            template = sprite * BULLET_TEMPLATE_STRIDE
            bullet_half_width, bullet_half_height = bullet_sizes[sprite]
            if (
                not math.isfinite(bullet_half_width)
                or not math.isfinite(bullet_half_height)
                or not 0.0 < bullet_half_width <= 256.0
                or not 0.0 < bullet_half_height <= 256.0
            ):
                if active_periodic:
                    raise RuntimeError(
                        f"invalid bullet template {sprite} for enemy slot {index}"
                    )
            else:
                bullet_pattern = BulletPattern(
                    sprite,
                    angle1,
                    angle2,
                    speed1,
                    speed2,
                    tuple(ex_floats),
                    tuple(ex_ints),
                    count1,
                    count2,
                    aim_mode,
                    bullet_flags,
                    bullet_half_width,
                    bullet_half_height,
                )

        def decode_ecl_context(offset: int) -> EnemyEclContext:
            instruction_address = struct.unpack_from(
                "<I", enemy_pool, offset
            )[0]
            subframe = struct.unpack_from("<f", enemy_pool, offset + 0x08)[0]
            current_time = struct.unpack_from("<i", enemy_pool, offset + 0x0C)[0]
            repeat_function = struct.unpack_from(
                "<I", enemy_pool, offset + 0x10
            )[0]
            integers = (
                *struct.unpack_from("<iiii", enemy_pool, offset + 0x14),
                *struct.unpack_from("<iiii", enemy_pool, offset + 0x34),
            )
            floats = struct.unpack_from("<ffff", enemy_pool, offset + 0x24)
            compare = struct.unpack_from("<i", enemy_pool, offset + 0x44)[0]
            if (
                not math.isfinite(subframe)
                or not 0.0 <= subframe < 1.0
                or not all(math.isfinite(value) for value in floats)
            ):
                raise RuntimeError(f"invalid ECL context at enemy slot {index}")
            repeat_index = (
                ex_index_by_address.get(repeat_function, -1)
                if repeat_function
                else None
            )
            return EnemyEclContext(
                instruction_address,
                current_time,
                current_time + subframe,
                tuple(integers),
                tuple(floats),
                compare,
                repeat_index,
            )

        context = base + ENEMY_ECL_CONTEXT_OFFSET
        current_context = decode_ecl_context(context)
        stack_depth = struct.unpack_from(
            "<i", enemy_pool, base + ENEMY_ECL_STACK_DEPTH_OFFSET
        )[0]
        if not 0 <= stack_depth <= ENEMY_ECL_STACK_CAPACITY:
            raise RuntimeError(f"invalid ECL stack depth at enemy slot {index}")
        ecl_stack = tuple(
            decode_ecl_context(
                context + ENEMY_ECL_CONTEXT_SIZE * (stack_index + 1)
            )
            for stack_index in range(stack_depth)
        )
        current_instruction_address = current_context.instruction_address
        ecl_time = current_context.time
        ecl_subframe = current_context.time_float - current_context.time
        ecl_ints = current_context.ints
        ecl_floats = current_context.floats
        ecl_compare = current_context.compare
        repeat_ex_index = current_context.repeat_ex_index
        next_instruction = None
        ecl_program = ()
        if current_instruction_address:
            next_instruction = process.read_ecl_instruction(
                current_instruction_address
            )
            ecl_program = _read_ecl_program(
                process, current_instruction_address
            )
        program_by_address = {
            instruction.address: instruction for instruction in ecl_program
        }
        for saved_context in ecl_stack:
            if saved_context.instruction_address:
                for instruction in _read_ecl_program(
                    process, saved_context.instruction_address
                ):
                    program_by_address.setdefault(
                        instruction.address, instruction
                    )
        ecl_program = tuple(program_by_address.values())

        spawners.append(EnemySpawner(
            index,
            *motion,
            shoot_offset_x,
            shoot_offset_y,
            bullet_rank_speed_low,
            bullet_rank_speed_high,
            bullet_rank_amount1_low,
            bullet_rank_amount1_high,
            bullet_rank_amount2_low,
            bullet_rank_amount2_high,
            life,
            shooting_disabled,
            interval,
            shoot_timer,
            shoot_timer + shoot_subframe,
            bullet_pattern,
            ecl_time,
            ecl_time + ecl_subframe,
            tuple(ecl_ints),
            tuple(ecl_floats),
            ecl_compare,
            repeat_ex_index,
            next_instruction,
            ecl_program,
            ecl_stack,
            hitbox_x / 3.0,
            hitbox_y / 3.0,
            bool(flags1 & 0x01),
            bool(flags1 & 0x02),
            bool(flags2 & 0x08),
            bool(flags2 & 0x04),
            process.ecl_subroutines,
            lower_move_x,
            lower_move_y,
            upper_move_x,
            upper_move_y,
            bool(flags2 & 0x01),
            boss_timer,
            boss_timer + boss_timer_subframe,
            death_callback_sub,
            life_callback_threshold,
            life_callback_sub,
            timer_callback_threshold,
            timer_callback_sub,
            bool(flags1 & 0x08),
            bool(flags2 & 0x10),
            bool(flags1 & 0x10),
        ))
    return Snapshot(
        frame, stage, player_state, x, y, half_width, half_height,
        normal_speed, focus_speed, normal_diagonal, focus_diagonal,
        frame_multiplier, input_mask, tuple(bullets), len(lasers), in_menu, time_stopped,
        bool(is_replay or demo_mode), tuple(lasers), tuple(enemies),
        tuple(despawning_bullets), bullet_read_retries, tuple(spawners),
        difficulty, rank, bullet_sizes, rng_seed, rng_generation,
    )


def read_snapshot(process: NativeProcess) -> Snapshot:
    """Return one frame-coherent native snapshot or fail closed."""
    observed_epochs = []
    for _attempt in range(8):
        before = read_game_frame(process)
        snapshot = _read_snapshot_once(process)
        after = read_game_frame(process)
        observed_epochs.append((before, snapshot.frame, after))
        if before == snapshot.frame == after:
            return snapshot
    raise NativeDecodeError(
        "native state changed throughout snapshot reads",
        {"observed_epochs": observed_epochs},
    )


def read_game_frame(process: NativeProcess) -> int:
    """Read the source-defined stage frame at the physical command boundary."""
    return struct.unpack(
        "<I", process.read(ADDR_GAME_MANAGER + GAME_FRAMES_OFFSET, 4)
    )[0]


def read_menu_state(process: NativeProcess) -> tuple[int, int, int]:
    block = process.read(
        ADDR_MAIN_MENU + MAIN_MENU_CURSOR_OFFSET,
        MAIN_MENU_TIMER_OFFSET + 4 - MAIN_MENU_CURSOR_OFFSET,
    )
    cursor = struct.unpack_from("<i", block, 0)[0]
    state = struct.unpack_from("<i", block, MAIN_MENU_STATE_OFFSET - MAIN_MENU_CURSOR_OFFSET)[0]
    timer = struct.unpack_from("<i", block, MAIN_MENU_TIMER_OFFSET - MAIN_MENU_CURSOR_OFFSET)[0]
    return state, cursor, timer


def read_supervisor_state(process: NativeProcess) -> tuple[int, int]:
    wanted, current = struct.unpack(
        "<ii", process.read(ADDR_SUPERVISOR + SUPERVISOR_STATES_OFFSET, 8)
    )
    if not 0 <= wanted <= 10 or not 0 <= current <= 10:
        raise RuntimeError(f"invalid Supervisor states: wanted={wanted}, current={current}")
    return wanted, current


def read_result_screen(process: NativeProcess) -> ResultScreenState | None:
    """Find ResultScreen through the source-defined calc chain."""
    pointer = struct.unpack(
        "<I", process.read(ADDR_CHAIN + CHAIN_ROOT_NEXT_OFFSET, 4)
    )[0]
    visited: set[int] = set()
    for _ in range(64):
        if pointer == 0:
            return None
        if pointer in visited or not 0x10000 <= pointer < 0x80000000:
            raise RuntimeError(f"invalid calc-chain pointer: 0x{pointer:08X}")
        visited.add(pointer)
        elem = process.read(pointer, CHAIN_ELEM_SIZE)
        callback = struct.unpack_from("<I", elem, CHAIN_ELEM_CALLBACK_OFFSET)[0]
        if callback == RESULT_SCREEN_ON_UPDATE:
            address = struct.unpack_from("<I", elem, CHAIN_ELEM_ARG_OFFSET)[0]
            if not 0x10000 <= address < 0x80000000:
                raise RuntimeError(f"invalid ResultScreen pointer: 0x{address:08X}")
            block = process.read(address, RESULT_SCREEN_STATE_SIZE)
            frame_timer, state, cursor = struct.unpack_from("<iii", block, 0x4)
            replay_number = struct.unpack_from("<i", block, 0x1C)[0]
            selected_character = struct.unpack_from("<i", block, 0x20)[0]
            if not 0 <= frame_timer < 10_000_000 or not 0 <= state <= 17:
                raise RuntimeError(
                    f"invalid ResultScreen state: timer={frame_timer}, state={state}"
                )
            return ResultScreenState(
                address, frame_timer, state, cursor, replay_number, selected_character
            )
        pointer = struct.unpack_from("<I", elem, CHAIN_ELEM_NEXT_OFFSET)[0]
    raise RuntimeError("calc chain exceeded 64 elements")


def read_dialogue_state(process: NativeProcess) -> tuple[bool, bool]:
    impl = struct.unpack("<I", process.read(ADDR_GUI + 4, 4))[0]
    if impl == 0:
        return False, False
    msg = impl + GUI_IMPL_MSG_OFFSET
    current_index = struct.unpack("<i", process.read(msg + GUI_MSG_INDEX_OFFSET, 4))[0]
    skippable = bool(process.read(msg + GUI_MSG_SKIPPABLE_OFFSET, 1)[0])
    return current_index >= 0, skippable

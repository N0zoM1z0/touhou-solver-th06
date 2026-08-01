"""ctypes bridge to the dense collision kernel."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

from ..hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from ..hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from ..hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from ..model import ACTIONS, SafeAction, Snapshot


class _Aabb(ctypes.Structure):
    _fields_ = (("left", ctypes.c_float), ("top", ctypes.c_float), ("right", ctypes.c_float), ("bottom", ctypes.c_float))


class _LaserHazard(ctypes.Structure):
    _fields_ = (
        ("origin_x", ctypes.c_float),
        ("origin_y", ctypes.c_float),
        ("angle", ctypes.c_float),
        ("center_offset", ctypes.c_float),
        ("size_x", ctypes.c_float),
        ("size_y", ctypes.c_float),
    )


class _SafeResult(ctypes.Structure):
    _fields_ = (
        ("safe", ctypes.c_int32),
        ("clearance", ctypes.c_float),
        ("final_x", ctypes.c_float),
        ("final_y", ctypes.c_float),
    )


class NativeSafetyKernel:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("native TH06 safety kernel requires Windows Python")
        path = Path(__file__).resolve().parents[3] / "build" / "th06_safety.dll"
        if not path.is_file():
            raise RuntimeError("missing build/th06_safety.dll; run ./build_th06_native.sh")
        self.library = ctypes.CDLL(str(path))
        self.function = self.library.th06_certify_actions
        self.function.argtypes = (
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_float,
            ctypes.c_uint16,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_Aabb),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_LaserHazard),
            ctypes.c_float,
            ctypes.POINTER(_SafeResult),
        )
        self.function.restype = ctypes.c_int32

    @staticmethod
    def _flatten(frames, value_type, convert):
        offsets = [0]
        values = []
        for frame in frames:
            values.extend(convert(value) for value in frame)
            offsets.append(len(values))
        offset_array = (ctypes.c_uint32 * len(offsets))(*offsets)
        value_array = (value_type * max(1, len(values)))(*values)
        return offset_array, value_array

    def certify(self, snapshot: Snapshot, horizon: int, collision_margin: float) -> tuple[SafeAction, ...]:
        bullet_frames = bullet_hazards_by_frame(snapshot, horizon)
        enemy_frames = enemy_hazards_by_frame(snapshot.enemies, horizon)
        aabb_frames = tuple(
            bullet_frame + enemy_frame
            for bullet_frame, enemy_frame in zip(bullet_frames, enemy_frames)
        )
        bullet_offsets, bullets = self._flatten(
            aabb_frames,
            _Aabb,
            lambda value: _Aabb(*value),
        )
        laser_offsets, lasers = self._flatten(
            laser_hazards_by_frame(snapshot.lasers, horizon),
            _LaserHazard,
            lambda value: _LaserHazard(
                value.origin_x,
                value.origin_y,
                value.angle,
                value.center_offset,
                value.size_x,
                value.size_y,
            ),
        )
        output = (_SafeResult * len(ACTIONS))()
        status = self.function(
            snapshot.x,
            snapshot.y,
            snapshot.half_width,
            snapshot.half_height,
            snapshot.normal_speed,
            snapshot.focus_speed,
            snapshot.normal_diagonal_speed,
            snapshot.focus_diagonal_speed,
            snapshot.input_mask,
            horizon,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            output,
        )
        if status != 0:
            raise RuntimeError(f"native safety kernel rejected input with status {status}")
        return tuple(
            SafeAction(action, result.clearance, result.final_x, result.final_y)
            for action, result in zip(ACTIONS, output)
            if result.safe
        )

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
            ctypes.POINTER(_SafeResult),
        )
        self.function.restype = ctypes.c_int32
        self.replanning_function = self.library.th06_replanning_scores
        self.replanning_function.argtypes = (
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
            ctypes.c_int32,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_Aabb),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_LaserHazard),
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_int32),
        )
        self.replanning_function.restype = ctypes.c_int32

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

    def _prepare(self, snapshot: Snapshot, horizon: int):
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
        return bullet_offsets, bullets, laser_offsets, lasers

    def _certify_prepared(
        self,
        snapshot: Snapshot,
        horizon: int,
        collision_margin: float,
        prepared,
    ) -> tuple[tuple[SafeAction, ...], tuple[SafeAction, ...]]:
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        output = (_SafeResult * len(ACTIONS))()
        age_zero_output = (_SafeResult * len(ACTIONS))()
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
            age_zero_output,
        )
        if status != 0:
            raise RuntimeError(f"native safety kernel rejected input with status {status}")
        fixed = tuple(
            SafeAction(action, result.clearance, result.final_x, result.final_y)
            for action, result in zip(ACTIONS, output)
            if result.safe
        )
        age_zero = tuple(
            SafeAction(action, result.clearance, result.final_x, result.final_y)
            for action, result in zip(ACTIONS, age_zero_output)
            if result.safe
        )
        return fixed, age_zero

    def certify(self, snapshot: Snapshot, horizon: int, collision_margin: float) -> tuple[SafeAction, ...]:
        return self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare(snapshot, horizon),
        )[0]

    def certify_delivery_sets(
        self,
        snapshot: Snapshot,
        horizon: int,
        collision_margin: float,
    ) -> tuple[tuple[SafeAction, ...], tuple[SafeAction, ...]]:
        return self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare(snapshot, horizon),
        )

    def certify_pair(
        self,
        snapshot: Snapshot,
        hard_horizon: int,
        effort_horizon: int,
        collision_margin: float,
    ) -> tuple[tuple[SafeAction, ...], tuple[SafeAction, ...]]:
        if effort_horizon < hard_horizon:
            raise ValueError("effort horizon cannot be shorter than hard horizon")
        prepared = self._prepare(snapshot, effort_horizon)
        hard, _age_zero = self._certify_prepared(
            snapshot, hard_horizon, collision_margin, prepared
        )
        if not hard or effort_horizon == hard_horizon:
            return hard, hard
        effort, _age_zero = self._certify_prepared(
            snapshot, effort_horizon, collision_margin, prepared
        )
        return hard, effort

    def certify_pair_with_age_zero(
        self,
        snapshot: Snapshot,
        hard_horizon: int,
        effort_horizon: int,
        collision_margin: float,
    ) -> tuple[
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
    ]:
        if effort_horizon < hard_horizon:
            raise ValueError("effort horizon cannot be shorter than hard horizon")
        prepared = self._prepare(snapshot, effort_horizon)
        hard, age_zero = self._certify_prepared(
            snapshot, hard_horizon, collision_margin, prepared
        )
        if not hard or effort_horizon == hard_horizon:
            return hard, hard, age_zero
        effort, _age_zero = self._certify_prepared(
            snapshot, effort_horizon, collision_margin, prepared
        )
        return hard, effort, age_zero

    def last_viable_frontier(
        self,
        snapshot: Snapshot,
        minimum_horizon: int,
        maximum_horizon: int,
        collision_margin: float,
    ) -> tuple[SafeAction, ...]:
        """Find the longest nonempty constant-action set with one hazard build."""
        if maximum_horizon < minimum_horizon:
            return ()
        prepared = self._prepare(snapshot, maximum_horizon)
        for horizon in range(maximum_horizon, minimum_horizon - 1, -1):
            certified, _age_zero = self._certify_prepared(
                snapshot,
                horizon,
                collision_margin,
                prepared,
            )
            if certified:
                return certified
        return ()

    def replanning_scores(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        split: int,
        horizon: int,
        collision_margin: float,
    ):
        prepared = self._prepare(snapshot, horizon)
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(ACTIONS)
            if action in candidate_actions
        )
        output = (ctypes.c_int32 * len(ACTIONS))()
        status = self.replanning_function(
            snapshot.x,
            snapshot.y,
            snapshot.half_width,
            snapshot.half_height,
            snapshot.normal_speed,
            snapshot.focus_speed,
            snapshot.normal_diagonal_speed,
            snapshot.focus_diagonal_speed,
            snapshot.input_mask,
            split,
            horizon,
            candidate_mask,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            output,
        )
        if status != 0:
            raise RuntimeError(
                f"native replanning kernel rejected input with status {status}"
            )
        return {
            action: output[index]
            for index, action in enumerate(ACTIONS)
            if action in candidate_actions
        }

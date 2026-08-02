"""ctypes bridge to the dense collision kernel."""

from __future__ import annotations

import ctypes
import os
from array import array
from dataclasses import replace
from pathlib import Path

from ..hazards.bullets import hazards_by_frame as bullet_hazards_by_frame
from ..hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from ..hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from ..hazards.world import forecast_world_births
from ..guidance import TerminalGuidance
from ..model import (
    ACTIONS,
    CONTROL_ACTIONS,
    Action,
    SafeAction,
    Snapshot,
    action_from_input,
)
from ..safety import _action_mask, candidate_path


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
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_Aabb),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_LaserHazard),
            ctypes.c_float,
            ctypes.POINTER(_SafeResult),
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
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_Aabb),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_LaserHazard),
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_int32),
        )
        self.replanning_function.restype = ctypes.c_int32
        self.nominal_function = self.library.th06_nominal_policy_counts
        self.nominal_function.argtypes = self.replanning_function.argtypes
        self.nominal_function.restype = ctypes.c_int32
        self.guidance_function = self.library.th06_terminal_guidance
        self.guidance_function.argtypes = (
            *self.replanning_function.argtypes[:-1],
            ctypes.c_float,
            ctypes.c_float,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        )
        self.guidance_function.restype = ctypes.c_int32
        self._prepared_snapshot: Snapshot | None = None
        self._prepared_horizon = 0
        self._prepared_hazards = None

    @staticmethod
    def _flatten(frames, value_type, convert):
        offsets = [0]
        coordinates = array("f")
        count = 0
        for frame in frames:
            count += len(frame)
            offsets.append(count)
            for value in frame:
                coordinates.extend(convert(value))
        offset_array = (ctypes.c_uint32 * len(offsets))(*offsets)
        value_array_type = value_type * max(1, count)
        value_array = (
            value_array_type.from_buffer_copy(coordinates)
            if count
            else value_array_type()
        )
        return offset_array, value_array

    def _prepare_window(
        self,
        snapshot: Snapshot,
        start_frame: int,
        horizon: int,
    ):
        total_horizon = start_frame + horizon
        bullet_frames = bullet_hazards_by_frame(snapshot, total_horizon)[
            start_frame:
        ]
        enemy_frames = enemy_hazards_by_frame(snapshot.enemies, total_horizon)[
            start_frame:
        ]
        hard_births = forecast_world_births(
            snapshot,
            ((snapshot.x, snapshot.y),) * min(4, total_horizon),
        )
        nominal_births = forecast_world_births(
            snapshot,
            ((snapshot.x, snapshot.y),) * total_horizon,
            rng_mode="nominal",
        )
        uncovered = ((-10000.0, -10000.0, 10000.0, 10000.0),)
        birth_frames = tuple(
            (
                hard_births.hazards[index]
                if index < hard_births.covered_frames
                else uncovered
            )
            if index < 4
            else (
                nominal_births.hazards[index]
                if index < nominal_births.covered_frames
                else ()
            )
            for index in range(start_frame, total_horizon)
        )
        forecast_body_frames = tuple(
            (
                hard_births.body_hazards[index]
                if index < hard_births.covered_frames
                and hard_births.body_hazards
                else uncovered
            )
            if index < 4
            else (
                nominal_births.body_hazards[index]
                if index < nominal_births.covered_frames
                and nominal_births.body_hazards
                else ()
            )
            for index in range(start_frame, total_horizon)
        )
        aabb_frames = tuple(
            bullet_frame + enemy_frame + birth_frame + body_frame
            for bullet_frame, enemy_frame, birth_frame, body_frame in zip(
                bullet_frames,
                enemy_frames,
                birth_frames,
                forecast_body_frames,
            )
        )
        bullet_offsets, bullets = self._flatten(
            aabb_frames,
            _Aabb,
            lambda value: value,
        )
        laser_offsets, lasers = self._flatten(
            laser_hazards_by_frame(snapshot.lasers, total_horizon)[start_frame:],
            _LaserHazard,
            lambda value: (
                value.origin_x,
                value.origin_y,
                value.angle,
                value.center_offset,
                value.size_x,
                value.size_y,
            ),
        )
        return bullet_offsets, bullets, laser_offsets, lasers

    def _prepare(self, snapshot: Snapshot, horizon: int):
        return self._prepare_window(snapshot, 0, horizon)

    def _prepare_reusable(self, snapshot: Snapshot, horizon: int):
        if (
            self._prepared_snapshot is snapshot
            and self._prepared_horizon >= horizon
        ):
            return self._prepared_hazards
        prepared = self._prepare(snapshot, horizon)
        self._prepared_snapshot = snapshot
        self._prepared_horizon = horizon
        self._prepared_hazards = prepared
        return prepared

    def prepare(self, snapshot: Snapshot, horizon: int) -> None:
        """Prepare one shared soft window before progressive frontier scans."""
        self._prepare_reusable(snapshot, horizon)

    def _certify_prepared(
        self,
        snapshot: Snapshot,
        horizon: int,
        collision_margin: float,
        prepared,
        candidate_mask: int = (1 << len(ACTIONS)) - 1,
        include_extended: bool = False,
    ) -> tuple[
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
    ]:
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        output = (_SafeResult * len(CONTROL_ACTIONS))()
        age_zero_output = (_SafeResult * len(CONTROL_ACTIONS))()
        extended_output = (_SafeResult * len(CONTROL_ACTIONS))()
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
            candidate_mask,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            output,
            age_zero_output,
            extended_output if include_extended else None,
        )
        if status != 0:
            raise RuntimeError(f"native safety kernel rejected input with status {status}")
        fixed = tuple(
            SafeAction(action, result.clearance, result.final_x, result.final_y)
            for action, result in zip(CONTROL_ACTIONS, output)
            if result.safe
        )
        age_zero = tuple(
            SafeAction(action, result.clearance, result.final_x, result.final_y)
            for action, result in zip(CONTROL_ACTIONS, age_zero_output)
            if result.safe
        )
        extended = tuple(
            SafeAction(action, result.clearance, result.final_x, result.final_y)
            for action, result in zip(CONTROL_ACTIONS, extended_output)
            if result.safe
        )
        return fixed, age_zero, extended

    def certify(self, snapshot: Snapshot, horizon: int, collision_margin: float) -> tuple[SafeAction, ...]:
        return self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare_reusable(snapshot, horizon),
        )[0]

    def certify_selected(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
        collision_margin: float,
    ) -> tuple[SafeAction, ...]:
        selected = frozenset(actions)
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in selected
        )
        if not candidate_mask:
            return ()
        return self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare_reusable(snapshot, horizon),
            candidate_mask,
        )[0]

    def certify_selected_extended_delivery(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
        collision_margin: float,
    ) -> tuple[SafeAction, ...]:
        selected = frozenset(actions)
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in selected
        )
        if not candidate_mask:
            return ()
        return self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare_reusable(snapshot, horizon),
            candidate_mask,
            include_extended=True,
        )[2]

    def certify_selected_pair(
        self,
        snapshot: Snapshot,
        hard_horizon: int,
        effort_horizon: int,
        actions: tuple[Action, ...],
        collision_margin: float,
    ) -> tuple[tuple[SafeAction, ...], tuple[SafeAction, ...]]:
        if effort_horizon < hard_horizon:
            raise ValueError("effort horizon cannot be shorter than hard horizon")
        selected = frozenset(actions)
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in selected
        )
        if not candidate_mask:
            return (), ()
        prepared = self._prepare_reusable(snapshot, effort_horizon)
        hard = self._certify_prepared(
            snapshot,
            hard_horizon,
            collision_margin,
            prepared,
            candidate_mask,
        )[0]
        effort = self._certify_prepared(
            snapshot,
            effort_horizon,
            collision_margin,
            prepared,
            candidate_mask,
        )[0]
        return hard, effort

    def longest_selected_horizon(
        self,
        snapshot: Snapshot,
        minimum_horizon: int,
        maximum_horizon: int,
        actions: tuple[Action, ...],
        collision_margin: float,
    ) -> int:
        if minimum_horizon > maximum_horizon:
            return 0
        selected = frozenset(actions)
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in selected
        )
        if not candidate_mask:
            return 0
        prepared = self._prepare_reusable(snapshot, maximum_horizon)
        for horizon in range(maximum_horizon, minimum_horizon - 1, -1):
            if self._certify_prepared(
                snapshot,
                horizon,
                collision_margin,
                prepared,
                candidate_mask,
            )[0]:
                return horizon
        return 0

    def certify_delivery_sets_with_selected(
        self,
        snapshot: Snapshot,
        hard_horizon: int,
        selected_horizon: int,
        actions: tuple[Action, ...],
        collision_margin: float,
    ) -> tuple[
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
    ]:
        if selected_horizon < hard_horizon:
            raise ValueError("selected horizon must cover the hard horizon")
        selected = frozenset(actions)
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in selected
        )
        prepared = self._prepare_reusable(snapshot, selected_horizon)
        hard, age_zero, _extended = self._certify_prepared(
            snapshot,
            hard_horizon,
            collision_margin,
            prepared,
        )
        selected_safe = (
            self._certify_prepared(
                snapshot,
                selected_horizon,
                collision_margin,
                prepared,
                candidate_mask,
            )[0]
            if candidate_mask
            else ()
        )
        return hard, age_zero, selected_safe

    def certify_delivery_sets(
        self,
        snapshot: Snapshot,
        horizon: int,
        collision_margin: float,
    ) -> tuple[tuple[SafeAction, ...], tuple[SafeAction, ...]]:
        hard, age_zero, _extended = self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare(snapshot, horizon),
        )
        return hard, age_zero

    def certify_selected_delivery_sets(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
        collision_margin: float,
    ) -> tuple[tuple[SafeAction, ...], tuple[SafeAction, ...]]:
        selected = frozenset(actions)
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in selected
        )
        hard, age_zero, _extended = self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare_reusable(snapshot, horizon),
            candidate_mask,
        )
        return hard, age_zero

    def certify_pair(
        self,
        snapshot: Snapshot,
        hard_horizon: int,
        effort_horizon: int,
        collision_margin: float,
    ) -> tuple[tuple[SafeAction, ...], tuple[SafeAction, ...]]:
        if effort_horizon < hard_horizon:
            raise ValueError("effort horizon cannot be shorter than hard horizon")
        prepared = self._prepare_reusable(snapshot, effort_horizon)
        hard, _age_zero, _extended = self._certify_prepared(
            snapshot, hard_horizon, collision_margin, prepared
        )
        if not hard or effort_horizon == hard_horizon:
            return hard, hard
        effort, _age_zero, _extended = self._certify_prepared(
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
        prepared = self._prepare_reusable(snapshot, effort_horizon)
        hard, age_zero, _extended = self._certify_prepared(
            snapshot, hard_horizon, collision_margin, prepared
        )
        if not hard or effort_horizon == hard_horizon:
            return hard, hard, age_zero
        effort, _age_zero, _extended = self._certify_prepared(
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
        prepared = self._prepare_reusable(snapshot, maximum_horizon)
        for horizon in range(maximum_horizon, minimum_horizon - 1, -1):
            certified, _age_zero, _extended = self._certify_prepared(
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
        prepared = self._prepare_reusable(snapshot, horizon)
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        output = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
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
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        }

    def nominal_policy_counts(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
    ):
        prepared = self._prepare_reusable(snapshot, horizon)
        return self._nominal_policy_counts_prepared(
            snapshot,
            candidates,
            segment_length,
            horizon,
            collision_margin,
            prepared,
        )

    def terminal_guidance(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
        target: tuple[float, float] | None = None,
    ) -> dict[Action, TerminalGuidance]:
        """Return unique terminal volume and target values on one snapshot."""
        bullet_offsets, bullets, laser_offsets, lasers = (
            self._prepare_reusable(snapshot, horizon)
        )
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        terminal_counts = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        free_clearances = (ctypes.c_float * len(CONTROL_ACTIONS))()
        free_x = (ctypes.c_float * len(CONTROL_ACTIONS))()
        free_y = (ctypes.c_float * len(CONTROL_ACTIONS))()
        target_distances = (ctypes.c_float * len(CONTROL_ACTIONS))()
        target_x, target_y = target or (snapshot.x, snapshot.y)
        status = self.guidance_function(
            snapshot.x,
            snapshot.y,
            snapshot.half_width,
            snapshot.half_height,
            snapshot.normal_speed,
            snapshot.focus_speed,
            snapshot.normal_diagonal_speed,
            snapshot.focus_diagonal_speed,
            snapshot.input_mask,
            segment_length,
            horizon,
            candidate_mask,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            target_x,
            target_y,
            terminal_counts,
            free_clearances,
            free_x,
            free_y,
            target_distances,
        )
        if status != 0:
            raise RuntimeError(
                f"native terminal guidance rejected input with status {status}"
            )
        return {
            action: TerminalGuidance(
                terminal_count=terminal_counts[index],
                free_clearance=free_clearances[index],
                free_x=free_x[index],
                free_y=free_y[index],
                target_distance_squared=target_distances[index],
            )
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        }

    def nominal_policy_counts_ahead(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        ahead_frames: int,
        collision_margin: float,
        assumed_action: Action | None = None,
        delivery_delay: int = 0,
    ):
        return self.nominal_policy_counts_ahead_window(
            snapshot,
            candidates,
            segment_length,
            horizon,
            (ahead_frames,),
            collision_margin,
            assumed_action,
            delivery_delay,
        )[ahead_frames]

    def nominal_policy_counts_ahead_window(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        ahead_frames: tuple[int, ...],
        collision_margin: float,
        assumed_action: Action | None = None,
        delivery_delay: int = 0,
    ):
        if not ahead_frames:
            return {}
        if min(ahead_frames) < 0 or delivery_delay < 0:
            raise ValueError("ahead frames and delivery delay cannot be negative")
        if len(set(ahead_frames)) != len(ahead_frames):
            raise ValueError("ahead frames must be unique")
        current = action_from_input(snapshot.input_mask)
        planned = assumed_action or current
        maximum_ahead = max(ahead_frames)
        prepared = self._prepare_reusable(
            snapshot, maximum_ahead + horizon
        )
        result = {}
        for ahead in ahead_frames:
            x, y = (
                candidate_path(
                    snapshot,
                    planned,
                    delivery_delay,
                    ahead,
                )[-1]
                if ahead
                else (snapshot.x, snapshot.y)
            )
            target_action = planned if ahead > delivery_delay else current
            predicted = replace(
                snapshot,
                frame=snapshot.frame + ahead,
                x=x,
                y=y,
                input_mask=_action_mask(target_action),
            )
            result[ahead] = self._nominal_policy_counts_prepared(
                predicted,
                candidates,
                segment_length,
                horizon,
                collision_margin,
                self._prepared_at_offset(prepared, ahead),
            )
        return result

    @staticmethod
    def _prepared_at_offset(prepared, frame_offset: int):
        if frame_offset == 0:
            return prepared
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        byte_offset = frame_offset * ctypes.sizeof(ctypes.c_uint32)
        return (
            ctypes.cast(
                ctypes.byref(bullet_offsets, byte_offset),
                ctypes.POINTER(ctypes.c_uint32),
            ),
            bullets,
            ctypes.cast(
                ctypes.byref(laser_offsets, byte_offset),
                ctypes.POINTER(ctypes.c_uint32),
            ),
            lasers,
        )

    def _nominal_policy_counts_prepared(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
        prepared,
    ):
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        output = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        status = self.nominal_function(
            snapshot.x,
            snapshot.y,
            snapshot.half_width,
            snapshot.half_height,
            snapshot.normal_speed,
            snapshot.focus_speed,
            snapshot.normal_diagonal_speed,
            snapshot.focus_diagonal_speed,
            snapshot.input_mask,
            segment_length,
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
                f"native nominal policy kernel rejected input with status {status}"
            )
        return {
            action: output[index]
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        }

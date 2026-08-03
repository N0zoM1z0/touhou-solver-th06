"""ctypes bridge to the dense collision kernel."""

from __future__ import annotations

import ctypes
import math
import os
from array import array
from dataclasses import replace
from pathlib import Path

from ..hazards.bullets import (
    extend_hazards_by_frame as extend_bullet_hazards_by_frame,
    hazards_by_frame as bullet_hazards_by_frame,
)
from ..hazards.enemies import hazards_by_frame as enemy_hazards_by_frame
from ..hazards.lasers import hazards_by_frame as laser_hazards_by_frame
from ..hazards.world import (
    extend_nominal_world_births,
    forecast_world_births,
)
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
        self.budgeted_certify_function = (
            self.library.th06_certify_actions_budgeted
        )
        self.budgeted_certify_function.argtypes = (
            *self.function.argtypes[:-3],
            ctypes.c_double,
            *self.function.argtypes[-3:],
        )
        self.budgeted_certify_function.restype = ctypes.c_int32
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
        self.macro_tail_function = (
            self.library.th06_macro_tail_scores_budgeted
        )
        self.macro_tail_function.argtypes = (
            *self.replanning_function.argtypes[:-1],
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_int32),
        )
        self.macro_tail_function.restype = ctypes.c_int32
        self.nominal_function = self.library.th06_nominal_policy_counts
        self.nominal_function.argtypes = self.replanning_function.argtypes
        self.nominal_function.restype = ctypes.c_int32
        self.budgeted_nominal_function = (
            self.library.th06_nominal_policy_counts_budgeted
        )
        self.budgeted_nominal_function.argtypes = (
            *self.replanning_function.argtypes[:-1],
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_int32),
        )
        self.budgeted_nominal_function.restype = ctypes.c_int32
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
        self.budgeted_guidance_function = (
            self.library.th06_terminal_guidance_budgeted
        )
        self.budgeted_guidance_function.argtypes = (
            *self.guidance_function.argtypes[:-5],
            ctypes.c_double,
            *self.guidance_function.argtypes[-5:],
        )
        self.budgeted_guidance_function.restype = ctypes.c_int32
        self.counts_function = self.library.th06_terminal_counts
        self.counts_function.argtypes = (
            *self.replanning_function.argtypes[:-1],
            ctypes.POINTER(ctypes.c_int32),
        )
        self.counts_function.restype = ctypes.c_int32
        self.budgeted_counts_function = (
            self.library.th06_terminal_counts_budgeted
        )
        self.budgeted_counts_function.argtypes = (
            *self.replanning_function.argtypes[:-1],
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_int32),
        )
        self.budgeted_counts_function.restype = ctypes.c_int32
        self.progressive_counts_function = (
            self.library.th06_flexible_terminal_counts_progressive
        )
        self.progressive_counts_function.argtypes = (
            *self.replanning_function.argtypes[:10],
            ctypes.c_int32,
            ctypes.c_int32,
            *self.replanning_function.argtypes[11:-1],
            ctypes.c_double,
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
        )
        self.progressive_counts_function.restype = ctypes.c_int32
        self.progressive_segment_counts_function = (
            self.library.th06_segment_terminal_counts_progressive
        )
        self.progressive_segment_counts_function.argtypes = (
            *self.progressive_counts_function.argtypes,
        )
        self.progressive_segment_counts_function.restype = ctypes.c_int32
        self.progressive_segment_guidance_function = (
            self.library.th06_segment_terminal_guidance_progressive
        )
        self.progressive_segment_guidance_function.argtypes = (
            *self.progressive_segment_counts_function.argtypes[:-2],
            ctypes.c_int32,
            *self.progressive_segment_counts_function.argtypes[-2:],
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        )
        self.progressive_segment_guidance_function.restype = ctypes.c_int32
        self.progressive_viability_function = (
            self.library.th06_boolean_reachability_progressive
        )
        self.progressive_viability_function.argtypes = (
            *self.progressive_counts_function.argtypes,
        )
        self.progressive_viability_function.restype = ctypes.c_int32
        self._prepared_snapshot: Snapshot | None = None
        self._prepared_horizon = 0
        self._prepared_collision_margin = -math.inf
        self._prepared_hazards = None
        self._hard_birth_snapshot: Snapshot | None = None
        self._hard_birth_horizon = 0
        self._hard_birth_forecast = None
        self._nominal_birth_snapshot: Snapshot | None = None
        self._nominal_birth_horizon = 0
        self._nominal_birth_forecast = None
        self._bullet_snapshot: Snapshot | None = None
        self._bullet_horizon = 0
        self._bullet_hazards = None

    @staticmethod
    def _flatten(frames, value_type, convert):
        offsets = [0]
        count = 0
        for frame in frames:
            count += len(frame)
            offsets.append(count)
        coordinates = array(
            "f",
            [
                coordinate
                for frame in frames
                for value in frame
                for coordinate in convert(value)
            ],
        )
        offset_array = (ctypes.c_uint32 * len(offsets))(*offsets)
        value_array_type = value_type * max(1, count)
        value_array = (
            value_array_type.from_buffer_copy(coordinates)
            if count
            else value_array_type()
        )
        return offset_array, value_array

    @staticmethod
    def _reachable_aabb_frames(
        snapshot: Snapshot,
        frames,
        start_frame: int,
        collision_margin: float,
    ):
        """Drop boxes outside a conservative player-reachable rectangle."""
        margin = max(0.0, collision_margin)
        speed = max(
            abs(snapshot.normal_speed),
            abs(snapshot.focus_speed),
            abs(snapshot.normal_diagonal_speed),
            abs(snapshot.focus_diagonal_speed),
        )
        result = []
        for relative_frame, frame in enumerate(frames, 1):
            steps = start_frame + relative_frame
            minimum_x = (
                max(8.0, snapshot.x - speed * steps)
                - snapshot.half_width
                - margin
            )
            maximum_x = (
                min(376.0, snapshot.x + speed * steps)
                + snapshot.half_width
                + margin
            )
            minimum_y = (
                max(16.0, snapshot.y - speed * steps)
                - snapshot.half_height
                - margin
            )
            maximum_y = (
                min(432.0, snapshot.y + speed * steps)
                + snapshot.half_height
                + margin
            )
            result.append(tuple(
                hazard for hazard in frame
                if not (
                    hazard[2] < minimum_x
                    or hazard[0] > maximum_x
                    or hazard[3] < minimum_y
                    or hazard[1] > maximum_y
                )
            ))
        return tuple(result)

    def _prepare_window(
        self,
        snapshot: Snapshot,
        start_frame: int,
        horizon: int,
        fail_closed_horizon: int = 4,
        collision_margin: float = 0.35,
    ):
        total_horizon = start_frame + horizon
        if (
            getattr(self, "_bullet_snapshot", None) is snapshot
            and getattr(self, "_bullet_horizon", 0) >= total_horizon
        ):
            all_bullet_frames = self._bullet_hazards[:total_horizon]
        elif (
            getattr(self, "_bullet_snapshot", None) is snapshot
            and getattr(self, "_bullet_hazards", None) is not None
        ):
            all_bullet_frames = extend_bullet_hazards_by_frame(
                snapshot,
                self._bullet_hazards[:self._bullet_horizon],
                total_horizon,
            )
        else:
            all_bullet_frames = bullet_hazards_by_frame(
                snapshot,
                total_horizon,
            )[:total_horizon]
        if not (
            getattr(self, "_bullet_snapshot", None) is snapshot
            and getattr(self, "_bullet_horizon", 0) > total_horizon
        ):
            self._bullet_snapshot = snapshot
            self._bullet_horizon = total_horizon
            self._bullet_hazards = all_bullet_frames
        bullet_frames = all_bullet_frames[start_frame:]
        enemy_frames = enemy_hazards_by_frame(snapshot.enemies, total_horizon)[
            start_frame:
        ]
        hard_birth_horizon = min(fail_closed_horizon, total_horizon)
        if (
            getattr(self, "_hard_birth_snapshot", None) is snapshot
            and getattr(self, "_hard_birth_horizon", 0)
            >= hard_birth_horizon
        ):
            hard_births = self._hard_birth_forecast
        else:
            hard_births = forecast_world_births(
                snapshot,
                ((snapshot.x, snapshot.y),) * hard_birth_horizon,
            )
            self._hard_birth_snapshot = snapshot
            self._hard_birth_horizon = hard_birth_horizon
            self._hard_birth_forecast = hard_births
        # A fully fail-closed authority window never reads nominal births.
        # Avoid executing the same ECL program a second time on this Hard hot
        # path; mixed Hard/soft windows still build the nominal continuation.
        nominal_births = None
        if fail_closed_horizon < total_horizon:
            if (
                getattr(self, "_nominal_birth_snapshot", None) is snapshot
                and getattr(self, "_nominal_birth_horizon", 0)
                    >= total_horizon
            ):
                nominal_births = self._nominal_birth_forecast
            elif (
                getattr(self, "_nominal_birth_snapshot", None) is snapshot
                and getattr(self, "_nominal_birth_forecast", None)
                    is not None
                and self._nominal_birth_forecast.continuation is not None
                and self._nominal_birth_forecast.covered_frames
                    == getattr(self, "_nominal_birth_horizon", 0)
            ):
                nominal_births = extend_nominal_world_births(
                    snapshot,
                    self._nominal_birth_forecast,
                    ((snapshot.x, snapshot.y),) * (
                        total_horizon - self._nominal_birth_horizon
                    ),
                )
            else:
                nominal_births = forecast_world_births(
                    snapshot,
                    ((snapshot.x, snapshot.y),) * total_horizon,
                    rng_mode="nominal",
                )
            self._nominal_birth_snapshot = snapshot
            self._nominal_birth_horizon = total_horizon
            self._nominal_birth_forecast = nominal_births
        uncovered = ((-10000.0, -10000.0, 10000.0, 10000.0),)
        birth_frames = tuple(
            (
                hard_births.hazards[index]
                if index < hard_births.covered_frames
                else uncovered
            )
            if index < fail_closed_horizon
            else (
                nominal_births.hazards[index]
                if nominal_births is not None
                and index < nominal_births.covered_frames
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
            if index < fail_closed_horizon
            else (
                nominal_births.body_hazards[index]
                if nominal_births is not None
                and index < nominal_births.covered_frames
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
        aabb_frames = self._reachable_aabb_frames(
            snapshot,
            aabb_frames,
            start_frame,
            collision_margin,
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

    def _prepare(
        self,
        snapshot: Snapshot,
        horizon: int,
        collision_margin: float = 0.35,
    ):
        return self._prepare_window(
            snapshot,
            0,
            horizon,
            collision_margin=collision_margin,
        )

    def _prepare_fail_closed(
        self,
        snapshot: Snapshot,
        horizon: int,
        collision_margin: float,
    ):
        prepared = self._prepare_window(
            snapshot,
            0,
            horizon,
            fail_closed_horizon=horizon,
            collision_margin=collision_margin,
        )
        self._prepared_snapshot = snapshot
        self._prepared_horizon = horizon
        self._prepared_collision_margin = collision_margin
        self._prepared_hazards = prepared
        return prepared

    def _prepare_reusable(
        self,
        snapshot: Snapshot,
        horizon: int,
        collision_margin: float = 0.35,
    ):
        if (
            self._prepared_snapshot is snapshot
            and self._prepared_horizon >= horizon
            and getattr(
                self,
                "_prepared_collision_margin",
                -math.inf,
            ) >= collision_margin
        ):
            return self._prepared_hazards
        prepared = self._prepare(snapshot, horizon, collision_margin)
        self._prepared_snapshot = snapshot
        self._prepared_horizon = horizon
        self._prepared_collision_margin = collision_margin
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
        budget_ms: float | None = None,
    ) -> tuple[
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
        tuple[SafeAction, ...],
    ] | None:
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        output = (_SafeResult * len(CONTROL_ACTIONS))()
        age_zero_output = (_SafeResult * len(CONTROL_ACTIONS))()
        extended_output = (_SafeResult * len(CONTROL_ACTIONS))()
        arguments = (
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
        )
        outputs = (
            output,
            age_zero_output,
            extended_output if include_extended else None,
        )
        status = (
            self.function(*arguments, *outputs)
            if budget_ms is None
            else self.budgeted_certify_function(
                *arguments, budget_ms, *outputs
            )
        )
        if status == 1 and budget_ms is not None:
            return None
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
            self._prepare_reusable(snapshot, horizon, collision_margin),
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
            self._prepare_reusable(snapshot, horizon, collision_margin),
            candidate_mask,
        )[0]

    def certify_selected_budgeted(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
        collision_margin: float,
        budget_ms: float,
    ) -> tuple[SafeAction, ...] | None:
        """Return one complete constant witness set, or None on timeout."""
        selected = frozenset(actions)
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in selected
        )
        if not candidate_mask:
            return ()
        result = self._certify_prepared(
            snapshot,
            horizon,
            collision_margin,
            self._prepare_reusable(snapshot, horizon, collision_margin),
            candidate_mask,
            budget_ms=budget_ms,
        )
        return None if result is None else result[0]

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
            self._prepare_reusable(snapshot, horizon, collision_margin),
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
        prepared = self._prepare_reusable(
            snapshot, effort_horizon, collision_margin
        )
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
        prepared = self._prepare_reusable(
            snapshot, maximum_horizon, collision_margin
        )
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
        # This selected continuation may extend physical publication
        # authority, so every included ECL frame must use fail-closed source
        # semantics rather than the nominal soft-proposal forecast.
        prepared = self._prepare_fail_closed(
            snapshot, selected_horizon, collision_margin
        )
        hard, age_zero, _extended = self._certify_prepared(
            snapshot,
            hard_horizon,
            collision_margin,
            prepared,
            (1 << len(CONTROL_ACTIONS)) - 1,
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
            self._prepare(snapshot, horizon, collision_margin),
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
            self._prepare_reusable(snapshot, horizon, collision_margin),
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
        prepared = self._prepare_reusable(
            snapshot, effort_horizon, collision_margin
        )
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
        prepared = self._prepare_reusable(
            snapshot, effort_horizon, collision_margin
        )
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
        prepared = self._prepare_reusable(
            snapshot, maximum_horizon, collision_margin
        )
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
        prepared = self._prepare_reusable(
            snapshot, horizon, collision_margin
        )
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

    def macro_tail_scores_budgeted(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        split: int,
        horizon: int,
        collision_margin: float,
        budget_ms: float,
    ) -> dict[Action, int] | None:
        """Compare complete 18-action constant tails, or discard on timeout."""
        bullet_offsets, bullets, laser_offsets, lasers = (
            self._prepare_reusable(snapshot, horizon, collision_margin)
        )
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        output = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        status = self.macro_tail_function(
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
            budget_ms,
            output,
        )
        if status == 1:
            return None
        if status != 0:
            raise RuntimeError(
                f"native macro-tail kernel rejected input with status {status}"
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
        prepared = self._prepare_reusable(
            snapshot, horizon, collision_margin
        )
        return self._nominal_policy_counts_prepared(
            snapshot,
            candidates,
            segment_length,
            horizon,
            collision_margin,
            prepared,
        )

    def nominal_policy_counts_budgeted(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
        budget_ms: float,
    ):
        """Return a complete policy volume, or None when its budget expires."""
        prepared = self._prepare_reusable(
            snapshot, horizon, collision_margin
        )
        return self._nominal_policy_counts_prepared(
            snapshot,
            candidates,
            segment_length,
            horizon,
            collision_margin,
            prepared,
            budget_ms,
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
        return self._terminal_guidance_prepared(
            snapshot,
            candidates,
            segment_length,
            horizon,
            collision_margin,
            target,
            self._prepare_reusable(snapshot, horizon, collision_margin),
        )

    def terminal_guidance_budgeted(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
        budget_ms: float,
        target: tuple[float, float] | None = None,
    ) -> dict[Action, TerminalGuidance] | None:
        """Return a complete terminal-state ranking, or None on timeout."""
        return self._terminal_guidance_prepared(
            snapshot,
            candidates,
            segment_length,
            horizon,
            collision_margin,
            target,
            self._prepare_reusable(snapshot, horizon, collision_margin),
            budget_ms,
        )

    def terminal_counts(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
    ) -> dict[Action, int]:
        """Return exact deduplicated terminal-state counts."""
        return self._terminal_counts_prepared(
            snapshot,
            candidates,
            segment_length,
            horizon,
            collision_margin,
            self._prepare_reusable(snapshot, horizon, collision_margin),
        )

    def terminal_counts_budgeted(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
        budget_ms: float,
    ) -> dict[Action, int] | None:
        """Return complete terminal counts, or None when the budget expires."""
        return self._terminal_counts_prepared(
            snapshot,
            candidates,
            segment_length,
            horizon,
            collision_margin,
            self._prepare_reusable(snapshot, horizon, collision_margin),
            budget_ms,
        )

    def flexible_terminal_counts_progressive(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        minimum_horizon: int,
        maximum_horizon: int,
        collision_margin: float,
        budget_ms: float,
    ) -> tuple[int, dict[Action, int], bool] | None:
        """Return the deepest complete per-frame continuation rung.

        The boolean is true only when the requested maximum horizon completed;
        a false value means the next rung timed out and was discarded.
        """
        bullet_offsets, bullets, laser_offsets, lasers = (
            self._prepare_reusable(
                snapshot, maximum_horizon, collision_margin
            )
        )
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        completed_horizon = ctypes.c_int32()
        terminal_counts = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        status = self.progressive_counts_function(
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
            minimum_horizon,
            maximum_horizon,
            candidate_mask,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            budget_ms,
            ctypes.byref(completed_horizon),
            terminal_counts,
        )
        if status == 1:
            return None
        if status not in (0, 2):
            raise RuntimeError(
                "native flexible terminal counts rejected input "
                f"with status {status}"
            )
        return (
            completed_horizon.value,
            {
                action: terminal_counts[index]
                for index, action in enumerate(CONTROL_ACTIONS)
                if action in candidate_actions
            },
            status == 0,
        )

    def segment_terminal_counts_progressive(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        minimum_horizon: int,
        maximum_horizon: int,
        collision_margin: float,
        budget_ms: float,
    ) -> tuple[int, dict[Action, int], bool] | None:
        """Return the deepest complete delivery-segment terminal rung."""
        bullet_offsets, bullets, laser_offsets, lasers = (
            self._prepare_reusable(
                snapshot, maximum_horizon, collision_margin
            )
        )
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        completed_horizon = ctypes.c_int32()
        terminal_counts = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        status = self.progressive_segment_counts_function(
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
            minimum_horizon,
            maximum_horizon,
            candidate_mask,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            budget_ms,
            ctypes.byref(completed_horizon),
            terminal_counts,
        )
        if status == 1:
            return None
        if status not in (0, 2):
            raise RuntimeError(
                "native segment terminal counts rejected input "
                f"with status {status}"
            )
        return (
            completed_horizon.value,
            {
                action: terminal_counts[index]
                for index, action in enumerate(CONTROL_ACTIONS)
                if action in candidate_actions
            },
            status == 0,
        )

    def segment_terminal_guidance_progressive(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        minimum_horizon: int,
        maximum_horizon: int,
        guidance_action: Action,
        collision_margin: float,
        budget_ms: float,
    ) -> tuple[
        int,
        dict[Action, int],
        bool,
        TerminalGuidance | None,
    ] | None:
        """Publish survival first, then optional exact route guidance."""
        bullet_offsets, bullets, laser_offsets, lasers = (
            self._prepare_reusable(
                snapshot, maximum_horizon, collision_margin
            )
        )
        candidate_actions = {candidate.action for candidate in candidates}
        if guidance_action not in candidate_actions:
            raise ValueError("guidance action must be a candidate")
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        guidance_index = CONTROL_ACTIONS.index(guidance_action)
        completed_horizon = ctypes.c_int32()
        terminal_counts = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        guidance_ready = ctypes.c_int32()
        guidance_clearance = ctypes.c_float()
        guidance_x = ctypes.c_float()
        guidance_y = ctypes.c_float()
        status = self.progressive_segment_guidance_function(
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
            minimum_horizon,
            maximum_horizon,
            candidate_mask,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            budget_ms,
            guidance_index,
            ctypes.byref(completed_horizon),
            terminal_counts,
            ctypes.byref(guidance_ready),
            ctypes.byref(guidance_clearance),
            ctypes.byref(guidance_x),
            ctypes.byref(guidance_y),
        )
        if status == 1:
            return None
        if status not in (0, 2):
            raise RuntimeError(
                "native segment terminal guidance rejected input "
                f"with status {status}"
            )
        counts = {
            action: terminal_counts[index]
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        }
        guidance = (
            TerminalGuidance(
                terminal_count=counts[guidance_action],
                free_clearance=guidance_clearance.value,
                free_x=guidance_x.value,
                free_y=guidance_y.value,
                target_distance_squared=math.inf,
            )
            if guidance_ready.value
            else None
        )
        return (
            completed_horizon.value,
            counts,
            status == 0,
            guidance,
        )

    def boolean_reachability_progressive(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        minimum_horizon: int,
        maximum_horizon: int,
        collision_margin: float,
        budget_ms: float,
    ) -> tuple[int, dict[Action, int], bool] | None:
        """Return deepest complete robust Boolean viability membership."""
        bullet_offsets, bullets, laser_offsets, lasers = (
            self._prepare_reusable(
                snapshot, maximum_horizon, collision_margin
            )
        )
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        completed_horizon = ctypes.c_int32()
        membership = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        status = self.progressive_viability_function(
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
            minimum_horizon,
            maximum_horizon,
            candidate_mask,
            bullet_offsets,
            bullets,
            laser_offsets,
            lasers,
            collision_margin,
            budget_ms,
            ctypes.byref(completed_horizon),
            membership,
        )
        if status == 1:
            return None
        if status not in (0, 2):
            raise RuntimeError(
                "native Boolean reachability rejected input "
                f"with status {status}"
            )
        return (
            completed_horizon.value,
            {
                action: membership[index]
                for index, action in enumerate(CONTROL_ACTIONS)
                if action in candidate_actions
            },
            status == 0,
        )

    def _terminal_counts_prepared(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
        prepared,
        budget_ms: float | None = None,
    ) -> dict[Action, int] | None:
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        terminal_counts = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        arguments = (
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
        )
        status = (
            self.counts_function(*arguments, terminal_counts)
            if budget_ms is None
            else self.budgeted_counts_function(
                *arguments,
                budget_ms,
                terminal_counts,
            )
        )
        if status == 1 and budget_ms is not None:
            return None
        if status != 0:
            raise RuntimeError(
                f"native terminal counts rejected input with status {status}"
            )
        return {
            action: terminal_counts[index]
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        }

    def _terminal_guidance_prepared(
        self,
        snapshot: Snapshot,
        candidates: tuple[SafeAction, ...],
        segment_length: int,
        horizon: int,
        collision_margin: float,
        target: tuple[float, float] | None,
        prepared,
        budget_ms: float | None = None,
    ) -> dict[Action, TerminalGuidance] | None:
        bullet_offsets, bullets, laser_offsets, lasers = prepared
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
        arguments = (
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
        )
        outputs = (
            terminal_counts,
            free_clearances,
            free_x,
            free_y,
            target_distances,
        )
        status = (
            self.guidance_function(*arguments, *outputs)
            if budget_ms is None
            else self.budgeted_guidance_function(
                *arguments,
                budget_ms,
                *outputs,
            )
        )
        if status == 1 and budget_ms is not None:
            return None
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
            snapshot, maximum_ahead + horizon, collision_margin
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
        budget_ms: float | None = None,
    ):
        bullet_offsets, bullets, laser_offsets, lasers = prepared
        candidate_actions = {candidate.action for candidate in candidates}
        candidate_mask = sum(
            1 << index
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        )
        output = (ctypes.c_int32 * len(CONTROL_ACTIONS))()
        arguments = (
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
        )
        status = (
            self.nominal_function(*arguments, output)
            if budget_ms is None
            else self.budgeted_nominal_function(
                *arguments,
                budget_ms,
                output,
            )
        )
        if budget_ms is not None and status == 1:
            return None
        if status != 0:
            raise RuntimeError(
                f"native nominal policy kernel rejected input with status {status}"
            )
        return {
            action: output[index]
            for index, action in enumerate(CONTROL_ACTIONS)
            if action in candidate_actions
        }

#!/usr/bin/env python3
"""Screen the complete Stage 1 second-nonspell source family.

The retained physical root is sub16 immediately after the first-spell timer
callback.  Sub16 contains a source-authored no-birth entry through t199 and
CALLs sub18 at t200.  Sub18/19/20/21 then form an RNG-selected attack family
until the life or timer callback enters sub23.  A case succeeds only at that
stable source boundary; short fixed-frame survival is not accepted.

All policies rank actions inside the unchanged native Hard set.  Results are
offline evidence, never action authority or a physical clear.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import time

from th06.barrage_lab.corpus import load_failure_history
from th06.barrage_lab.stateful import NativeTerminalPolicy, run_closed_loop
from th06.barrage_lab.stateful import (
    UnsupportedStatefulModel,
    current_bullet_clearance,
)
from th06.kernels.safety import NativeSafetyKernel
from th06.model import ACTIONS, CONTROL_ACTIONS, Action, Snapshot, action_from_input
from th06.ranking import ProposalRanker, preferred_target_actions
from th06.routes.phase import ecl_subroutine_index
from th06.solver import Solver


ENTRY_SUBROUTINE = 16
ATTACK_SUBROUTINES = frozenset((18, 19, 20, 21))
PHASE_SUBROUTINES = ATTACK_SUBROUTINES | {ENTRY_SUBROUTINE}
ENTRY_ATTACK_TIME = 200
TIMER_LIMIT = 1800
BOTTOM_CENTER = (192.0, 380.0)


# Installed ecldata1.ecl source-clock states.  ``active`` ends immediately
# after the last hostile birth/laser mutation, ``residual`` owns only the
# resulting field, and ``dispatch`` is the one source tick which chooses the
# next subroutine.  Keeping these states separate also prevents a ranker's
# four-frame soft commitment from leaking across a source boundary.
SOURCE_SEGMENTS = {
    18: (
        ("entry-positioning", 0, 12),
        ("aimed-fan", 12, 20),
        ("laser-births", 20, 61),
        ("laser-hold", 61, 124),
        ("laser-turn", 124, 165),
        ("residual", 165, 224),
        ("dispatch", 224, 225),
    ),
    19: (
        ("entry-movement", 0, 60),
        ("circle-volley", 60, 121),
        ("residual", 121, 240),
        ("dispatch", 240, 241),
    ),
    20: (
        ("entry-movement", 0, 60),
        ("aimed-fans", 60, 101),
        ("residual", 101, 220),
        ("dispatch", 220, 221),
    ),
    21: (("active", 0, 5), ("residual", 5, 124), ("dispatch", 124, 125)),
}


def _source_segment(subroutine: int, local_time: int) -> str:
    for name, start_time, stop_time in SOURCE_SEGMENTS[subroutine]:
        if start_time <= local_time < stop_time:
            return name
    raise ValueError(
        f"sub{subroutine} local t{local_time} is outside its audited cycle"
    )


def _segment_group(segment: str) -> str:
    return segment if segment in ("residual", "dispatch") else "active"


@dataclass(frozen=True)
class Candidate:
    metric: str
    horizon: int
    overrides: tuple[tuple[int, str, int], ...] = ()
    target: tuple[float, float] | None = None
    target_overrides: tuple[
        tuple[int, tuple[float, float] | None], ...
    ] = ()
    segment_overrides: tuple[
        tuple[str, str, int, tuple[float, float] | None], ...
    ] = ()
    source_segment_overrides: tuple[
        tuple[int, str, str, int, tuple[float, float] | None], ...
    ] = ()
    caller_segment_overrides: tuple[
        tuple[int, int, str, str, int, tuple[float, float] | None], ...
    ] = ()

    def policy_for(
        self,
        subroutine: int,
        local_time: int,
        caller_subroutine: int | None = None,
    ) -> tuple[str, int, tuple[float, float] | None]:
        metric, horizon = next(
            (
                (metric, horizon)
                for selected, metric, horizon in self.overrides
                if selected == subroutine
            ),
            (self.metric, self.horizon),
        )
        target = next(
            (
                target
                for selected, target in self.target_overrides
                if selected == subroutine
            ),
            self.target,
        )
        segment = _source_segment(subroutine, local_time)
        segment_group = _segment_group(segment)
        metric, horizon, target = next(
            (
                (selected_metric, selected_horizon, selected_target)
                for (
                    selected_segment,
                    selected_metric,
                    selected_horizon,
                    selected_target,
                ) in self.segment_overrides
                if selected_segment in (segment, segment_group)
            ),
            (metric, horizon, target),
        )
        caller_exact = next(
            (
                (selected_metric, selected_horizon, selected_target)
                for (
                    selected_caller,
                    selected_subroutine,
                    selected_segment,
                    selected_metric,
                    selected_horizon,
                    selected_target,
                ) in self.caller_segment_overrides
                if (
                    selected_caller == caller_subroutine
                    and selected_subroutine == subroutine
                    and selected_segment == segment
                )
            ),
            None,
        )
        if caller_exact is not None:
            return caller_exact
        exact = next(
            (
                (selected_metric, selected_horizon, selected_target)
                for (
                    selected_subroutine,
                    selected_segment,
                    selected_metric,
                    selected_horizon,
                    selected_target,
                ) in self.source_segment_overrides
                if (
                    selected_subroutine == subroutine
                    and selected_segment == segment
                )
            ),
            None,
        )
        if exact is not None:
            return exact
        return next(
            (
                (selected_metric, selected_horizon, selected_target)
                for (
                    selected_subroutine,
                    selected_segment,
                    selected_metric,
                    selected_horizon,
                    selected_target,
                ) in self.source_segment_overrides
                if (
                    selected_subroutine == subroutine
                    and selected_segment == segment_group
                )
            ),
            (metric, horizon, target),
        )

    def policy_key(
        self,
        subroutine: int,
        local_time: int,
        caller_subroutine: int | None = None,
    ) -> tuple[
        int, int | None, str, str, int, tuple[float, float] | None
    ]:
        segment = _source_segment(subroutine, local_time)
        metric, horizon, target = self.policy_for(
            subroutine, local_time, caller_subroutine
        )
        return (
            subroutine,
            caller_subroutine,
            segment,
            metric,
            horizon,
            target,
        )


def _segmented(
    residual_metric: str,
    residual_horizon: int,
    residual_target: tuple[float, float] | None = None,
    *,
    active_metric: str = "policy-volume",
    active_horizon: int = 8,
    active_target: tuple[float, float] | None = None,
) -> Candidate:
    return Candidate(
        active_metric,
        active_horizon,
        target=active_target,
        segment_overrides=(
            ("residual", residual_metric, residual_horizon, residual_target),
            ("dispatch", "policy-volume", 4, None),
        ),
    )


def _segmented_with(
    *overrides: tuple[
        int, str, str, int, tuple[float, float] | None
    ],
) -> Candidate:
    candidate = _segmented("policy-volume", 6)
    return Candidate(
        candidate.metric,
        candidate.horizon,
        target=candidate.target,
        segment_overrides=candidate.segment_overrides,
        source_segment_overrides=overrides,
    )


def _segmented_with_caller(
    source_overrides: tuple[
        tuple[int, str, str, int, tuple[float, float] | None], ...
    ],
    caller_overrides: tuple[
        tuple[int, int, str, str, int, tuple[float, float] | None], ...
    ],
) -> Candidate:
    candidate = _segmented("policy-volume", 6)
    return Candidate(
        candidate.metric,
        candidate.horizon,
        target=candidate.target,
        segment_overrides=candidate.segment_overrides,
        source_segment_overrides=source_overrides,
        caller_segment_overrides=caller_overrides,
    )


class NativeStickyReservePolicy:
    """Hold a demonstrated command tube until its durable reserve expires."""

    def __init__(
        self,
        horizon: int,
        *,
        kernel,
        metric: str,
        target: tuple[float, float] | None,
    ) -> None:
        self.horizon = horizon
        self.kernel = kernel
        self.metric = metric
        self.target = target
        self.ranker = ProposalRanker()

    def __call__(self, snapshot: Snapshot):
        hard = self.kernel.certify_selected(
            snapshot,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        )
        if not hard:
            return None
        current = action_from_input(snapshot.input_mask)
        reserve = self.kernel.certify_selected(
            snapshot,
            self.horizon,
            tuple(candidate.action for candidate in hard),
            collision_margin=0.35,
        )
        reserve_actions = frozenset(
            candidate.action for candidate in reserve
        )
        if current in reserve_actions:
            return current

        preferred = reserve_actions
        if self.metric == "sticky-clearance" and reserve:
            best = max(candidate.clearance for candidate in reserve)
            preferred = frozenset(
                candidate.action for candidate in reserve
                if candidate.clearance == best
            )
        elif self.metric == "sticky-reserve-count" and reserve:
            deep = self.kernel.terminal_counts(
                snapshot,
                reserve,
                4,
                self.horizon,
                collision_margin=0.35,
            )
            best = max((deep[action] for action in reserve_actions), default=0)
            if best > 0:
                preferred = frozenset(
                    action for action in reserve_actions
                    if deep[action] == best
                )
        elif self.metric == "sticky-delivery-count":
            robust = self.kernel.delivery_segment_viability_progressive(
                snapshot,
                hard,
                4,
                min(8, self.horizon),
                self.horizon,
                collision_margin=0.35,
                budget_ms=1000.0,
            )
            viable = frozenset(
                action for action, score in (robust[1] if robust else {}).items()
                if score > 0
            )
            if viable:
                deep = self.kernel.terminal_counts(
                    snapshot,
                    tuple(
                        candidate for candidate in hard
                        if candidate.action in viable
                    ),
                    4,
                    self.horizon,
                    collision_margin=0.35,
                )
                best = max((deep[action] for action in viable), default=0)
                preferred = frozenset(
                    action for action in viable
                    if best <= 0 or deep[action] == best
                )
        if not preferred:
            best = max(candidate.clearance for candidate in hard)
            preferred = frozenset(
                candidate.action for candidate in hard
                if candidate.clearance == best
            )
        if self.target is not None:
            preferred = preferred_target_actions(hard, preferred, self.target)
        return self.ranker.choose(
            snapshot,
            hard,
            preferred,
            commitment_frames=1,
        ).action


def _boundary_room(x: float, y: float) -> float:
    return min(x - 8.0, 376.0 - x, y - 16.0, 432.0 - y)


class NativeHistoricalDurablePolicy:
    """Native form of the b5 Stage 1 clear demonstrator, scoped per state."""

    def __init__(self, *, kernel) -> None:
        self.kernel = kernel
        self.repair_action: Action | None = None
        self.repair_until_frame: int | None = None

    def __call__(self, snapshot: Snapshot):
        hard = self.kernel.certify_selected(
            snapshot,
            4,
            ACTIONS,
            collision_margin=0.35,
        )
        if not hard:
            return None
        durable = self.kernel.certify_selected(
            snapshot,
            16,
            tuple(candidate.action for candidate in hard),
            collision_margin=0.35,
        )
        durable_actions = frozenset(
            candidate.action for candidate in durable
        )
        repairable_actions: frozenset[Action] = frozenset()
        if not durable_actions:
            scores = self.kernel.macro_tail_scores_budgeted(
                snapshot,
                hard,
                4,
                8,
                collision_margin=0.35,
                budget_ms=1000.0,
            )
            best = max((scores or {}).values(), default=0)
            if best > 0:
                repairable_actions = frozenset(
                    action for action, score in scores.items()
                    if score == best
                )

        current = action_from_input(snapshot.input_mask)
        candidate_actions = frozenset(
            candidate.action for candidate in hard
        )
        continued_repair = (
            self.repair_action
            if (
                self.repair_action in candidate_actions
                and self.repair_until_frame is not None
                and snapshot.frame < self.repair_until_frame
            )
            else None
        )
        current_room = _boundary_room(snapshot.x, snapshot.y)

        def score(candidate) -> tuple:
            useful_position = -0.04 * math.hypot(
                candidate.final_x - BOTTOM_CENTER[0],
                candidate.final_y - BOTTOM_CENTER[1],
            )
            continuity = 0.15 if candidate.action == current else 0.0
            return (
                candidate.action in durable_actions,
                candidate.action == continued_repair,
                candidate.action in repairable_actions,
                _boundary_room(candidate.final_x, candidate.final_y)
                > current_room + 0.25,
                min(80.0, candidate.clearance) + useful_position + continuity,
                candidate.clearance,
                continuity,
                candidate.action.name,
            )

        chosen = max(hard, key=score)
        selective_repair = (
            repairable_actions
            and len(repairable_actions) < len(candidate_actions)
            and chosen.action in repairable_actions
        )
        if selective_repair and continued_repair != chosen.action:
            self.repair_action = chosen.action
            self.repair_until_frame = snapshot.frame + 4
        elif continued_repair is not None and chosen.action != continued_repair:
            self.repair_action = None
            self.repair_until_frame = None
        return chosen.action


def _make_policy(
    metric: str,
    horizon: int,
    target: tuple[float, float] | None,
    kernel,
):
    if metric in (
        "sticky-frontier",
        "sticky-clearance",
        "sticky-reserve-count",
        "sticky-delivery-count",
    ):
        return NativeStickyReservePolicy(
            horizon,
            kernel=kernel,
            metric=metric,
            target=target,
        )
    if metric == "historical-durable":
        return NativeHistoricalDurablePolicy(kernel=kernel)
    return NativeTerminalPolicy(
        horizon,
        kernel=kernel,
        metric=metric,
        target=target,
    )


CANDIDATES = {
    "production": Candidate("production", 8),
    "pv6": Candidate("policy-volume", 6),
    "pv8": Candidate("policy-volume", 8),
    "pv10": Candidate("policy-volume", 10),
    "pv12": Candidate("policy-volume", 12),
    "cc6": Candidate("count-clearance", 6),
    "cc8": Candidate("count-clearance", 8),
    "cfc8": Candidate("constant-frontier-count", 8),
    "s18pv8-restpv6": Candidate(
        "policy-volume", 6, ((18, "policy-volume", 8),)
    ),
    "s18s20pv8-restpv6": Candidate(
        "policy-volume",
        6,
        ((18, "policy-volume", 8), (20, "policy-volume", 8)),
    ),
    "s18s20pv8-restcfc8": Candidate(
        "constant-frontier-count",
        8,
        ((18, "policy-volume", 8), (20, "policy-volume", 8)),
    ),
    "pv8bc": Candidate(
        "policy-volume", 8, target=BOTTOM_CENTER
    ),
    "s18pv8bc-restpv8": Candidate(
        "policy-volume",
        8,
        target_overrides=((18, BOTTOM_CENTER),),
    ),
    "seg-pv8-res-pv6": _segmented("policy-volume", 6),
    "seg-pv8-res-pv8": _segmented("policy-volume", 8),
    "seg-pv8-res-pv10": _segmented("policy-volume", 10),
    "seg-pv8-res-cf6": _segmented("constant-frontier", 6),
    "seg-pv8-res-cf8": _segmented("constant-frontier", 8),
    "seg-pv8-res-cf10": _segmented("constant-frontier", 10),
    "seg-pv8-res-cfc6": _segmented("constant-frontier-count", 6),
    "seg-pv8-res-cfc8": _segmented("constant-frontier-count", 8),
    "seg-pv8-res-clr4": _segmented("constant-clearance", 4),
    "seg-pv8-res-clr5": _segmented("constant-clearance", 5),
    "seg-pv8-res-clr6": _segmented("constant-clearance", 6),
    "seg-pv8-res-clr8": _segmented("constant-clearance", 8),
    "seg-pv8-res-cc6": _segmented("count-clearance", 6),
    "seg-pv8-res-cc8": _segmented("count-clearance", 8),
    "seg-pv8-res-cf8-bottom": _segmented(
        "constant-frontier", 8, BOTTOM_CENTER
    ),
    "seg-pv8-res-clr6-bottom": _segmented(
        "constant-clearance", 6, BOTTOM_CENTER
    ),
    "seg-s18active-pv10": _segmented_with(
        (18, "active", "policy-volume", 10, None),
    ),
    "seg-s18active-pv12": _segmented_with(
        (18, "active", "policy-volume", 12, None),
    ),
    "seg-s18active-cf8": _segmented_with(
        (18, "active", "constant-frontier", 8, None),
    ),
    "seg-s18active-cfc8": _segmented_with(
        (18, "active", "constant-frontier-count", 8, None),
    ),
    "seg-s18active-cfc10": _segmented_with(
        (18, "active", "constant-frontier-count", 10, None),
    ),
    "seg-s18active-clr8": _segmented_with(
        (18, "active", "constant-clearance", 8, None),
    ),
    "seg-s18active-delivery8": _segmented_with(
        (18, "active", "delivery-filtered-count", 8, None),
    ),
    "seg-s18active-replan8": _segmented_with(
        (18, "active", "replanning-count", 8, None),
    ),
    "seg-s18active-authority8": _segmented_with(
        (18, "active", "authority-filtered-count", 8, None),
    ),
    "seg-s18active-authority10": _segmented_with(
        (18, "active", "authority-filtered-count", 10, None),
    ),
    "seg-s18active-reserve8": _segmented_with(
        (18, "active", "constant-reserve-count", 8, None),
    ),
    "seg-s18active-reserve10": _segmented_with(
        (18, "active", "constant-reserve-count", 10, None),
    ),
    "seg-s18active-vector8": _segmented_with(
        (18, "active", "count-vector", 8, None),
    ),
    "seg-s18active-localvector8": _segmented_with(
        (18, "active", "local-count-vector", 8, None),
    ),
    "seg-s18active-clearancecount8": _segmented_with(
        (18, "active", "clearance-count", 8, None),
    ),
    "seg-s18active-sticky8": _segmented_with(
        (18, "active", "sticky-frontier", 8, None),
    ),
    "seg-s18active-sticky10": _segmented_with(
        (18, "active", "sticky-frontier", 10, None),
    ),
    "seg-s18active-sticky12": _segmented_with(
        (18, "active", "sticky-frontier", 12, None),
    ),
    "seg-s18active-stickyclr8": _segmented_with(
        (18, "active", "sticky-clearance", 8, None),
    ),
    "seg-s18active-stickyclr10": _segmented_with(
        (18, "active", "sticky-clearance", 10, None),
    ),
    "seg-s18active-stickycount8": _segmented_with(
        (18, "active", "sticky-reserve-count", 8, None),
    ),
    "seg-s18active-stickycount10": _segmented_with(
        (18, "active", "sticky-reserve-count", 10, None),
    ),
    "seg-s18active-stickydelivery8": _segmented_with(
        (18, "active", "sticky-delivery-count", 8, None),
    ),
    "seg-s18active-stickydelivery12": _segmented_with(
        (18, "active", "sticky-delivery-count", 12, None),
    ),
    "seg-s18active-stickydelivery16": _segmented_with(
        (18, "active", "sticky-delivery-count", 16, None),
    ),
    "seg-s18sticky10-hold-delivery12": _segmented_with(
        (18, "active", "sticky-frontier", 10, None),
        (18, "laser-hold", "sticky-delivery-count", 12, None),
    ),
    "seg-s18stickycount10-hold-delivery12": _segmented_with(
        (18, "active", "sticky-reserve-count", 10, None),
        (18, "laser-hold", "sticky-delivery-count", 12, None),
    ),
    "seg-s18delivery12-turn-stickycount10": _segmented_with(
        (18, "active", "sticky-delivery-count", 12, None),
        (18, "laser-turn", "sticky-reserve-count", 10, None),
    ),
    "seg-s18active-historical16": _segmented_with(
        (18, "active", "historical-durable", 16, None),
    ),
    "seg-s18entry380-restpv8": _segmented_with(
        (18, "entry-positioning", "policy-volume", 4, (192.0, 380.0)),
    ),
    "seg-s18entry400-restpv8": _segmented_with(
        (18, "entry-positioning", "policy-volume", 4, (192.0, 400.0)),
    ),
    "seg-s18entry420-restpv8": _segmented_with(
        (18, "entry-positioning", "policy-volume", 4, (192.0, 420.0)),
    ),
    "seg-s18entry380-delivery12-turncount10": _segmented_with(
        (18, "active", "sticky-delivery-count", 12, None),
        (18, "entry-positioning", "policy-volume", 4, (192.0, 380.0)),
        (18, "laser-turn", "sticky-reserve-count", 10, None),
    ),
    "seg-s18entry400-delivery12-turncount10": _segmented_with(
        (18, "active", "sticky-delivery-count", 12, None),
        (18, "entry-positioning", "policy-volume", 4, (192.0, 400.0)),
        (18, "laser-turn", "sticky-reserve-count", 10, None),
    ),
    "seg-s18entry420-delivery12-turncount10": _segmented_with(
        (18, "active", "sticky-delivery-count", 12, None),
        (18, "entry-positioning", "policy-volume", 4, (192.0, 420.0)),
        (18, "laser-turn", "sticky-reserve-count", 10, None),
    ),
    "seg-s20res-pv8": _segmented_with(
        (20, "residual", "policy-volume", 8, None),
    ),
    "seg-s20res-pv10": _segmented_with(
        (20, "residual", "policy-volume", 10, None),
    ),
    "seg-s20res-cf8": _segmented_with(
        (20, "residual", "constant-frontier", 8, None),
    ),
    "seg-s20res-cfc8": _segmented_with(
        (20, "residual", "constant-frontier-count", 8, None),
    ),
    "seg-s20res-clr6": _segmented_with(
        (20, "residual", "constant-clearance", 6, None),
    ),
    "seg-s20res-clr8": _segmented_with(
        (20, "residual", "constant-clearance", 8, None),
    ),
    "seg-s21res-pv8": _segmented_with(
        (21, "residual", "policy-volume", 8, None),
    ),
    "seg-s21res-pv10": _segmented_with(
        (21, "residual", "policy-volume", 10, None),
    ),
    "seg-s21res-cf8": _segmented_with(
        (21, "residual", "constant-frontier", 8, None),
    ),
    "seg-s21res-cfc8": _segmented_with(
        (21, "residual", "constant-frontier-count", 8, None),
    ),
    "seg-s21res-clr6": _segmented_with(
        (21, "residual", "constant-clearance", 6, None),
    ),
    "seg-s21res-clr8": _segmented_with(
        (21, "residual", "constant-clearance", 8, None),
    ),
    "seg-s18firstentry380-delivery12-turncount10": _segmented_with_caller(
        (
            (18, "active", "sticky-delivery-count", 12, None),
            (18, "laser-turn", "sticky-reserve-count", 10, None),
        ),
        (
            (
                16,
                18,
                "entry-positioning",
                "policy-volume",
                4,
                (192.0, 380.0),
            ),
        ),
    ),
}


def _caller_subroutine(boss) -> int | None:
    if not boss.ecl_stack or not boss.ecl_subroutines:
        return None
    address = boss.ecl_stack[-1].instruction_address
    bases = boss.ecl_subroutines
    return next(
        (
            index
            for index, base in reversed(tuple(enumerate(bases)))
            if address >= base
        ),
        None,
    )


def _boss(snapshot: Snapshot):
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    if len(bosses) != 1:
        raise ValueError("workload state does not have one stable boss")
    return bosses[0]


def _spell_active(snapshot: Snapshot) -> bool:
    return bool(snapshot.player_attack and snapshot.player_attack.spell_active)


def _left_phase(snapshot: Snapshot) -> bool:
    bosses = tuple(spawner for spawner in snapshot.spawners if spawner.is_boss)
    return (
        len(bosses) != 1
        or ecl_subroutine_index(bosses[0]) not in PHASE_SUBROUTINES
        or _spell_active(snapshot)
    )


def _roots(
    paths: tuple[Path, ...],
    entry_frame: int | None,
) -> tuple[tuple[Path, Snapshot], ...]:
    selected = []
    for path in paths:
        history = load_failure_history(path)
        candidates = []
        for snapshot in history:
            bosses = tuple(
                spawner for spawner in snapshot.spawners if spawner.is_boss
            )
            if len(bosses) != 1 or _spell_active(snapshot):
                continue
            subroutine = ecl_subroutine_index(bosses[0])
            stable_family = (
                subroutine in ATTACK_SUBROUTINES
                and not snapshot.despawning_bullets
                and snapshot.player_attack is not None
            )
            clean_entry = (
                subroutine == ENTRY_SUBROUTINE
                and bosses[0].ecl_time < ENTRY_ATTACK_TIME
                and not snapshot.despawning_bullets
                and snapshot.player_attack is not None
            )
            if (
                (stable_family or clean_entry)
                and (entry_frame is None or snapshot.frame == entry_frame)
            ):
                candidates.append(snapshot)
        if not candidates:
            suffix = "" if entry_frame is None else f" at frame {entry_frame}"
            raise ValueError(
                f"{path} has no exactly step-able second-nonspell root{suffix}"
            )
        selected.append((path, candidates[0]))
    return tuple(selected)


class FamilyPolicy:
    """Keep proposal commitment private to each source-clock segment."""

    def __init__(self, kernel, candidate: Candidate) -> None:
        self.calls: Counter[str] = Counter()
        self.entry = NativeTerminalPolicy(
            4, kernel=kernel, metric="policy-volume", target=BOTTOM_CENTER
        )
        self.kernel = kernel
        self.candidate = candidate
        self.attacks: dict[
            tuple[
                int,
                int | None,
                str,
                str,
                int,
                tuple[float, float] | None,
            ],
            NativeTerminalPolicy,
        ] = {}

    def __call__(self, snapshot: Snapshot):
        subroutine = ecl_subroutine_index(_boss(snapshot))
        if subroutine == ENTRY_SUBROUTINE:
            self.calls[f"sub{subroutine}:entry"] += 1
            return self.entry(snapshot)
        boss = _boss(snapshot)
        caller = _caller_subroutine(boss)
        key = self.candidate.policy_key(subroutine, boss.ecl_time, caller)
        self.calls[f"sub{subroutine}:{key[2]}:caller{caller}"] += 1
        policy = self.attacks.get(key)
        if policy is None:
            _, _caller, _segment, metric, horizon, target = key
            policy = _make_policy(metric, horizon, target, self.kernel)
            self.attacks[key] = policy
        return policy(snapshot)


class ProductionPolicy:
    def __init__(self) -> None:
        self.solver = Solver()
        self.reasons: Counter[str] = Counter()
        self.sources: Counter[str] = Counter()
        self.calls: Counter[str] = Counter()

    def __call__(self, snapshot: Snapshot):
        boss = _boss(snapshot)
        subroutine = ecl_subroutine_index(boss)
        label = (
            "entry"
            if subroutine == ENTRY_SUBROUTINE
            else _source_segment(subroutine, boss.ecl_time)
        )
        self.calls[f"sub{subroutine}:{label}"] += 1
        decision = self.solver.decide(snapshot)
        self.reasons[decision.reason] += 1
        self.sources[decision.proposal_source or ""] += 1
        return decision.action


class TimedPolicy:
    def __init__(self, policy) -> None:
        self.policy = policy
        self.elapsed_ms: list[float] = []

    def __call__(self, snapshot: Snapshot):
        started = time.perf_counter()
        action = self.policy(snapshot)
        self.elapsed_ms.append((time.perf_counter() - started) * 1000.0)
        return action


class CaseTrace:
    """Retain only diagnostic extrema, never a large per-frame dump."""

    def __init__(self, root: Snapshot) -> None:
        self.last = root
        self.minimum = current_bullet_clearance(root)
        self.minimum_snapshot = root

    def __call__(self, snapshot: Snapshot) -> None:
        self.last = snapshot
        clearance = current_bullet_clearance(snapshot)
        if clearance < self.minimum:
            self.minimum = clearance
            self.minimum_snapshot = snapshot


def _source_state(snapshot: Snapshot) -> dict[str, object]:
    bosses = tuple(
        spawner for spawner in snapshot.spawners if spawner.is_boss
    )
    boss = bosses[0] if len(bosses) == 1 else None
    return {
        "frame": snapshot.frame,
        "subroutine": (
            ecl_subroutine_index(boss) if boss is not None else None
        ),
        "local_time": boss.ecl_time if boss is not None else None,
        "boss_timer": boss.boss_timer if boss is not None else None,
        "boss_life": boss.life if boss is not None else None,
        "x": snapshot.x,
        "y": snapshot.y,
        "bullets": len(snapshot.bullets),
        "lasers": len(snapshot.lasers),
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def _parse_candidates(raw: str) -> tuple[str, ...]:
    names = tuple(value.strip() for value in raw.split(",") if value.strip())
    unknown = set(names) - set(CANDIDATES)
    if not names or unknown:
        raise ValueError(f"unknown/empty candidates: {sorted(unknown)}")
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path, nargs="+")
    parser.add_argument("--entry-frame", type=int)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument(
        "--seed-list",
        help="comma-separated delivery seeds; overrides --seed-start/--seeds",
    )
    parser.add_argument(
        "--candidates",
        default="pv6,pv8,pv10,cc6,cc8,cfc8",
        help=f"comma-separated names from {','.join(CANDIDATES)}",
    )
    parser.add_argument(
        "--include-decision-trace",
        action="store_true",
        help="include every issued action in diagnostic JSON",
    )
    args = parser.parse_args()
    if args.seeds <= 0:
        raise ValueError("seeds must be positive")
    delivery_seeds = (
        tuple(int(value) for value in args.seed_list.split(",") if value)
        if args.seed_list
        else tuple(range(args.seed_start, args.seed_start + args.seeds))
    )
    if not delivery_seeds:
        raise ValueError("delivery seed set cannot be empty")

    roots = _roots(tuple(args.artifacts), args.entry_frame)
    names = _parse_candidates(args.candidates)
    kernel = NativeSafetyKernel()
    output: dict[str, object] = {
        "entries": tuple({
            "artifact": str(path),
            "frame": root.frame,
            "subroutine": ecl_subroutine_index(_boss(root)),
            "local_time": _boss(root).ecl_time,
            "boss_timer": _boss(root).boss_timer,
            "life": _boss(root).life,
            "x": root.x,
            "y": root.y,
        } for path, root in roots),
        "source_contract": {
            "entry_attack_time": ENTRY_ATTACK_TIME,
            "attack_subroutines": tuple(sorted(ATTACK_SUBROUTINES)),
            "segments": SOURCE_SEGMENTS,
            "exit_subroutine": 23,
        },
        "candidates": {},
    }

    for name in names:
        candidate = CANDIDATES[name]
        results = []
        case_rows = []
        timings: list[float] = []
        reasons: Counter[str] = Counter()
        sources: Counter[str] = Counter()
        started = time.perf_counter()
        for path, root in roots:
            frames = max(1, TIMER_LIMIT - _boss(root).boss_timer + 4)
            for seed in delivery_seeds:
                selected = (
                    ProductionPolicy()
                    if candidate.metric == "production"
                    else FamilyPolicy(kernel, candidate)
                )
                policy = TimedPolicy(selected)
                trace = CaseTrace(root)
                try:
                    result = run_closed_loop(
                        root,
                        policy,
                        frames=frames,
                        delivery_seed=seed,
                        battle_world=True,
                        state_sink=trace,
                        stop_when=_left_phase,
                        stop_outcome="phase-exit",
                    )
                except UnsupportedStatefulModel as exc:
                    timings.extend(policy.elapsed_ms)
                    case_rows.append({
                        "artifact": path.name,
                        "frame": root.frame,
                        "seed": seed,
                        "outcome": "model-stop",
                        "error": str(exc),
                        "final": _source_state(trace.last),
                        "minimum": _source_state(trace.minimum_snapshot),
                        "minimum_clearance": trace.minimum,
                        "policy_calls_by_subroutine": dict(selected.calls),
                    })
                    continue
                results.append(result)
                timings.extend(policy.elapsed_ms)
                if isinstance(selected, ProductionPolicy):
                    reasons.update(selected.reasons)
                    sources.update(selected.sources)
                case_row = {
                    "artifact": path.name,
                    "frame": root.frame,
                    "seed": seed,
                    "outcome": result.outcome,
                    "survived_frames": result.survived_frames,
                    "minimum_clearance": result.minimum_clearance,
                    "commands": result.commands,
                    "born_bullets": result.born_bullets,
                    "final": _source_state(trace.last),
                    "minimum": _source_state(trace.minimum_snapshot),
                    "policy_calls_by_subroutine": dict(selected.calls),
                }
                if args.include_decision_trace:
                    case_row["decision_trace"] = result.decision_trace
                case_rows.append(case_row)
        output["candidates"][name] = {
            "metric": candidate.metric,
            "horizon": candidate.horizon,
            "segment_policies": {
                f"sub{subroutine}:{segment}": {
                    "metric": candidate.policy_for(subroutine, start_time)[0],
                    "horizon": candidate.policy_for(subroutine, start_time)[1],
                    "target": candidate.policy_for(subroutine, start_time)[2],
                }
                for subroutine in sorted(ATTACK_SUBROUTINES)
                for segment, start_time, _stop_time in SOURCE_SEGMENTS[subroutine]
            },
            "outcomes": dict(Counter(
                row["outcome"] for row in case_rows
            )),
            "cases": case_rows,
            "minimum_survived_frames": (
                min(result.survived_frames for result in results)
                if results else None
            ),
            "worst_clearance": (
                min(result.minimum_clearance for result in results)
                if results else None
            ),
            "maximum_commands": (
                max(result.commands for result in results)
                if results else None
            ),
            "mean_commands": (
                statistics.fmean(result.commands for result in results)
                if results else None
            ),
            "decision_ms": {
                "count": len(timings),
                "median": statistics.median(timings) if timings else None,
                "p90": _percentile(timings, 0.90) if timings else None,
                "p99": _percentile(timings, 0.99) if timings else None,
                "maximum": max(timings) if timings else None,
            },
            "decision_reasons": dict(reasons),
            "proposal_sources": dict(sources),
            "elapsed_seconds": time.perf_counter() - started,
        }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

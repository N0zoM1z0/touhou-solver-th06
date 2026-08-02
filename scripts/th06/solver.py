"""Hard authority plus a small deadline-driven progressive proposal solver."""

from __future__ import annotations

import os
import time

from .hazards.lasers import unknown_motion_may_reach_player
from .kernels.safety import NativeSafetyKernel
from .model import (
    ACTIONS,
    Action,
    Decision,
    PLAYER_ALIVE,
    PLAYER_INVULNERABLE,
    Snapshot,
    action_from_input,
)
from .ranking import ProposalRanker
from .safety import DELIVERY_DELAYS, certify_actions
from .viability import nominal_policy_scores


HARD_SAFETY_HORIZON = 4
EFFORT_HORIZONS = (6, 8, 12, 16)
BASE_POLICY_HORIZON = HARD_SAFETY_HORIZON * 2
DECISION_FRAME_MS = 1000.0 / 60.0
DEFAULT_DECISION_BUDGET_MS = DECISION_FRAME_MS * 0.75
FIXED_WORK_EQUIVALENT = 32
MEASUREMENT_WEIGHT = 0.2
PROMOTION_BUDGET_FRACTION = 0.8
INITIAL_POLICY_RATE_GROWTH_PER_SEGMENT = 2.5
POLICY_RATE_HALF_LIFE_FRAMES = 60.0


class EffortController:
    """Estimate affordable rollout work from measurements, not scene bands."""

    def __init__(self, decision_budget_ms: float) -> None:
        if decision_budget_ms <= 0.0:
            raise ValueError("decision budget must be positive")
        self.decision_budget_ms = decision_budget_ms
        self.publication_scale = 1.0
        self.rollout_ms_per_work: float | None = None
        self.policy_ms_per_work: float | None = None
        self.policy_rate_by_horizon: dict[int, float] = {}
        self.policy_frame_by_horizon: dict[int, int] = {}
        self.policy_rate_growth = INITIAL_POLICY_RATE_GROWTH_PER_SEGMENT
        self.last_limit = HARD_SAFETY_HORIZON

    @staticmethod
    def rollout_work(
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
    ) -> int:
        sources = (
            len(snapshot.bullets)
            + len(snapshot.enemies)
            + len(snapshot.lasers)
            + len(snapshot.spawners)
        )
        return (
            (sources + FIXED_WORK_EQUIVALENT)
            * max(1, candidate_count)
            * horizon
        )

    @staticmethod
    def _update_rate(
        previous: float | None,
        elapsed_ms: float,
        work: int,
    ) -> float:
        sample = max(0.0, elapsed_ms) / max(1, work)
        if previous is None:
            return sample
        return (
            previous * (1.0 - MEASUREMENT_WEIGHT)
            + sample * MEASUREMENT_WEIGHT
        )

    def budget_ms(self) -> float:
        return self.decision_budget_ms * self.publication_scale

    def choose_limit(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        elapsed_ms: float,
    ) -> int:
        remaining_ms = self.budget_ms() - elapsed_ms
        if remaining_ms <= 0.0 or candidate_count < 2:
            self.last_limit = HARD_SAFETY_HORIZON
            return self.last_limit

        if self.rollout_ms_per_work is None:
            hard_work = self.rollout_work(
                snapshot,
                candidate_count,
                HARD_SAFETY_HORIZON,
            )
            bootstrap_rate = elapsed_ms / max(1, hard_work)
            first_horizon = EFFORT_HORIZONS[0]
            first_estimate = bootstrap_rate * self.rollout_work(
                snapshot,
                candidate_count,
                first_horizon,
            )
            proposed = (
                first_horizon
                if first_estimate
                <= remaining_ms * PROMOTION_BUDGET_FRACTION
                else HARD_SAFETY_HORIZON
            )
        else:
            proposed = HARD_SAFETY_HORIZON
            for horizon in EFFORT_HORIZONS:
                estimate = self.rollout_ms_per_work * self.rollout_work(
                    snapshot,
                    candidate_count,
                    horizon,
                )
                if estimate > remaining_ms:
                    break
                proposed = horizon

        ladder = (HARD_SAFETY_HORIZON,) + EFFORT_HORIZONS
        if proposed > self.last_limit:
            previous_index = ladder.index(self.last_limit)
            next_horizon = ladder[previous_index + 1]
            rate = self.rollout_ms_per_work
            next_estimate = (
                rate * self.rollout_work(
                    snapshot,
                    candidate_count,
                    next_horizon,
                )
                if rate is not None
                else first_estimate
            )
            proposed = (
                next_horizon
                if next_estimate
                <= remaining_ms * PROMOTION_BUDGET_FRACTION
                else self.last_limit
            )
        self.last_limit = proposed
        return proposed

    def observe_rollout(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
        elapsed_ms: float,
    ) -> None:
        self.rollout_ms_per_work = self._update_rate(
            self.rollout_ms_per_work,
            elapsed_ms,
            self.rollout_work(snapshot, candidate_count, horizon),
        )

    def _effective_policy_rate(
        self,
        snapshot: Snapshot,
        horizon: int,
    ) -> float | None:
        measured_rate = self.policy_rate_by_horizon.get(horizon)
        lower = tuple(
            measured_horizon
            for measured_horizon in self.policy_rate_by_horizon
            if measured_horizon < horizon
        )
        predicted_rate = None
        if lower:
            nearest = max(lower)
            added_segments = max(
                1,
                (horizon - nearest) // HARD_SAFETY_HORIZON,
            )
            predicted_rate = (
                self.policy_rate_by_horizon[nearest]
                * self.policy_rate_growth ** added_segments
            )

        if measured_rate is None:
            return predicted_rate
        if predicted_rate is None:
            return measured_rate

        measured_frame = self.policy_frame_by_horizon.get(horizon)
        age = (
            snapshot.frame - measured_frame
            if measured_frame is not None
            else -1
        )
        freshness = (
            0.5 ** (age / POLICY_RATE_HALF_LIFE_FRAMES)
            if age >= 0
            else 0.0
        )
        return (
            measured_rate * freshness
            + predicted_rate * (1.0 - freshness)
        )

    def policy_affordable(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
        elapsed_ms: float,
    ) -> bool:
        remaining_ms = self.budget_ms() - elapsed_ms
        work = self.rollout_work(snapshot, candidate_count, horizon)
        rate = self._effective_policy_rate(snapshot, horizon)
        estimate = rate * work if rate is not None else None
        fallback_rate = self.policy_ms_per_work or self.rollout_ms_per_work
        if estimate is None and fallback_rate is not None:
            estimate = fallback_rate * work
        return (
            remaining_ms > 0.0
            and estimate is not None
            and estimate <= remaining_ms * PROMOTION_BUDGET_FRACTION
        )

    def observe_policy(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
        elapsed_ms: float,
    ) -> None:
        self.policy_ms_per_work = self._update_rate(
            self.policy_ms_per_work,
            elapsed_ms,
            self.rollout_work(snapshot, candidate_count, horizon),
        )
        work = self.rollout_work(snapshot, candidate_count, horizon)
        measured_rate = self._update_rate(
            self._effective_policy_rate(snapshot, horizon),
            elapsed_ms,
            work,
        )
        lower = tuple(
            measured_horizon
            for measured_horizon in self.policy_rate_by_horizon
            if measured_horizon < horizon
        )
        if lower:
            lower_rate = self.policy_rate_by_horizon[max(lower)]
            if lower_rate > 0.0:
                observed_growth = measured_rate / lower_rate
                self.policy_rate_growth = (
                    self.policy_rate_growth * (1.0 - MEASUREMENT_WEIGHT)
                    + observed_growth * MEASUREMENT_WEIGHT
                )
        self.policy_rate_by_horizon[horizon] = measured_rate
        self.policy_frame_by_horizon[horizon] = snapshot.frame

    def observe_publication(self, stale: bool) -> None:
        if stale:
            self.publication_scale = max(0.25, self.publication_scale * 0.5)
            self.last_limit = HARD_SAFETY_HORIZON
        else:
            self.publication_scale += (1.0 - self.publication_scale) * 0.02


class Solver:
    def __init__(
        self,
        ranker: ProposalRanker | None = None,
        decision_budget_ms: float = DEFAULT_DECISION_BUDGET_MS,
        clock=time.perf_counter,
    ) -> None:
        self.ranker = ranker or ProposalRanker()
        self.kernel = NativeSafetyKernel() if os.name == "nt" else None
        self.backend = "native-c++" if self.kernel is not None else "python-reference"
        self.effort = EffortController(decision_budget_ms)
        self.clock = clock

    def _certify_selected(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
    ):
        if self.kernel is not None:
            return self.kernel.certify_selected(
                snapshot,
                horizon,
                actions,
                collision_margin=0.35,
            )
        return certify_actions(snapshot, horizon, actions=actions)

    def _hard_authority(self, snapshot: Snapshot):
        native = (
            getattr(type(self.kernel), "certify_selected_delivery_sets", None)
            if self.kernel is not None
            else None
        )
        if native is not None:
            return native(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                ACTIONS,
                collision_margin=0.35,
            )
        hard = certify_actions(snapshot, HARD_SAFETY_HORIZON)
        age_zero = (
            certify_actions(
                snapshot,
                HARD_SAFETY_HORIZON,
                DELIVERY_DELAYS[:-1],
            )
            if not hard
            else ()
        )
        return hard, age_zero

    def _prepare_soft(self, snapshot: Snapshot, horizon: int) -> None:
        native = (
            getattr(type(self.kernel), "prepare", None)
            if self.kernel is not None
            else None
        )
        if native is not None:
            native(self.kernel, snapshot, horizon)

    def _policy_scores(self, snapshot: Snapshot, candidates, horizon: int):
        native = (
            getattr(type(self.kernel), "nominal_policy_counts", None)
            if self.kernel is not None
            else None
        )
        if native is not None:
            return native(
                self.kernel,
                snapshot,
                candidates,
                HARD_SAFETY_HORIZON,
                horizon,
                collision_margin=0.35,
            )
        return nominal_policy_scores(
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            horizon,
        )

    def selected_delivery_safe(
        self,
        snapshot: Snapshot,
        action: Action,
        maximum_delay: int,
    ) -> bool:
        if maximum_delay <= DELIVERY_DELAYS[-1]:
            return bool(self._certify_selected(
                snapshot,
                HARD_SAFETY_HORIZON,
                (action,),
            ))
        if maximum_delay != DELIVERY_DELAYS[-1] + 1:
            return False
        native = (
            getattr(
                type(self.kernel),
                "certify_selected_extended_delivery",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is not None:
            return bool(native(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                (action,),
                collision_margin=0.35,
            ))
        return bool(certify_actions(
            snapshot,
            HARD_SAFETY_HORIZON,
            delivery_delays=DELIVERY_DELAYS + (maximum_delay,),
            actions=(action,),
        ))

    def observe(self, survived: bool) -> None:
        self.ranker.observe(survived)

    def observe_publication(self, stale: bool) -> None:
        self.effort.observe_publication(stale)

    def decide(
        self,
        snapshot: Snapshot,
        required_action: Action | None = None,
    ) -> Decision:
        if snapshot.in_menu:
            return Decision(None, (), 0.0, 0, "menu")
        if snapshot.replay_or_demo:
            return Decision(None, (), 0.0, 0, "replay-or-demo")
        if snapshot.time_stopped:
            return Decision(None, (), 0.0, 0, "time-stopped")
        if snapshot.player_state not in (PLAYER_ALIVE, PLAYER_INVULNERABLE):
            return Decision(None, (), 0.0, 0, "player-not-active")
        if not 0.99 <= snapshot.frame_multiplier <= 1.01:
            return Decision(None, (), 0.0, 0, "unsupported-frame-multiplier")
        if snapshot.laser_count != len(snapshot.lasers):
            return Decision(None, (), 0.0, 0, "unsupported-laser-decode")
        if any(
            not laser.motion_known
            and unknown_motion_may_reach_player(
                snapshot,
                laser,
                HARD_SAFETY_HORIZON,
            )
            for laser in snapshot.lasers
        ):
            return Decision(None, (), 0.0, 0, "unsupported-laser-motion")

        if required_action is not None:
            certified = self._certify_selected(
                snapshot,
                1,
                ACTIONS if required_action.focused else (required_action,),
            )
            leased = next(
                (
                    candidate for candidate in certified
                    if candidate.action == required_action
                ),
                None,
            )
            if leased is None:
                return Decision(None, certified, 0.0, 1, "input-lease-unsafe", 1)
            return Decision(
                leased.action,
                certified,
                leased.clearance,
                1,
                "ok",
                1,
            )

        started = self.clock()
        hard, age_zero = self._hard_authority(snapshot)
        if not hard:
            if age_zero:
                chosen = self.ranker.choose(snapshot, age_zero)
                return Decision(
                    chosen.action,
                    age_zero,
                    chosen.clearance,
                    HARD_SAFETY_HORIZON,
                    "same-frame-delivery-only",
                    HARD_SAFETY_HORIZON,
                )
            return Decision(
                None,
                (),
                0.0,
                HARD_SAFETY_HORIZON,
                "hard-safe-set-empty",
                HARD_SAFETY_HORIZON,
            )

        elapsed_ms = (self.clock() - started) * 1000.0
        limit = self.effort.choose_limit(
            snapshot,
            len(hard),
            elapsed_ms,
        )
        frontier = hard
        frontier_horizon = HARD_SAFETY_HORIZON
        contracted = False
        constant_exhausted = False
        policy_exhausted = False
        rollout_ms = 0.0
        rollout_horizon = HARD_SAFETY_HORIZON
        policy_preferred: frozenset[Action] = frozenset()
        policy_horizon = HARD_SAFETY_HORIZON

        if limit > HARD_SAFETY_HORIZON:
            operation_started = self.clock()
            self._prepare_soft(snapshot, limit)
            rollout_ms += (self.clock() - operation_started) * 1000.0
            for horizon in EFFORT_HORIZONS:
                if horizon > limit:
                    break
                if not constant_exhausted:
                    operation_started = self.clock()
                    next_frontier = self._certify_selected(
                        snapshot,
                        horizon,
                        tuple(candidate.action for candidate in frontier),
                    )
                    rollout_ms += (
                        self.clock() - operation_started
                    ) * 1000.0
                    rollout_horizon = horizon
                    if len(next_frontier) < len(frontier):
                        contracted = True
                    if next_frontier:
                        frontier = next_frontier
                        frontier_horizon = horizon
                    else:
                        constant_exhausted = True

                if (
                    horizon < BASE_POLICY_HORIZON
                    or len(hard) <= 1
                    or policy_exhausted
                    or (
                        horizon > BASE_POLICY_HORIZON
                        and not contracted
                    )
                ):
                    continue
                elapsed_ms = (self.clock() - started) * 1000.0
                if not self.effort.policy_affordable(
                    snapshot,
                    len(hard),
                    horizon,
                    elapsed_ms,
                ):
                    policy_exhausted = True
                    continue
                policy_started = self.clock()
                scores = self._policy_scores(
                    snapshot,
                    hard,
                    horizon,
                )
                policy_ms = (self.clock() - policy_started) * 1000.0
                self.effort.observe_policy(
                    snapshot,
                    len(hard),
                    horizon,
                    policy_ms,
                )
                allowed = frozenset(candidate.action for candidate in hard)
                best_score = max(
                    (
                        score for action, score in scores.items()
                        if action in allowed
                    ),
                    default=0,
                )
                if best_score > 0:
                    policy_preferred = frozenset(
                        action for action, score in scores.items()
                        if score == best_score
                        and action in allowed
                    )
                    policy_horizon = horizon

            self.effort.observe_rollout(
                snapshot,
                len(hard),
                rollout_horizon,
                rollout_ms,
            )

        preferred = policy_preferred or (
            frozenset(candidate.action for candidate in frontier)
            if frontier_horizon > HARD_SAFETY_HORIZON
            else frozenset()
        )

        chosen = self.ranker.choose(
            snapshot,
            hard,
            preferred,
            commitment_frames=HARD_SAFETY_HORIZON,
        )
        held = action_from_input(snapshot.input_mask)
        held_horizon = (
            frontier_horizon
            if any(candidate.action == held for candidate in frontier)
            else HARD_SAFETY_HORIZON
        )
        return Decision(
            chosen.action,
            hard,
            chosen.clearance,
            HARD_SAFETY_HORIZON,
            "ok",
            max(frontier_horizon, policy_horizon),
            len(preferred),
            0,
            held_horizon,
        )

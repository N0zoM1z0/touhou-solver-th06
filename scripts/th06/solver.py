"""Hard authority plus a small deadline-driven progressive proposal solver."""

from __future__ import annotations

import math
import os
import time

from .guidance import terminal_guidance_scores
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
COST_RATE_HALF_LIFE_FRAMES = 60.0


class EffortController:
    """Estimate affordable rollout work from measurements, not scene bands."""

    def __init__(self, decision_budget_ms: float) -> None:
        if decision_budget_ms <= 0.0:
            raise ValueError("decision budget must be positive")
        self.decision_budget_ms = decision_budget_ms
        self.publication_scale = 1.0
        self.rollout_ms_per_work: float | None = None
        self.rollout_frame: int | None = None
        self.policy_ms_per_work: float | None = None
        self.policy_rate_by_horizon: dict[int, float] = {}
        self.policy_frame_by_horizon: dict[int, int] = {}
        self.target_rate_by_kind: dict[str, dict[int, float]] = {
            "acquire": {},
            "track": {},
        }
        self.target_frame_by_kind: dict[str, dict[int, int]] = {
            "acquire": {},
            "track": {},
        }
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

    @staticmethod
    def _measurement_freshness(
        snapshot_frame: int,
        measured_frame: int | None,
    ) -> float:
        age = (
            snapshot_frame - measured_frame
            if measured_frame is not None
            else -1
        )
        return (
            0.5 ** (age / COST_RATE_HALF_LIFE_FRAMES)
            if age >= 0
            else 0.0
        )

    def _effective_rollout_rate(
        self,
        snapshot: Snapshot,
        current_rate: float,
    ) -> float:
        if self.rollout_ms_per_work is None:
            return current_rate
        freshness = self._measurement_freshness(
            snapshot.frame,
            self.rollout_frame,
        )
        return (
            self.rollout_ms_per_work * freshness
            + current_rate * (1.0 - freshness)
        )

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

        hard_work = self.rollout_work(
            snapshot,
            candidate_count,
            HARD_SAFETY_HORIZON,
        )
        bootstrap_rate = elapsed_ms / max(1, hard_work)
        rate = self._effective_rollout_rate(snapshot, bootstrap_rate)
        if self.rollout_ms_per_work is None:
            first_horizon = EFFORT_HORIZONS[0]
            first_estimate = rate * self.rollout_work(
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
                estimate = rate * self.rollout_work(
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
            next_estimate = rate * self.rollout_work(
                snapshot,
                candidate_count,
                next_horizon,
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
        work = self.rollout_work(snapshot, candidate_count, horizon)
        sample_rate = max(0.0, elapsed_ms) / max(1, work)
        self.rollout_ms_per_work = self._update_rate(
            self._effective_rollout_rate(snapshot, sample_rate),
            elapsed_ms,
            work,
        )
        self.rollout_frame = snapshot.frame

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

        freshness = self._measurement_freshness(
            snapshot.frame,
            self.policy_frame_by_horizon.get(horizon),
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

    def _effective_target_rate(
        self,
        kind: str,
        snapshot: Snapshot,
        horizon: int,
    ) -> float | None:
        rates = self.target_rate_by_kind[kind]
        frames = self.target_frame_by_kind[kind]
        measured = rates.get(horizon)
        lower = tuple(value for value in rates if value < horizon)
        predicted = None
        if lower:
            nearest = max(lower)
            added_segments = max(
                1,
                (horizon - nearest) // HARD_SAFETY_HORIZON,
            )
            predicted = (
                rates[nearest]
                * self.policy_rate_growth ** added_segments
            )
        fallback = self._effective_policy_rate(snapshot, horizon)
        if fallback is None:
            fallback = self.policy_ms_per_work or self.rollout_ms_per_work
        if predicted is None:
            predicted = fallback
        if measured is None:
            return predicted
        if predicted is None:
            return measured
        freshness = self._measurement_freshness(
            snapshot.frame,
            frames.get(horizon),
        )
        return measured * freshness + predicted * (1.0 - freshness)

    def target_affordable(
        self,
        kind: str,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
        elapsed_ms: float,
    ) -> bool:
        remaining_ms = self.budget_ms() - elapsed_ms
        rate = self._effective_target_rate(kind, snapshot, horizon)
        estimate = (
            rate * self.rollout_work(snapshot, candidate_count, horizon)
            if rate is not None
            else None
        )
        return (
            remaining_ms > 0.0
            and estimate is not None
            and estimate <= remaining_ms * PROMOTION_BUDGET_FRACTION
        )

    def observe_target(
        self,
        kind: str,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
        elapsed_ms: float,
    ) -> None:
        work = self.rollout_work(snapshot, candidate_count, horizon)
        effective = self._effective_target_rate(kind, snapshot, horizon)
        self.target_rate_by_kind[kind][horizon] = self._update_rate(
            effective,
            elapsed_ms,
            work,
        )
        self.target_frame_by_kind[kind][horizon] = snapshot.frame

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
        self.guidance_target: tuple[float, float] | None = None
        self.guidance_deadline: int | None = None
        self.pending_target_action: Action | None = None
        self.pending_target_horizon = HARD_SAFETY_HORIZON
        self.guidance_last_frame: int | None = None

    def _clear_target(self) -> None:
        self.guidance_target = None
        self.guidance_deadline = None

    def _terminal_guidance(
        self,
        snapshot: Snapshot,
        candidates,
        horizon: int,
        target: tuple[float, float] | None = None,
    ):
        native = (
            getattr(type(self.kernel), "terminal_guidance", None)
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
                target=target,
            )
        if self.kernel is not None:
            return None
        return terminal_guidance_scores(
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            horizon,
            target,
        )

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
        if (
            self.guidance_last_frame is not None
            and snapshot.frame <= self.guidance_last_frame
        ):
            self._clear_target()
            self.pending_target_action = None
        self.guidance_last_frame = snapshot.frame
        if (
            self.guidance_deadline is not None
            and snapshot.frame >= self.guidance_deadline
        ):
            self._clear_target()
        if snapshot.in_menu:
            self._clear_target()
            self.pending_target_action = None
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
        target_guided = False
        target_invalid = False
        acquired_pending_target = False
        last_target_horizon = 0

        if limit > HARD_SAFETY_HORIZON:
            operation_started = self.clock()
            self._prepare_soft(snapshot, limit)
            rollout_ms += (self.clock() - operation_started) * 1000.0
            observed_held = action_from_input(snapshot.input_mask)
            pending_candidate = next(
                (
                    candidate
                    for candidate in hard
                    if (
                        candidate.action == self.pending_target_action
                        and candidate.action == observed_held
                    )
                ),
                None,
            )
            elapsed_ms = (self.clock() - started) * 1000.0
            acquisition_horizon = min(
                limit,
                self.pending_target_horizon,
            )
            if (
                pending_candidate is not None
                and self.effort.target_affordable(
                    "acquire",
                    snapshot,
                    1,
                    acquisition_horizon,
                    elapsed_ms,
                )
            ):
                guidance_started = self.clock()
                guidance = self._terminal_guidance(
                    snapshot,
                    (pending_candidate,),
                    acquisition_horizon,
                )
                guidance_ms = (
                    self.clock() - guidance_started
                ) * 1000.0
                if guidance is not None:
                    self.effort.observe_target(
                        "acquire",
                        snapshot,
                        1,
                        acquisition_horizon,
                        guidance_ms,
                    )
                    value = guidance.get(pending_candidate.action)
                    if (
                        value is not None
                        and value.terminal_count > 0
                        and math.isfinite(value.free_clearance)
                    ):
                        self.guidance_target = (
                            value.free_x,
                            value.free_y,
                        )
                        self.guidance_deadline = (
                            snapshot.frame + acquisition_horizon
                        )
                        policy_preferred = frozenset(
                            (pending_candidate.action,)
                        )
                        policy_horizon = acquisition_horizon
                        acquired_pending_target = True
                self.pending_target_action = None
            elif pending_candidate is None:
                self.pending_target_action = None

            for horizon in (() if acquired_pending_target else EFFORT_HORIZONS):
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
                        self.guidance_target is None
                        and
                        horizon > BASE_POLICY_HORIZON
                        and not contracted
                    )
                ):
                    continue
                if self.guidance_target is not None:
                    remaining = max(
                        HARD_SAFETY_HORIZON,
                        (self.guidance_deadline or snapshot.frame)
                        - snapshot.frame,
                    )
                    if horizon > remaining and last_target_horizon > 0:
                        continue
                    effective_horizon = min(horizon, remaining)
                    if effective_horizon <= last_target_horizon:
                        continue
                else:
                    effective_horizon = horizon
                elapsed_ms = (self.clock() - started) * 1000.0
                affordable = (
                    self.effort.target_affordable(
                        "track",
                        snapshot,
                        len(hard),
                        effective_horizon,
                        elapsed_ms,
                    )
                    if self.guidance_target is not None
                    else self.effort.policy_affordable(
                        snapshot,
                        len(hard),
                        effective_horizon,
                        elapsed_ms,
                    )
                )
                if not affordable:
                    policy_exhausted = True
                    continue
                policy_started = self.clock()
                if self.guidance_target is not None:
                    guidance = self._terminal_guidance(
                        snapshot,
                        hard,
                        effective_horizon,
                        self.guidance_target,
                    )
                    last_target_horizon = effective_horizon
                    scores = None
                else:
                    guidance = None
                    scores = self._policy_scores(
                        snapshot,
                        hard,
                        horizon,
                    )
                policy_ms = (self.clock() - policy_started) * 1000.0
                if self.guidance_target is not None:
                    self.effort.observe_target(
                        "track",
                        snapshot,
                        len(hard),
                        effective_horizon,
                        policy_ms,
                    )
                else:
                    self.effort.observe_policy(
                        snapshot,
                        len(hard),
                        effective_horizon,
                        policy_ms,
                    )
                allowed = frozenset(candidate.action for candidate in hard)
                if guidance is not None:
                    reachable = {
                        action: value.target_distance_squared
                        for action, value in guidance.items()
                        if (
                            action in allowed
                            and value.terminal_count > 0
                            and math.isfinite(
                                value.target_distance_squared
                            )
                        )
                    }
                    if reachable:
                        best_distance = min(reachable.values())
                        policy_preferred = frozenset(
                            action
                            for action, distance in reachable.items()
                            if distance == best_distance
                        )
                        policy_horizon = effective_horizon
                        target_guided = True
                    else:
                        if not target_guided:
                            target_invalid = True
                        policy_exhausted = True
                    continue
                if scores is None:
                    policy_exhausted = True
                    continue
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

            if (
                self.guidance_target is not None
                and not acquired_pending_target
                and target_invalid
            ):
                self._clear_target()

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
        if (
            self.guidance_target is None
            and len(policy_preferred) == 1
            and policy_horizon > HARD_SAFETY_HORIZON
            and chosen.action != held
        ):
            self.pending_target_action = chosen.action
            self.pending_target_horizon = policy_horizon
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

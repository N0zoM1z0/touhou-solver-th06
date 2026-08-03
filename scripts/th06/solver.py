"""Hard authority plus a small deadline-driven progressive proposal solver."""

from __future__ import annotations

import math
import os
import time

from .attack import preferred_suppression_actions, suppression_target
from .guidance import preferred_target_actions, terminal_guidance_scores
from .hazards.lasers import unknown_motion_may_reach_player
from .kernels.safety import NativeSafetyKernel
from .model import (
    ACTIONS,
    CONTROL_ACTIONS,
    Action,
    Decision,
    PLAYER_ALIVE,
    PLAYER_INVULNERABLE,
    Snapshot,
    action_from_input,
)
from .ranking import ProposalRanker, precision_preferred_actions
from .safety import DELIVERY_DELAYS, certify_actions
from .viability import nominal_policy_scores


HARD_SAFETY_HORIZON = 4
HARD_CURRENT_HOLD_HORIZON = HARD_SAFETY_HORIZON + 1
EFFORT_HORIZONS = (6, 8, 12, 16, 20)
TURN_CAPABLE_POLICY_HORIZONS = (8, 12, 16)
COARSE_GLOBAL_HORIZONS = (24, 32, 40, 48)
BASE_POLICY_HORIZON = HARD_SAFETY_HORIZON * 2
DECISION_FRAME_MS = 1000.0 / 60.0
DEFAULT_DECISION_BUDGET_MS = DECISION_FRAME_MS * 0.75
SAME_FRAME_DECISION_BUDGET_MS = DECISION_FRAME_MS * 0.5
FIXED_WORK_EQUIVALENT = 32
MEASUREMENT_WEIGHT = 0.2
PROMOTION_BUDGET_FRACTION = 0.8
INITIAL_POLICY_RATE_GROWTH_PER_SEGMENT = 2.5
COST_RATE_HALF_LIFE_FRAMES = 60.0
# Measured room for the native return, Python ranking, and publication handoff.
POLICY_DEADLINE_GUARD_MS = 0.5
# Exact terminal layers poll their deadline in batches; leave room for the
# final poll overshoot as well as the ordinary publication handoff.
TERMINAL_DEADLINE_GUARD_MS = 1.5
BASE_RECOVERY_CONFIRMATIONS = 2
PUBLICATION_RECOVERY_CONFIRMATIONS = 2


class EffortController:
    """Estimate affordable rollout work from measurements, not scene bands."""

    def __init__(self, decision_budget_ms: float) -> None:
        if decision_budget_ms <= 0.0:
            raise ValueError("decision budget must be positive")
        self.decision_budget_ms = decision_budget_ms
        self.decision_budget_cap_ms: float | None = None
        self.publication_scale = 1.0
        self.rollout_ms_per_work: float | None = None
        self.rollout_frame: int | None = None
        self.projection_ms_per_work: float | None = None
        self.projection_frame: int | None = None
        self.policy_ms_per_work: float | None = None
        self.policy_rate_by_horizon: dict[int, float] = {}
        self.policy_frame_by_horizon: dict[int, int] = {}
        self.policy_probe_rate_by_horizon: dict[int, float] = {}
        self.policy_probe_frame_by_horizon: dict[int, int] = {}
        self.policy_probe_candidate_count_by_horizon: dict[int, int] = {}
        self.policy_probe_timeout_frame_by_horizon: dict[int, int] = {}
        self.target_rate_by_kind: dict[str, dict[int, float]] = {
            "acquire": {},
            "track": {},
            "survival": {},
        }
        self.target_frame_by_kind: dict[str, dict[int, int]] = {
            "acquire": {},
            "track": {},
            "survival": {},
        }
        self.policy_rate_growth = INITIAL_POLICY_RATE_GROWTH_PER_SEGMENT
        self.last_limit = HARD_SAFETY_HORIZON
        self.base_recovery_confirmations = 0
        self.base_recovery_last_frame: int | None = None
        self.publication_recovery_confirmations = 0

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
    def projection_work(snapshot: Snapshot, horizon: int) -> int:
        """Work proxy for candidate-independent hazard/ECL preparation."""
        sources = (
            len(snapshot.bullets)
            + len(snapshot.enemies)
            + len(snapshot.lasers)
            + len(snapshot.spawners)
        )
        return (sources + FIXED_WORK_EQUIVALENT) * horizon

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
        budget = self.decision_budget_ms * self.publication_scale
        if self.decision_budget_cap_ms is not None:
            budget = min(budget, self.decision_budget_cap_ms)
        return budget

    def begin_decision(self) -> None:
        self.decision_budget_cap_ms = None

    def require_same_frame_publication(self) -> None:
        self.decision_budget_cap_ms = SAME_FRAME_DECISION_BUDGET_MS

    def full_publication_budget_available(self) -> bool:
        return (
            self.decision_budget_cap_ms is None
            and self.publication_scale >= 1.0
        )

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
            self.base_recovery_confirmations = 0
            self.base_recovery_last_frame = None
            return self.last_limit

        hard_work = self.rollout_work(
            snapshot,
            candidate_count,
            HARD_SAFETY_HORIZON,
        )
        bootstrap_rate = elapsed_ms / max(1, hard_work)
        rate = self._effective_rollout_rate(snapshot, bootstrap_rate)
        base_bootstrap_estimate = bootstrap_rate * self.rollout_work(
            snapshot,
            candidate_count,
            BASE_POLICY_HORIZON,
        )
        projection_estimate = (
            self.projection_ms_per_work
            * self.projection_work(snapshot, BASE_POLICY_HORIZON)
            if self.projection_ms_per_work is not None
            else None
        )
        # Projection is independent of the number of candidate actions and
        # is not a horizon-scaled copy of Hard certification.  Once measured,
        # use that causal cost to decide whether the uninterruptible p8 hazard
        # build fits.  The native terminal search receives only the residual
        # budget and remains complete-or-discard.
        base_projection_affordable = (
            projection_estimate is not None
            and projection_estimate
            <= max(0.0, remaining_ms - TERMINAL_DEADLINE_GUARD_MS)
        )
        projection_measurement_stale = (
            self.projection_ms_per_work is not None
            and self._measurement_freshness(
                snapshot.frame,
                self.projection_frame,
            ) < 0.5
        )
        base_projection_probe_due = (
            self.last_limit < BASE_POLICY_HORIZON
            and projection_measurement_stale
            and remaining_ms > TERMINAL_DEADLINE_GUARD_MS
        )
        if (
            self.rollout_ms_per_work is not None
            and self.last_limit < BASE_POLICY_HORIZON
            and (
                base_projection_affordable
                or base_bootstrap_estimate
                <= remaining_ms * PROMOTION_BUDGET_FRACTION
            )
        ):
            if (
                self.base_recovery_last_frame is None
                or snapshot.frame > self.base_recovery_last_frame
            ):
                self.base_recovery_confirmations += 1
            else:
                self.base_recovery_confirmations = 1
            self.base_recovery_last_frame = snapshot.frame
        else:
            self.base_recovery_confirmations = 0
            self.base_recovery_last_frame = None
        base_recovery_confirmed = (
            self.base_recovery_confirmations
            >= BASE_RECOVERY_CONFIRMATIONS
        )
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

        if (
            self.last_limit >= BASE_POLICY_HORIZON
            and base_projection_affordable
        ):
            proposed = max(proposed, BASE_POLICY_HORIZON)

        # A recent expensive projection remains authoritative after one cheap
        # Hard sample.  Two independent current samples can reopen p8 under
        # the same promotion reserve; otherwise one transient spike can lock
        # out the first turn-capable continuation until the route is lost.
        if base_recovery_confirmed:
            proposed = max(proposed, BASE_POLICY_HORIZON)
        # Projection cost can change discontinuously after a forecast birth
        # becomes a current bullet set.  A once-expensive p8 preparation must
        # not remain closed forever merely because no later preparation was
        # allowed to replace that estimate.  Probe one ordinary base rung
        # only after its cost evidence has aged past the generic half-life and
        # current Hard work leaves the publication guard.  The preparation is
        # measured immediately; the native terminal rung remains strictly
        # complete-or-discard, and a late result is still rejected by the
        # physical publication check.
        if base_projection_probe_due:
            proposed = max(proposed, BASE_POLICY_HORIZON)

        ladder = (HARD_SAFETY_HORIZON,) + EFFORT_HORIZONS
        if proposed > self.last_limit:
            # Progress through every currently measured-affordable rung in
            # this decision. Requiring one physical decision per rung adds
            # several publication/lease frames and can lose a short-lived
            # continuation even though the deeper work already fits the
            # current budget estimate.
            promoted = self.last_limit
            for horizon in ladder:
                if (
                    horizon <= self.last_limit
                    or horizon > proposed
                ):
                    continue
                if (
                    base_recovery_confirmed
                    and base_projection_affordable
                    and horizon <= BASE_POLICY_HORIZON
                ):
                    promoted = horizon
                    continue
                if (
                    base_projection_probe_due
                    and horizon <= BASE_POLICY_HORIZON
                ):
                    promoted = horizon
                    continue
                promotion_rate = (
                    bootstrap_rate
                    if (
                        base_recovery_confirmed
                        and horizon <= BASE_POLICY_HORIZON
                    )
                    else rate
                )
                estimate = promotion_rate * self.rollout_work(
                    snapshot,
                    candidate_count,
                    horizon,
                )
                if estimate > remaining_ms * PROMOTION_BUDGET_FRACTION:
                    break
                promoted = horizon
            proposed = promoted
        self.last_limit = proposed
        if proposed >= BASE_POLICY_HORIZON:
            self.base_recovery_confirmations = 0
            self.base_recovery_last_frame = None
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

    def observe_projection(
        self,
        snapshot: Snapshot,
        horizon: int,
        elapsed_ms: float,
    ) -> None:
        """Measure only the candidate-independent hazard/ECL build."""
        previous = self.projection_ms_per_work
        if (
            previous is not None
            and self._measurement_freshness(
                snapshot.frame,
                self.projection_frame,
            ) < 0.5
        ):
            # This sample was admitted specifically because the previous
            # projection cost had aged out.  Keeping most of that stale value
            # through the ordinary EMA would immediately close the rung again
            # without allowing the new measurement to be falsifiable.
            previous = None
        self.projection_ms_per_work = self._update_rate(
            previous,
            elapsed_ms,
            self.projection_work(snapshot, horizon),
        )
        self.projection_frame = snapshot.frame

    def observe_projection_extension(
        self,
        snapshot: Snapshot,
        previous_horizon: int,
        horizon: int,
        elapsed_ms: float,
    ) -> None:
        """Record cached extension work as an equivalent full projection."""
        span = horizon - previous_horizon
        if span <= 0:
            return
        self.observe_projection(
            snapshot,
            horizon,
            elapsed_ms * horizon / span,
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
        estimate = self.policy_estimate_ms(
            snapshot,
            candidate_count,
            horizon,
        )
        return (
            remaining_ms > 0.0
            and estimate is not None
            and estimate <= remaining_ms * PROMOTION_BUDGET_FRACTION
        )

    def continuation_extension_affordable(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        previous_horizon: int,
        horizon: int,
        elapsed_ms: float,
    ) -> bool:
        """Whether measured marginal projection plus one exact rung fits."""
        remaining_ms = (
            self.budget_ms()
            - elapsed_ms
            - TERMINAL_DEADLINE_GUARD_MS
        )
        if (
            remaining_ms <= 0.0
            or horizon <= previous_horizon
            or self.projection_ms_per_work is None
            or self._measurement_freshness(
                snapshot.frame,
                self.projection_frame,
            ) < 0.5
        ):
            return False
        projection_estimate = self.projection_ms_per_work * (
            self.projection_work(snapshot, horizon)
            - self.projection_work(snapshot, previous_horizon)
        )
        policy_estimate = self.policy_estimate_ms(
            snapshot,
            candidate_count,
            horizon,
        )
        return (
            policy_estimate is not None
            and projection_estimate + policy_estimate
                <= remaining_ms * PROMOTION_BUDGET_FRACTION
        )

    def policy_estimate_ms(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
    ) -> float | None:
        work = self.rollout_work(snapshot, candidate_count, horizon)
        rate = self._effective_policy_rate(snapshot, horizon)
        estimate = rate * work if rate is not None else None
        fallback_rate = self.policy_ms_per_work or self.rollout_ms_per_work
        if estimate is None and fallback_rate is not None:
            estimate = fallback_rate * work
        return estimate

    def policy_probe_budget_ms(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
        remaining_ms: float,
    ) -> float:
        """Bound one uncertain deep probe from its latest completed sample."""
        if remaining_ms <= 0.0:
            return 0.0
        sample_rate = self.policy_probe_rate_by_horizon.get(horizon)
        if sample_rate is None:
            return remaining_ms
        freshness = self._measurement_freshness(
            snapshot.frame,
            self.policy_probe_frame_by_horizon.get(horizon),
        )
        if freshness < 0.5:
            return remaining_ms
        # The native recursive continuation cache is shared by every first
        # action.  Reducing the first-action shortlist therefore does not
        # reduce the measured probe cost in direct proportion to its length.
        # Keep the last completed candidate count as a work floor; a larger
        # current set can still raise the estimate, while a smaller set gets
        # enough time to repeat work already observed to complete.
        measured_candidate_count = (
            self.policy_probe_candidate_count_by_horizon.get(
                horizon,
                candidate_count,
            )
        )
        measured_ms = sample_rate * self.rollout_work(
            snapshot,
            max(candidate_count, measured_candidate_count),
            horizon,
        )
        return min(remaining_ms, max(0.0, measured_ms))

    def policy_probe_evidence_fresh(
        self,
        snapshot: Snapshot,
        horizon: int,
    ) -> bool:
        completed_freshness = self._measurement_freshness(
            snapshot.frame,
            self.policy_probe_frame_by_horizon.get(horizon),
        )
        timeout_freshness = self._measurement_freshness(
            snapshot.frame,
            self.policy_probe_timeout_frame_by_horizon.get(horizon),
        )
        return max(completed_freshness, timeout_freshness) >= 0.5

    def policy_probe_timeout_fresh(
        self,
        snapshot: Snapshot,
        horizon: int,
    ) -> bool:
        return self._measurement_freshness(
            snapshot.frame,
            self.policy_probe_timeout_frame_by_horizon.get(horizon),
        ) >= 0.5

    def observe_policy_timeout(
        self,
        snapshot: Snapshot,
        horizon: int,
    ) -> None:
        self.policy_probe_timeout_frame_by_horizon[horizon] = snapshot.frame

    def observe_policy(
        self,
        snapshot: Snapshot,
        candidate_count: int,
        horizon: int,
        elapsed_ms: float,
    ) -> None:
        self.policy_probe_timeout_frame_by_horizon.pop(horizon, None)
        work = self.rollout_work(snapshot, candidate_count, horizon)
        self.policy_probe_rate_by_horizon[horizon] = (
            max(0.0, elapsed_ms) / max(1, work)
        )
        self.policy_probe_frame_by_horizon[horizon] = snapshot.frame
        self.policy_probe_candidate_count_by_horizon[horizon] = (
            candidate_count
        )
        self.policy_ms_per_work = self._update_rate(
            self.policy_ms_per_work,
            elapsed_ms,
            work,
        )
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
            self.base_recovery_confirmations = 0
            self.base_recovery_last_frame = None
            self.publication_recovery_confirmations = 0
        else:
            if self.publication_scale < 1.0:
                self.publication_recovery_confirmations += 1
                if (
                    self.publication_recovery_confirmations
                    >= PUBLICATION_RECOVERY_CONFIRMATIONS
                ):
                    # The stale proposal was never published.  Two subsequent
                    # on-time Hard publications are fresh physical evidence
                    # that the transient latency has passed; keeping the
                    # compute penalty for dozens more frames can itself starve
                    # the first turn-capable continuation.
                    self.publication_scale = 1.0
                    self.publication_recovery_confirmations = 0
                else:
                    self.publication_scale += (
                        1.0 - self.publication_scale
                    ) * 0.02
            else:
                self.publication_recovery_confirmations = 0


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

    def reset_plan(self) -> None:
        """Discard soft continuation state without changing Hard authority."""
        self._clear_target()
        self.pending_target_action = None
        self.pending_target_horizon = HARD_SAFETY_HORIZON
        self.guidance_last_frame = None
        self.ranker.reset_plan()

    def _terminal_guidance(
        self,
        snapshot: Snapshot,
        candidates,
        horizon: int,
        target: tuple[float, float] | None = None,
        budget_ms: float | None = None,
    ):
        if budget_ms is not None and budget_ms <= 0.0:
            return None
        budgeted_native = (
            getattr(type(self.kernel), "terminal_guidance_budgeted", None)
            if self.kernel is not None and budget_ms is not None
            else None
        )
        if budgeted_native is not None:
            return budgeted_native(
                self.kernel,
                snapshot,
                candidates,
                HARD_SAFETY_HORIZON,
                horizon,
                collision_margin=0.35,
                budget_ms=budget_ms,
                target=target,
            )
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
            continuation_actions=CONTROL_ACTIONS,
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

    def _budgeted_certify_selected(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
        budget_ms: float,
    ):
        native = (
            getattr(type(self.kernel), "certify_selected_budgeted", None)
            if self.kernel is not None
            else None
        )
        if native is None:
            return self._certify_selected(snapshot, horizon, actions)
        if budget_ms <= 0.0:
            return None
        return native(
            self.kernel,
            snapshot,
            horizon,
            actions,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )

    def _hard_authority(self, snapshot: Snapshot):
        held = action_from_input(snapshot.input_mask)
        reserved = (
            getattr(
                type(self.kernel),
                "certify_delivery_sets_with_selected_reserved",
                None,
            )
            if self.kernel is not None
            else None
        )
        if reserved is not None:
            # Prepare the ordinary local continuation window once.  Hard and
            # the current-input reserve keep their exact h4/h5 certification
            # boundaries; only the immutable hazard projection is shared.
            return reserved(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                HARD_CURRENT_HOLD_HORIZON,
                BASE_POLICY_HORIZON,
                (held,),
                collision_margin=0.35,
            )
        combined = (
            getattr(
                type(self.kernel),
                "certify_delivery_sets_with_selected",
                None,
            )
            if self.kernel is not None
            else None
        )
        if combined is not None:
            # This independently certified current-input guard permits only a
            # late no-write retry; it never enlarges Hard-4 eligibility.
            return combined(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                HARD_CURRENT_HOLD_HORIZON,
                (held,),
                collision_margin=0.35,
            )
        native = (
            getattr(type(self.kernel), "certify_selected_delivery_sets", None)
            if self.kernel is not None
            else None
        )
        if native is not None:
            hard, age_zero = native(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                CONTROL_ACTIONS,
                collision_margin=0.35,
            )
            return hard, age_zero, ()
        hard = certify_actions(
            snapshot,
            HARD_SAFETY_HORIZON,
            actions=CONTROL_ACTIONS,
        )
        age_zero = (
            certify_actions(
                snapshot,
                HARD_SAFETY_HORIZON,
                DELIVERY_DELAYS[:-1],
                actions=CONTROL_ACTIONS,
            )
            if not hard
            else ()
        )
        held_safe = (
            certify_actions(
                snapshot,
                HARD_CURRENT_HOLD_HORIZON,
                actions=(held,),
            )
            if any(candidate.action == held for candidate in hard)
            else ()
        )
        return hard, age_zero, held_safe

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
            continuation_actions=CONTROL_ACTIONS,
        )

    def _budgeted_policy_scores(
        self,
        snapshot: Snapshot,
        candidates,
        horizon: int,
        budget_ms: float,
    ):
        native = (
            getattr(
                type(self.kernel),
                "nominal_policy_counts_budgeted",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None:
            return None
        return native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            horizon,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )

    def _budgeted_progressive_reachability(
        self,
        snapshot: Snapshot,
        candidates,
        maximum_horizon: int,
        budget_ms: float,
    ):
        native = (
            getattr(
                type(self.kernel),
                "boolean_reachability_progressive",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None:
            return None
        return native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            BASE_POLICY_HORIZON,
            maximum_horizon,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )

    def _budgeted_terminal_counts(
        self,
        snapshot: Snapshot,
        candidates,
        horizon: int,
        budget_ms: float,
    ):
        native = (
            getattr(
                type(self.kernel),
                "terminal_counts_budgeted",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None:
            return None
        return native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            horizon,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )

    def _budgeted_replanning_scores(
        self,
        snapshot: Snapshot,
        candidates,
        budget_ms: float,
    ):
        progressive = (
            getattr(
                type(self.kernel),
                "replanning_scores_progressive_budgeted",
                None,
            )
            if self.kernel is not None
            else None
        )
        if progressive is not None and budget_ms > 0.0:
            return progressive(
                self.kernel,
                snapshot,
                candidates,
                HARD_SAFETY_HORIZON,
                BASE_POLICY_HORIZON,
                collision_margin=0.35,
                budget_ms=budget_ms,
            )
        native = (
            getattr(
                type(self.kernel),
                "replanning_scores_budgeted",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None or budget_ms <= 0.0:
            return None
        result = native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            BASE_POLICY_HORIZON,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )
        return None if result is None else (result, True)

    def _budgeted_replanning_viability(
        self,
        snapshot: Snapshot,
        candidates,
        budget_ms: float,
    ):
        native = (
            getattr(
                type(self.kernel),
                "replanning_viability_budgeted",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None:
            return self._budgeted_replanning_scores(
                snapshot,
                candidates,
                budget_ms,
            )
        if budget_ms <= 0.0:
            return None
        result = native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            BASE_POLICY_HORIZON,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )
        return None if result is None else (result, False)

    def _budgeted_progressive_terminal_counts(
        self,
        snapshot: Snapshot,
        candidates,
        minimum_horizon: int,
        maximum_horizon: int,
        budget_ms: float,
        guidance_action: Action | None = None,
    ):
        guidance_native = (
            getattr(
                type(self.kernel),
                "segment_terminal_guidance_progressive",
                None,
            )
            if self.kernel is not None and guidance_action is not None
            else None
        )
        if guidance_native is not None:
            return guidance_native(
                self.kernel,
                snapshot,
                candidates,
                HARD_SAFETY_HORIZON,
                minimum_horizon,
                maximum_horizon,
                guidance_action,
                collision_margin=0.35,
                budget_ms=budget_ms,
            )
        native = (
            getattr(
                type(self.kernel),
                "segment_terminal_counts_progressive",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None:
            return None
        return native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            minimum_horizon,
            maximum_horizon,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )

    def _budgeted_delivery_segment_viability(
        self,
        snapshot: Snapshot,
        candidates,
        horizon: int,
        budget_ms: float,
    ):
        native = (
            getattr(
                type(self.kernel),
                "delivery_segment_viability_progressive",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None or budget_ms <= 0.0:
            return None
        return native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            horizon,
            horizon,
            collision_margin=0.35,
            budget_ms=budget_ms,
        )

    def _budgeted_macro_tail_scores(
        self,
        snapshot: Snapshot,
        candidates,
        horizon: int,
        budget_ms: float,
    ):
        native = (
            getattr(
                type(self.kernel),
                "macro_tail_scores_budgeted",
                None,
            )
            if self.kernel is not None
            else None
        )
        if native is None or budget_ms <= 0.0:
            return None
        return native(
            self.kernel,
            snapshot,
            candidates,
            HARD_SAFETY_HORIZON,
            horizon,
            collision_margin=0.35,
            budget_ms=budget_ms,
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
        self.effort.begin_decision()
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
        hard, age_zero, hard_held = self._hard_authority(snapshot)
        if not hard:
            return Decision(
                None,
                (),
                0.0,
                HARD_SAFETY_HORIZON,
                "hard-safe-set-empty",
                HARD_SAFETY_HORIZON,
                repairable_count=len(age_zero),
            )

        extended_delivery = (
            getattr(
                type(self.kernel),
                "certify_selected_extended_delivery",
                None,
            )
            if self.kernel is not None
            else None
        )
        if extended_delivery is not None:
            extended = extended_delivery(
                self.kernel,
                snapshot,
                HARD_SAFETY_HORIZON,
                tuple(candidate.action for candidate in hard),
                collision_margin=0.35,
            )
            if len(extended) < len(hard):
                # Some otherwise-Hard action cannot tolerate publication one
                # frame later.  Keep the exact Hard set unchanged, but reserve
                # enough wall time to publish from this snapshot rather than
                # discovering after soft work that its winner lacks delay-4
                # authority.
                self.effort.require_same_frame_publication()

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
        policy_scores = None
        policy_guidance = None
        delivery_viable: frozenset[Action] = frozenset()
        delivery_preferred: frozenset[Action] = frozenset()
        segment_delivery_viable: frozenset[Action] = frozenset()
        segment_delivery_exhausted = False
        terminal_completed = False
        target_guided = False
        target_invalid = False
        policy_probe_ready = False
        pending_candidate = None
        acquisition_horizon = HARD_SAFETY_HORIZON
        progressive_pending_guidance = None
        planning_candidates = hard
        full_publication_budget = (
            self.effort.full_publication_budget_available()
        )

        if len(hard) > 1:
            # This is the ordinary first continuation rung, not a predicted
            # scene depth.  With the full publication budget, publish the
            # cheap complete delivery-viability predicate first and leave the
            # measured residual to h12/h16.  A latency-constrained decision
            # instead spends its smaller residual on complete p8 robustness;
            # starting a fresh projection there can discard both rankings.
            # Kernels without the Boolean primitive retain the same complete
            # p8 fallback.  This changes compute effort only; every published
            # action remains in Hard and delivery-viable.
            elapsed_ms = (self.clock() - started) * 1000.0
            remaining_ms = (
                self.effort.budget_ms()
                - elapsed_ms
                - POLICY_DEADLINE_GUARD_MS
            )
            replanning_started = self.clock()
            replanning_result = (
                self._budgeted_replanning_viability(
                    snapshot,
                    hard,
                    remaining_ms,
                )
                if full_publication_budget
                else self._budgeted_replanning_scores(
                    snapshot,
                    hard,
                    remaining_ms,
                )
            )
            replanning_ms = (
                self.clock() - replanning_started
            ) * 1000.0
            if replanning_result is not None:
                replanning, _robustness_complete = replanning_result
                self.effort.observe_policy(
                    snapshot,
                    len(hard),
                    BASE_POLICY_HORIZON,
                    replanning_ms,
                )
                replanning_best = max(
                    replanning.values(),
                    default=0,
                )
                if replanning_best > 0:
                    delivery_viable = frozenset(
                        action for action, score
                        in replanning.items()
                        if score > 0
                    )
                    delivery_preferred = frozenset(
                        action for action, score
                        in replanning.items()
                        if score == replanning_best
                    )
                    planning_candidates = tuple(
                        candidate for candidate in hard
                        if candidate.action in delivery_viable
                    )
                    policy_preferred = delivery_preferred
                    policy_horizon = BASE_POLICY_HORIZON
                    policy_scores = replanning
                    terminal_completed = True

        elapsed_ms = (self.clock() - started) * 1000.0
        constrained_next_rung_affordable = False
        if (
            not full_publication_budget
            and policy_horizon >= BASE_POLICY_HORIZON
            and len(planning_candidates) > 1
        ):
            next_horizon = next(
                (
                    horizon for horizon in TURN_CAPABLE_POLICY_HORIZONS
                    if horizon > policy_horizon
                ),
                None,
            )
            constrained_next_rung_affordable = (
                next_horizon is not None
                and self.effort.continuation_extension_affordable(
                    snapshot,
                    len(planning_candidates),
                    policy_horizon,
                    next_horizon,
                    elapsed_ms,
                )
            )
        if (
            (
                full_publication_budget
                or constrained_next_rung_affordable
            )
            and (
                limit > max(HARD_SAFETY_HORIZON, policy_horizon)
                # A completed p8 result is safe to retain while one ordinary
                # h12 probe measures a previously unseen cost.  Otherwise an
                # extrapolated p8 estimate can suppress that rung forever.
                or policy_horizon >= BASE_POLICY_HORIZON
            )
            and len(planning_candidates) > 1
            and self.effort.budget_ms() - elapsed_ms
                > TERMINAL_DEADLINE_GUARD_MS
        ):
            nominal_minimum_horizon = next(
                (
                    horizon for horizon in TURN_CAPABLE_POLICY_HORIZONS
                    if horizon > policy_horizon
                ),
                BASE_POLICY_HORIZON,
            )
            terminal_progressive_native = (
                getattr(
                    type(self.kernel),
                    "segment_terminal_counts_progressive",
                    None,
                )
                if self.kernel is not None
                else None
            )
            progressive_terminal_ready = bool(
                terminal_progressive_native is not None
                and len(planning_candidates) > 1
            )
            # Prepare only the next ordinary turn-capable rung.  Building the
            # whole predicted h16 projection up front can consume a shortened
            # publication deadline before h12 gets any terminal-search time.
            # Once h12 completes, the measured residual promotion below may
            # extend the same cached projection to h16.  Every rung therefore
            # remains complete-or-discard instead of hiding an intermediate
            # result behind a deeper candidate-independent build.
            soft_prepare_horizon = (
                nominal_minimum_horizon
                if progressive_terminal_ready
                else limit
            )
            operation_started = self.clock()
            self._prepare_soft(snapshot, soft_prepare_horizon)
            soft_prepare_ms = (
                self.clock() - operation_started
            ) * 1000.0
            soft_prepare_step_ms = soft_prepare_ms
            soft_prepare_step_span = max(
                1,
                soft_prepare_horizon - BASE_POLICY_HORIZON,
            )
            soft_prepare_step_growth = 1.0
            rollout_ms += soft_prepare_ms
            self.effort.observe_projection(
                snapshot,
                soft_prepare_horizon,
                soft_prepare_ms,
            )
            observed_held = action_from_input(snapshot.input_mask)
            pending_candidate = next(
                (
                    candidate
                    for candidate in planning_candidates
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
            if pending_candidate is None:
                self.pending_target_action = None

            terminal_native = (
                getattr(
                    type(self.kernel),
                    "terminal_counts_budgeted",
                    None,
                )
                if self.kernel is not None
                else None
            )
            if progressive_terminal_ready:
                allowed = frozenset(
                    candidate.action for candidate in planning_candidates
                )
                def accept_progressive(
                    minimum_horizon: int,
                    maximum_horizon: int,
                    guidance_action: Action | None = None,
                ) -> bool:
                    nonlocal policy_preferred
                    nonlocal policy_horizon
                    nonlocal policy_scores
                    nonlocal policy_guidance
                    nonlocal terminal_completed
                    nonlocal progressive_pending_guidance
                    nonlocal planning_candidates
                    nonlocal segment_delivery_viable
                    nonlocal segment_delivery_exhausted
                    elapsed_ms = (self.clock() - started) * 1000.0
                    remaining_ms = (
                        self.effort.budget_ms()
                        - elapsed_ms
                        - TERMINAL_DEADLINE_GUARD_MS
                    )
                    if remaining_ms <= 0.0:
                        return False
                    robust_native = (
                        getattr(
                            type(self.kernel),
                            "delivery_segment_viability_progressive",
                            None,
                        )
                        if self.kernel is not None
                        else None
                    )
                    # Make the next local rung exact under repeated physical
                    # pickup.  Deeper terminal rungs are the coarser global
                    # rank and may refine only inside this robust gate; they
                    # do not repay the same exponential universal branch tax
                    # at every extension.
                    if (
                        robust_native is not None
                        and not segment_delivery_viable
                    ):
                        robust_result = (
                            self._budgeted_delivery_segment_viability(
                                snapshot,
                                planning_candidates,
                                maximum_horizon,
                                remaining_ms,
                            )
                        )
                        if robust_result is None:
                            return False
                        robust_horizon = robust_result[0]
                        robust_scores = robust_result[1]
                        robust_viable = frozenset(
                            action for action, score
                            in robust_scores.items()
                            if score > 0
                        )
                        if robust_horizon < maximum_horizon:
                            return False
                        if not robust_viable:
                            # Repeated-pickup viability is monotone: once a
                            # complete rung has no winning first action, no
                            # deeper invocation of this same Boolean model can
                            # resurrect one.  Keep cheaper constant witnesses
                            # available for immediate ranking, but do not burn
                            # the publication window rebuilding an impossible
                            # deeper repeated-pickup search.
                            segment_delivery_exhausted = True
                            return False
                        planning_candidates = tuple(
                            candidate for candidate in planning_candidates
                            if candidate.action in robust_viable
                        )
                        segment_delivery_viable = robust_viable
                        retained_prior = (
                            policy_preferred & robust_viable
                        )
                        policy_preferred = (
                            retained_prior or robust_viable
                        )
                        policy_horizon = robust_horizon
                        if not retained_prior:
                            policy_scores = robust_scores
                        policy_guidance = None
                        terminal_completed = True
                        if len(planning_candidates) <= 1:
                            return True
                        elapsed_ms = (
                            self.clock() - started
                        ) * 1000.0
                        remaining_ms = (
                            self.effort.budget_ms()
                            - elapsed_ms
                            - TERMINAL_DEADLINE_GUARD_MS
                        )
                        if remaining_ms <= 0.0:
                            return True
                    terminal_started = self.clock()
                    progressive_terminal = (
                        self._budgeted_progressive_terminal_counts(
                            snapshot,
                            planning_candidates,
                            minimum_horizon,
                            maximum_horizon,
                            remaining_ms,
                            (
                                guidance_action
                                if any(
                                    candidate.action == guidance_action
                                    for candidate in planning_candidates
                                )
                                else None
                            ),
                        )
                    )
                    terminal_ms = (
                        self.clock() - terminal_started
                    ) * 1000.0
                    if progressive_terminal is None:
                        self.effort.observe_policy_timeout(
                            snapshot,
                            maximum_horizon,
                        )
                        return False
                    completed_horizon = progressive_terminal[0]
                    terminal_scores = progressive_terminal[1]
                    optional_guidance = (
                        progressive_terminal[3]
                        if len(progressive_terminal) > 3
                        else None
                    )
                    if (
                        optional_guidance is not None
                        and guidance_action is not None
                    ):
                        progressive_pending_guidance = (
                            guidance_action,
                            completed_horizon,
                            optional_guidance,
                        )
                    self.effort.observe_policy(
                        snapshot,
                        len(hard),
                        completed_horizon,
                        terminal_ms,
                    )
                    best_terminal_count = max(
                        (
                            score for action, score
                            in terminal_scores.items()
                            if action in allowed
                        ),
                        default=0,
                    )
                    if best_terminal_count > 0:
                        policy_preferred = frozenset(
                            action for action, score
                            in terminal_scores.items()
                            if (
                                action in allowed
                                and score == best_terminal_count
                            )
                        )
                        policy_horizon = completed_horizon
                        policy_scores = terminal_scores
                        policy_guidance = None
                        terminal_completed = True
                    return True

                initial_completed = accept_progressive(
                    nominal_minimum_horizon,
                    soft_prepare_horizon,
                    (
                        pending_candidate.action
                        if pending_candidate is not None
                        else None
                    ),
                )
                if (
                    initial_completed
                    and full_publication_budget
                    and soft_prepare_horizon
                        < TURN_CAPABLE_POLICY_HORIZONS[-1]
                ):
                    # A deliberately shallow predicted limit may still leave
                    # measured residual time.  Preserve that falsifiable
                    # promotion path: extend once from the completed rung,
                    # while the earlier result remains publishable if either
                    # preparation or the deeper exact call consumes the rest.
                    elapsed_ms = (self.clock() - started) * 1000.0
                    remaining_ms = (
                        self.effort.budget_ms()
                        - elapsed_ms
                        - TERMINAL_DEADLINE_GUARD_MS
                    )
                    deepest_affordable = max(
                        (
                            horizon for horizon
                            in TURN_CAPABLE_POLICY_HORIZONS
                            if (
                                horizon > soft_prepare_horizon
                                and soft_prepare_ms
                                    * horizon
                                    / soft_prepare_horizon
                                    <= remaining_ms
                                        * PROMOTION_BUDGET_FRACTION
                            )
                        ),
                        default=None,
                    )
                    if deepest_affordable is not None:
                        previous_horizon = soft_prepare_horizon
                        operation_started = self.clock()
                        self._prepare_soft(snapshot, deepest_affordable)
                        deep_prepare_ms = (
                            self.clock() - operation_started
                        ) * 1000.0
                        rollout_ms += deep_prepare_ms
                        # The initial preparation can be an almost-free cache
                        # hit at h8 while this promotion performs the real ECL
                        # and hazard extension to h16.  Keep an equivalent
                        # full-window cost floor from that measured marginal
                        # work; otherwise the optional coarse rung can
                        # extrapolate a cached h8 sample to h48 and consume the
                        # publication deadline after a stronger local result
                        # has already completed.
                        promoted_span = (
                            deepest_affordable - previous_horizon
                        )
                        if promoted_span > 0:
                            soft_prepare_step_ms = deep_prepare_ms
                            soft_prepare_step_span = promoted_span
                            soft_prepare_step_growth = 1.0
                            soft_prepare_ms = max(
                                soft_prepare_ms
                                    * deepest_affordable
                                    / max(1, previous_horizon),
                                deep_prepare_ms
                                    * deepest_affordable
                                    / promoted_span,
                            )
                        self.effort.observe_projection_extension(
                            snapshot,
                            previous_horizon,
                            deepest_affordable,
                            deep_prepare_ms,
                        )
                        soft_prepare_horizon = deepest_affordable
                        next_horizon = min(
                            horizon for horizon
                            in TURN_CAPABLE_POLICY_HORIZONS
                            if horizon > previous_horizon
                        )
                        accept_progressive(
                            next_horizon,
                            deepest_affordable,
                            (
                                pending_candidate.action
                                if pending_candidate is not None
                                else None
                            ),
                        )
            elif (
                terminal_native is not None
                and len(planning_candidates) > 1
            ):
                # Non-native test doubles and older kernels retain the same
                # complete-or-discard contract. Production uses the shared
                # progressive frontier above so h8/h12 are not recomputed
                # before attempting h16.
                allowed = frozenset(
                    candidate.action for candidate in planning_candidates
                )
                for terminal_horizon in TURN_CAPABLE_POLICY_HORIZONS:
                    if terminal_horizon > limit:
                        break
                    if terminal_horizon <= policy_horizon:
                        continue
                    elapsed_ms = (self.clock() - started) * 1000.0
                    remaining_ms = (
                        self.effort.budget_ms()
                        - elapsed_ms
                        - POLICY_DEADLINE_GUARD_MS
                    )
                    if remaining_ms <= 0.0:
                        break
                    terminal_scores = self._budgeted_terminal_counts(
                        snapshot,
                        planning_candidates,
                        terminal_horizon,
                        remaining_ms,
                    )
                    if terminal_scores is None:
                        break
                    best_terminal_count = max(
                        (
                            score for action, score
                            in terminal_scores.items()
                            if action in allowed
                        ),
                        default=0,
                    )
                    if best_terminal_count <= 0:
                        break
                    policy_preferred = frozenset(
                        action for action, score
                        in terminal_scores.items()
                        if (
                            action in allowed
                            and score == best_terminal_count
                        )
                    )
                    policy_horizon = terminal_horizon
                    policy_scores = terminal_scores
                    policy_guidance = None
                    terminal_completed = True

            # The shared turn-capable frontier receives the first soft
            # deadline: rebuilding constant h6/h8/h12 prefixes before it can
            # hide an affordable h16 divergence. Spend only the residual on
            # exact constant witnesses. They remain useful as deeper lower
            # bounds and may restrict only weaker/shallow proposal evidence.
            for horizon in EFFORT_HORIZONS:
                if (
                    horizon > limit
                    or horizon > TURN_CAPABLE_POLICY_HORIZONS[-1]
                    or constant_exhausted
                ):
                    break
                if (
                    policy_preferred
                    and horizon <= policy_horizon
                ):
                    # The delivery-aware local policy already covers both
                    # h6 and h8. Rebuilding an unchanged-input prefix cannot
                    # strengthen it and only consumes publication time.
                    continue
                elapsed_ms = (self.clock() - started) * 1000.0
                remaining_ms = (
                    self.effort.budget_ms()
                    - elapsed_ms
                    - TERMINAL_DEADLINE_GUARD_MS
                )
                if remaining_ms <= 0.0:
                    break
                operation_started = self.clock()
                next_frontier = self._budgeted_certify_selected(
                    snapshot,
                    horizon,
                    tuple(candidate.action for candidate in frontier),
                    remaining_ms,
                )
                rollout_ms += (
                    self.clock() - operation_started
                ) * 1000.0
                if next_frontier is None:
                    break
                rollout_horizon = horizon
                if len(next_frontier) < len(frontier):
                    contracted = True
                if next_frontier:
                    frontier = next_frontier
                    frontier_horizon = horizon
                else:
                    constant_exhausted = True
            if (
                frontier_horizon > HARD_SAFETY_HORIZON
                and not policy_preferred
            ):
                policy_preferred = frozenset(
                    candidate.action for candidate in frontier
                )
                policy_horizon = frontier_horizon
            if terminal_completed and policy_preferred:
                # The terminal rung is already a turn-capable proposal.
                # Prevent the legacy interleaved fallback below from
                # rebuilding the same h6/h8 constant prefixes after it.
                policy_probe_ready = True

            # A short exact terminal DP can remain indifferent until a known
            # future event enters its endpoint window.  Spend only measured
            # residual projection budget on one coarse, longer two-segment
            # comparator.  The long constant scan contributes witnesses, not
            # authority: the comparator rechecks their union with the local
            # winners and permits every focused/unfocused tail.  Timeout at
            # either step preserves the completed local result in full.
            macro_tail_native = (
                getattr(
                    type(self.kernel),
                    "macro_tail_scores_budgeted",
                    None,
                )
                if self.kernel is not None
                else None
            )
            if (
                macro_tail_native is not None
                and terminal_completed
                and policy_horizon >= TURN_CAPABLE_POLICY_HORIZONS[-1]
                and policy_preferred
                and len(hard) > 1
            ):
                coarse_horizon = None
                # Projection is cached, so each call below extends only the
                # newly requested frames.  Admit those extensions one rung at
                # a time from the latest measured marginal rate.  A linear
                # h16 -> h48 jump hid source-driven growth in future hazards
                # and could consume the publication deadline after the exact
                # local result was already complete.
                for horizon in COARSE_GLOBAL_HORIZONS:
                    if horizon <= soft_prepare_horizon:
                        continue
                    elapsed_ms = (self.clock() - started) * 1000.0
                    remaining_ms = (
                        self.effort.budget_ms()
                        - elapsed_ms
                        - 2.0 * POLICY_DEADLINE_GUARD_MS
                    )
                    extension_span = horizon - soft_prepare_horizon
                    # The first transition from the local window has no
                    # coarse-scale sample yet.  Reserve at the equivalent
                    # full-window rate; after one contiguous coarse rung is
                    # measured, its marginal rate and latest observed growth
                    # predict the next rung.
                    extension_estimate_ms = (
                        soft_prepare_step_ms
                        * (
                            horizon
                            if coarse_horizon is None
                            else extension_span
                        )
                        / max(1, soft_prepare_step_span)
                        * soft_prepare_step_growth
                    )
                    if (
                        remaining_ms <= 0.0
                        or extension_estimate_ms
                            > remaining_ms * PROMOTION_BUDGET_FRACTION
                    ):
                        break
                    previous_horizon = soft_prepare_horizon
                    operation_started = self.clock()
                    self._prepare_soft(snapshot, horizon)
                    extension_ms = (
                        self.clock() - operation_started
                    ) * 1000.0
                    rollout_ms += extension_ms
                    previous_step_rate = (
                        soft_prepare_step_ms
                        / max(1, soft_prepare_step_span)
                    )
                    current_step_rate = extension_ms / extension_span
                    soft_prepare_step_growth = max(
                        1.0,
                        (
                            current_step_rate / previous_step_rate
                            if previous_step_rate > 0.0
                            else 1.0
                        ),
                    )
                    soft_prepare_step_ms = extension_ms
                    soft_prepare_step_span = extension_span
                    soft_prepare_horizon = horizon
                    coarse_horizon = horizon
                    self.effort.observe_projection_extension(
                        snapshot,
                        previous_horizon,
                        horizon,
                        extension_ms,
                    )
                if coarse_horizon is not None:
                    elapsed_ms = (self.clock() - started) * 1000.0
                    remaining_ms = (
                        self.effort.budget_ms()
                        - elapsed_ms
                        - TERMINAL_DEADLINE_GUARD_MS
                    )
                    coarse_frontier = (
                        self._budgeted_certify_selected(
                            snapshot,
                            coarse_horizon,
                            tuple(candidate.action for candidate in hard),
                            remaining_ms,
                        )
                        if remaining_ms > 0.0
                        else None
                    )
                    coarse_actions = frozenset(
                        candidate.action
                        for candidate in (coarse_frontier or ())
                    )
                    if coarse_actions - policy_preferred:
                        shortlist_actions = (
                            policy_preferred | coarse_actions
                        )
                        shortlist = tuple(
                            candidate for candidate in hard
                            if candidate.action in shortlist_actions
                        )
                        elapsed_ms = (
                            self.clock() - started
                        ) * 1000.0
                        remaining_ms = (
                            self.effort.budget_ms()
                            - elapsed_ms
                            - POLICY_DEADLINE_GUARD_MS
                        )
                        macro_scores = self._budgeted_macro_tail_scores(
                            snapshot,
                            shortlist,
                            coarse_horizon,
                            remaining_ms,
                        )
                        macro_best = max(
                            (macro_scores or {}).values(),
                            default=0,
                        )
                        if macro_best > 0:
                            policy_preferred = frozenset(
                                action for action, score
                                in macro_scores.items()
                                if score == macro_best
                            )
                            policy_horizon = coarse_horizon
                            policy_scores = macro_scores
                            policy_guidance = None

            budgeted_policy = (
                getattr(
                    type(self.kernel),
                    "nominal_policy_counts_budgeted",
                    None,
                )
                if self.kernel is not None
                else None
            )
            progressive_reachability = (
                getattr(
                    type(self.kernel),
                    "boolean_reachability_progressive",
                    None,
                )
                if self.kernel is not None
                else None
            )
            if (
                progressive_reachability is not None
                and len(hard) > 1
                # Once the precise local repeated-pickup gate completed, the
                # deeper nominal terminal ladder is the coarse global rank.
                # Do not repay the universal delivery branch tax through the
                # legacy residual Boolean path in the same decision.
                and not segment_delivery_viable
                and not segment_delivery_exhausted
                and limit >= BASE_POLICY_HORIZON
                and (
                    not terminal_completed
                    or limit > policy_horizon
                )
            ):
                allowed = frozenset(
                    candidate.action for candidate in hard
                )
                elapsed_ms = (self.clock() - started) * 1000.0
                reachability_budget_ms = (
                    self.effort.budget_ms()
                    - elapsed_ms
                    - 2.0 * POLICY_DEADLINE_GUARD_MS
                )
                policy_exhausted = True
                if reachability_budget_ms > 0.0:
                    policy_started = self.clock()
                    progressive = (
                        self._budgeted_progressive_reachability(
                            snapshot,
                            hard,
                            limit,
                            reachability_budget_ms,
                        )
                    )
                    policy_ms = (
                        self.clock() - policy_started
                    ) * 1000.0
                    if progressive is not None:
                        (
                            completed_horizon,
                            flexible_scores,
                            _reached_maximum,
                        ) = progressive
                        self.effort.observe_target(
                            "survival",
                            snapshot,
                            len(hard),
                            completed_horizon,
                            policy_ms,
                        )
                        # Membership is an exact exists-controller result for
                        # every physical delivery branch.  A deeper completed
                        # Boolean rung may restrict a shallower terminal-state
                        # ranking, but never promotes an action outside its
                        # winning set.
                        if (
                            completed_horizon >= policy_horizon
                            and any(
                                score > 0
                                for action, score
                                in flexible_scores.items()
                                if action in allowed
                            )
                        ):
                            winning_actions = frozenset(
                                action for action, score
                                in flexible_scores.items()
                                if (
                                    score > 0
                                    and action in allowed
                                )
                            )
                            retained_terminal = (
                                policy_preferred & winning_actions
                                if terminal_completed
                                else frozenset()
                            )
                            policy_preferred = (
                                retained_terminal or winning_actions
                            )
                            policy_horizon = completed_horizon
                            if not retained_terminal:
                                policy_scores = flexible_scores
                            policy_guidance = None
                policy_probe_ready = bool(policy_preferred)

                if (
                    self.guidance_target is not None
                    and policy_probe_ready
                    and policy_horizon >= frontier_horizon
                    and not target_guided
                ):
                    # Survival continuation gets the budget first.  A tracked
                    # soft target may then break only a same-horizon survival
                    # tie; a shallower target calculation cannot starve or
                    # enlarge that preferred set.
                    refinement_actions = frozenset(policy_preferred)
                    refinement_candidates = tuple(
                        candidate for candidate in hard
                        if candidate.action in refinement_actions
                    )
                    elapsed_ms = (
                        self.clock() - started
                    ) * 1000.0
                    if (
                        len(refinement_candidates) > 1
                        and self.effort.target_affordable(
                            "track",
                            snapshot,
                            len(refinement_candidates),
                            policy_horizon,
                            elapsed_ms,
                        )
                    ):
                        guidance_started = self.clock()
                        guidance_budget_ms = (
                            self.effort.budget_ms()
                            - elapsed_ms
                            - POLICY_DEADLINE_GUARD_MS
                        )
                        guidance = self._terminal_guidance(
                            snapshot,
                            refinement_candidates,
                            policy_horizon,
                            self.guidance_target,
                            guidance_budget_ms,
                        )
                        guidance_ms = (
                            self.clock() - guidance_started
                        ) * 1000.0
                        if guidance is not None:
                            self.effort.observe_target(
                                "track",
                                snapshot,
                                len(refinement_candidates),
                                policy_horizon,
                                guidance_ms,
                            )
                            target_preferred = preferred_target_actions(
                                guidance,
                                refinement_actions,
                            )
                            if target_preferred:
                                policy_preferred = target_preferred
                                policy_guidance = guidance
                                policy_scores = None
                                target_guided = True

            for horizon in (
                ()
                if policy_probe_ready
                else EFFORT_HORIZONS
            ):
                if horizon > limit:
                    break
                elapsed_ms = (self.clock() - started) * 1000.0
                remaining_ms = (
                    self.effort.budget_ms()
                    - elapsed_ms
                    - TERMINAL_DEADLINE_GUARD_MS
                )
                if remaining_ms <= 0.0:
                    break
                if not constant_exhausted:
                    operation_started = self.clock()
                    next_frontier = self._budgeted_certify_selected(
                        snapshot,
                        horizon,
                        tuple(candidate.action for candidate in frontier),
                        remaining_ms,
                    )
                    rollout_ms += (
                        self.clock() - operation_started
                    ) * 1000.0
                    if next_frontier is None:
                        break
                    rollout_horizon = horizon
                    if len(next_frontier) < len(frontier):
                        contracted = True
                    if next_frontier:
                        frontier = next_frontier
                        frontier_horizon = horizon
                    else:
                        constant_exhausted = True

                if (
                    horizon not in TURN_CAPABLE_POLICY_HORIZONS
                    or
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
                    # A soft target must not shorten the ordinary survival
                    # lookahead as its commitment deadline approaches.  The
                    # deadline only expires the target; every affordable rung
                    # still evaluates a fresh full-horizon continuation.
                    effective_horizon = horizon
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
                guidance = None
                scores = None
                if not affordable:
                    # A stale cost estimate must not suppress the first
                    # turn-capable continuation indefinitely.  The constant
                    # frontier above is already available, so spend only the
                    # residual deadline on a complete-or-discard p8 probe.
                    remaining_ms = (
                        self.effort.budget_ms()
                        - elapsed_ms
                        - POLICY_DEADLINE_GUARD_MS
                    )
                    if (
                        horizon != BASE_POLICY_HORIZON
                        or budgeted_policy is None
                        or remaining_ms <= 0.0
                    ):
                        policy_exhausted = True
                        continue
                    policy_started = self.clock()
                    scores = self._budgeted_policy_scores(
                        snapshot,
                        hard,
                        horizon,
                        remaining_ms,
                    )
                    policy_ms = (
                        self.clock() - policy_started
                    ) * 1000.0
                    if scores is None:
                        self.effort.observe_policy_timeout(
                            snapshot,
                            horizon,
                        )
                        policy_exhausted = True
                        continue
                    self.effort.observe_policy(
                        snapshot,
                        len(hard),
                        horizon,
                        policy_ms,
                    )
                else:
                    policy_started = self.clock()
                    if self.guidance_target is not None:
                        guidance_budget_ms = (
                            self.effort.budget_ms()
                            - elapsed_ms
                            - POLICY_DEADLINE_GUARD_MS
                        )
                        guidance = self._terminal_guidance(
                            snapshot,
                            hard,
                            effective_horizon,
                            self.guidance_target,
                            guidance_budget_ms,
                        )
                    else:
                        scores = self._policy_scores(
                            snapshot,
                            hard,
                            horizon,
                        )
                    policy_ms = (
                        self.clock() - policy_started
                    ) * 1000.0
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
                    target_preferred = preferred_target_actions(
                        guidance, allowed
                    )
                    if target_preferred:
                        policy_preferred = target_preferred
                        policy_horizon = effective_horizon
                        policy_guidance = guidance
                        policy_scores = None
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
                    policy_scores = scores
                    policy_guidance = None

            if (
                self.guidance_target is not None
                and policy_guidance is not None
                and policy_horizon < frontier_horizon
                and len(frontier) > 1
                and budgeted_policy is not None
                and any(
                    policy_horizon < horizon <= frontier_horizon
                    for horizon in TURN_CAPABLE_POLICY_HORIZONS
                )
            ):
                # A shallow target may identify a useful basin, but it must
                # not settle an ambiguity left by materially deeper fresh
                # survival evidence when the remaining deadline can extend
                # that small frontier by one ordinary turn-capable rung.  The
                # timed native probe is complete-or-discard, so a timeout
                # preserves the prior evidence without publishing a partial
                # ranking.
                probe_horizon = next(
                    horizon for horizon in TURN_CAPABLE_POLICY_HORIZONS
                    if policy_horizon < horizon <= frontier_horizon
                )
                elapsed_ms = (self.clock() - started) * 1000.0
                remaining_ms = (
                    self.effort.budget_ms()
                    - elapsed_ms
                    - POLICY_DEADLINE_GUARD_MS
                )
                available_probe_ms = (
                    remaining_ms - POLICY_DEADLINE_GUARD_MS
                )
                probe_budget_ms = self.effort.policy_probe_budget_ms(
                    snapshot,
                    len(frontier),
                    probe_horizon,
                    available_probe_ms,
                )
                deep_scores = None
                if probe_budget_ms > 0.0:
                    policy_started = self.clock()
                    deep_scores = self._budgeted_policy_scores(
                        snapshot,
                        frontier,
                        probe_horizon,
                        probe_budget_ms,
                    )
                    policy_ms = (
                        self.clock() - policy_started
                    ) * 1000.0
                    if deep_scores is not None:
                        self.effort.observe_policy(
                            snapshot,
                            len(frontier),
                            probe_horizon,
                            policy_ms,
                        )
                    else:
                        self.effort.observe_policy_timeout(
                            snapshot,
                            probe_horizon,
                        )
                allowed = frozenset(
                    candidate.action for candidate in frontier
                )
                deep_best = max(
                    (
                        score for action, score in (
                            deep_scores or {}
                        ).items()
                        if action in allowed
                    ),
                    default=0,
                )
                if deep_best > 0:
                    policy_preferred = frozenset(
                        action for action, score in deep_scores.items()
                        if action in allowed and score == deep_best
                    )
                    policy_horizon = probe_horizon
                    policy_scores = deep_scores
                    policy_guidance = None

            policy_probe_ready = bool(policy_preferred)

            if (
                self.guidance_target is not None
                and target_invalid
            ):
                self._clear_target()

            if policy_probe_ready:
                # Attribute projection cost to the horizon actually built.
                # Charging an h16 shared forecast as h8 would poison the
                # generic work-rate estimate and keep later rungs closed.
                rollout_horizon = soft_prepare_horizon
            self.effort.observe_rollout(
                snapshot,
                len(hard),
                rollout_horizon,
                rollout_ms,
            )

        frontier_preferred = (
            frozenset(candidate.action for candidate in frontier)
            if frontier_horizon > HARD_SAFETY_HORIZON
            else frozenset()
        )
        # Deeper constant witnesses remain tie-breakers; they cannot reject a
        # turn-capable policy merely because holding its first input is worse.
        restricted_preferred: frozenset[Action] = frozenset()
        if (
            policy_preferred
            and policy_horizon < frontier_horizon
            and frontier_preferred
        ):
            if policy_guidance is not None:
                restricted_preferred = preferred_target_actions(
                    policy_guidance,
                    frontier_preferred,
                )
            elif policy_scores is not None:
                restricted_preferred = (
                    policy_preferred & frontier_preferred
                )
        if policy_preferred and policy_scores is not None:
            preferred = restricted_preferred or policy_preferred
        else:
            preferred = (
                policy_preferred
                if policy_preferred and policy_horizon >= frontier_horizon
                else restricted_preferred
                or frontier_preferred
                or policy_preferred
            )
        if segment_delivery_viable:
            # This is exact receding-horizon survival evidence under the same
            # pickup/transition timeline as publication.  Nominal endpoint,
            # coarse, target, and attack ranks may break ties inside it, but
            # cannot restore an action whose later correction was proved too
            # late across a complete delivery-segment rung.
            retained = preferred & segment_delivery_viable
            preferred = retained or segment_delivery_viable
        if delivery_viable:
            # Zero means no safe next correction across every modeled
            # delivery branch, so a later nominal proposal cannot restore it.
            # Positive endpoint multiplicity is only a local robustness rank:
            # a deeper completed continuation may reorder viable actions.
            retained = preferred & delivery_viable
            if retained:
                preferred = retained
            else:
                delivery_ranked: frozenset[Action] = frozenset()
                if policy_scores is not None:
                    delivery_best = max(
                        (
                            policy_scores.get(action, 0)
                            for action in delivery_viable
                        ),
                        default=0,
                    )
                    if delivery_best > 0:
                        delivery_ranked = frozenset(
                            action for action in delivery_viable
                            if policy_scores.get(action, 0) == delivery_best
                        )
                elif policy_guidance is not None:
                    delivery_ranked = preferred_target_actions(
                        policy_guidance,
                        delivery_viable,
                    )
                preferred = delivery_ranked or delivery_preferred

        if pending_candidate is not None:
            # A free-space target is soft state derived from a previously
            # selected action.  Acquire it only after this snapshot's ordinary
            # survival work and only if that action remains in the final fresh
            # survival-preferred set.  Target work can consume residual effort
            # but cannot shorten or replace the survival continuation.
            pending_still_preferred = pending_candidate.action in preferred
            elapsed_ms = (self.clock() - started) * 1000.0
            acquisition_complete = False
            guidance = None
            if pending_still_preferred and (
                progressive_pending_guidance is not None
                and progressive_pending_guidance[0]
                    == pending_candidate.action
                and progressive_pending_guidance[1]
                    >= acquisition_horizon
            ):
                # This optional endpoint was aggregated only after the native
                # progressive call had published its complete survival rung.
                # Reuse it without charging a second projection.
                guidance = {
                    pending_candidate.action:
                        progressive_pending_guidance[2]
                }
            elif (
                pending_still_preferred
                and self.effort.target_affordable(
                    "acquire",
                    snapshot,
                    1,
                    acquisition_horizon,
                    elapsed_ms,
                )
            ):
                guidance_started = self.clock()
                guidance_budget_ms = (
                    self.effort.budget_ms()
                    - elapsed_ms
                    - POLICY_DEADLINE_GUARD_MS
                )
                guidance = self._terminal_guidance(
                    snapshot,
                    (pending_candidate,),
                    acquisition_horizon,
                    budget_ms=guidance_budget_ms,
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
            if guidance is not None:
                acquisition_complete = True
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
            if not pending_still_preferred or acquisition_complete:
                self.pending_target_action = None

        if (
            self.guidance_target is not None
            and not target_guided
            and len(preferred) > 1
        ):
            # Exact target tracking is residual work and may legitimately
            # miss its budget.  Within an otherwise exact tie in the strongest
            # fresh continuation evidence, use the already Hard-certified
            # delivery endpoint as a zero-projection local micro step.  This
            # cannot admit a weaker route or alter Hard eligibility.
            target_x, target_y = self.guidance_target
            precise = precision_preferred_actions(preferred)
            target_candidates = tuple(
                candidate for candidate in hard
                if candidate.action in precise
            )
            best_local_distance = min(
                (
                    (candidate.final_x - target_x) ** 2
                    + (candidate.final_y - target_y) ** 2
                )
                for candidate in target_candidates
            )
            preferred = frozenset(
                candidate.action for candidate in target_candidates
                if (
                    (candidate.final_x - target_x) ** 2
                    + (candidate.final_y - target_y) ** 2
                    == best_local_distance
                )
            )

        attack_target = None
        if len(preferred) > 1:
            attack_target = suppression_target(snapshot)
            if attack_target is not None:
                attack_preferred = preferred_suppression_actions(
                    hard,
                    preferred,
                    attack_target,
                )
                if attack_preferred:
                    preferred = attack_preferred

        chosen = self.ranker.choose(
            snapshot,
            hard,
            preferred,
            commitment_frames=HARD_SAFETY_HORIZON,
        )
        held = action_from_input(snapshot.input_mask)
        target_source_horizon = max(
            (
                policy_horizon
                if chosen.action in policy_preferred
                else HARD_SAFETY_HORIZON
            ),
            (
                frontier_horizon
                if any(
                    candidate.action == chosen.action
                    for candidate in frontier
                )
                else HARD_SAFETY_HORIZON
            ),
        )
        preferred_directions = frozenset(
            (action.dx, action.dy) for action in preferred
        )
        if (
            self.guidance_target is None
            and len(preferred_directions) == 1
            and target_source_horizon > HARD_SAFETY_HORIZON
            and chosen.action != held
        ):
            self.pending_target_action = chosen.action
            self.pending_target_horizon = target_source_horizon
        held_horizon = max(
            (
                HARD_CURRENT_HOLD_HORIZON
                if any(candidate.action == held for candidate in hard_held)
                else HARD_SAFETY_HORIZON
            ),
            (
                frontier_horizon
                if any(candidate.action == held for candidate in frontier)
                else HARD_SAFETY_HORIZON
            ),
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
            (
                attack_target.x
                if attack_target is not None
                else None
            ),
            (
                attack_target.deadline
                if attack_target is not None
                else None
            ),
            attack_target.life if attack_target is not None else 0,
            attack_target.source if attack_target is not None else "",
        )

"""Compose adaptive horizon, hard authority, and proposal ranking."""

from __future__ import annotations

import os

from .hazards.lasers import unknown_motion_may_reach_player
from .kernels.safety import NativeSafetyKernel
from .laser_effort import (
    LASER_EFFORT_HORIZON,
    LASER_SPEED_HORIZON,
    isolate_lasers,
    needs_active_mixed_replan,
    needs_normal_speed,
    retained_current_corridor,
)
from .model import (
    ACTIONS,
    FAST_ACTIONS,
    Action,
    Decision,
    PLAYER_ALIVE,
    PLAYER_INVULNERABLE,
    Snapshot,
    action_from_input,
)
from .ranking import (
    ProposalRanker,
    boundary_relief,
    heads_toward_single_wall,
    near_two_walls,
)
from .safety import DELIVERY_DELAYS, certify_actions, nearest_current_clearance
from .viability import replanning_scores


# Physical runs normally bound a hazardous-state decision interval to two
# native frames and input pickup to two more.  Longer 8/12/16-frame rollouts
# allocate ranking effort; they must not turn constant-action rollout into a
# hard eligibility requirement.
HARD_SAFETY_HORIZON = 4


def needs_dense_corner_planning(snapshot: Snapshot) -> bool:
    """Spend a bounded longer soft rollout only in a dense two-wall trap."""
    return (
        350 <= len(snapshot.bullets) < 400
        and not snapshot.lasers
        and len(snapshot.enemies) <= 1
        and near_two_walls(snapshot, 20)
    )


def adaptive_horizon(snapshot: Snapshot) -> int:
    # Long proposal rollouts are useful only if their result can arrive in
    # time.  A physical Stage 3 CE measured a 38.5 ms 16-frame solve at 284
    # bullets, while the same hard authority plus 8-frame effort stayed below
    # one native frame in the saved-snapshot benchmark.  This changes ranking
    # effort only; HARD_SAFETY_HORIZON and its allowed actions are unchanged.
    # Stage 4 f2663 spent 34.6 ms on effort-8 with 461 bullets and four
    # enemies; the resulting four-frame-old proposal was correctly discarded.
    # Hard-4 alone was timely, but a later 623-bullet branch needed h6 to reject
    # a rightward dead end two frames earlier. Keep this bounded compromise;
    # decide() skips the extra effort when all hard actions remain available.
    if len(snapshot.bullets) >= 400:
        return 6
    if needs_dense_corner_planning(snapshot):
        # Stage 5 f3218 still had every Hard-4 action, but the ordinary h8
        # proposal retained five paths in the lower-left corner. Two decisions
        # later it selected down-right even though h12 had only down-left; the
        # hard set emptied at f3229. Build one combined h4/h12 native rollout
        # in this bounded geometry. This changes ranking effort only.
        return 12
    if len(snapshot.bullets) >= 220:
        return 8
    if (
        len(snapshot.bullets) >= 100
        and not snapshot.lasers
        and len(snapshot.enemies) <= 1
        and any(
            boundary_relief(snapshot, action, 20) != 0
            for action in ACTIONS
        )
    ):
        # Stage 4 f16163 entered the ranker's 20-frame bottom warning band,
        # but its ordinary 12-frame proposal still treated a tangent right
        # path as durable.  The source-grounded rollout rejected that path at
        # h17 and selected the surviving down-left corridor at h20.  Align the
        # effort window only in this bounded, non-laser boundary case; the
        # unchanged Hard-4 set remains the sole action authority.  A cold
        # native pair-20 pass on the saved 182-bullet state took about 10 ms
        # median, versus 16--18 ms for the unnecessary h24 extension.
        return 20
    if len(snapshot.bullets) >= 100:
        # Stage 4 f6425 spent 49.5 ms on a 16-frame repair with 119
        # bullets and six lasers, although four constant actions survived 12
        # frames. Keep mixed scenes inside one delivery interval here.
        return 12
    if snapshot.lasers or snapshot.enemies:
        return 16
    nearest = nearest_current_clearance(snapshot)
    if nearest < 48.0:
        return 16
    if nearest < 120.0:
        return 12
    return 8


class Solver:
    def __init__(self, ranker: ProposalRanker | None = None) -> None:
        self.ranker = ranker or ProposalRanker()
        self.kernel = NativeSafetyKernel() if os.name == "nt" else None
        self.backend = "native-c++" if self.kernel is not None else "python-reference"

    def _certify(self, snapshot: Snapshot, horizon: int):
        if self.kernel is not None:
            return self.kernel.certify(snapshot, horizon, collision_margin=0.35)
        return certify_actions(snapshot, horizon)

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

    def _certify_dense_subset(
        self,
        snapshot: Snapshot,
        horizon: int,
        actions: tuple[Action, ...],
    ):
        native_method = (
            getattr(type(self.kernel), "certify_selected", None)
            if self.kernel is not None
            else None
        )
        if native_method is not None:
            return self._certify_selected(snapshot, horizon, actions)
        return self._certify(snapshot, horizon)

    def _certify_selected_pair(
        self,
        snapshot: Snapshot,
        hard_horizon: int,
        effort_horizon: int,
        actions: tuple[Action, ...],
    ):
        native_method = (
            getattr(type(self.kernel), "certify_selected_pair", None)
            if self.kernel is not None
            else None
        )
        if native_method is not None:
            return self.kernel.certify_selected_pair(
                snapshot,
                hard_horizon,
                effort_horizon,
                actions,
                collision_margin=0.35,
            )
        hard = self._certify_selected(snapshot, hard_horizon, actions)
        effort = self._certify_selected(
            snapshot,
            effort_horizon,
            tuple(candidate.action for candidate in hard),
        ) if hard else ()
        return hard, effort

    def _last_viable_frontier(
        self,
        snapshot: Snapshot,
        minimum_horizon: int,
        maximum_horizon: int,
    ):
        if self.kernel is not None and hasattr(self.kernel, "last_viable_frontier"):
            return self.kernel.last_viable_frontier(
                snapshot,
                minimum_horizon,
                maximum_horizon,
                collision_margin=0.35,
            )
        for horizon in range(maximum_horizon, minimum_horizon - 1, -1):
            certified = self._certify(snapshot, horizon)
            if certified:
                return certified
        return ()

    def _longest_selected_horizon(
        self,
        snapshot: Snapshot,
        minimum_horizon: int,
        maximum_horizon: int,
        actions: tuple[Action, ...],
    ) -> int:
        native_method = (
            getattr(type(self.kernel), "longest_selected_horizon", None)
            if self.kernel is not None
            else None
        )
        if native_method is not None:
            return self.kernel.longest_selected_horizon(
                snapshot,
                minimum_horizon,
                maximum_horizon,
                actions,
                collision_margin=0.35,
            )
        if self.kernel is not None:
            return 0
        for horizon in range(maximum_horizon, minimum_horizon - 1, -1):
            if self._certify_selected(snapshot, horizon, actions):
                return horizon
        return 0

    def observe(self, survived: bool) -> None:
        self.ranker.observe(survived)

    def decide(self, snapshot: Snapshot, required_action: Action | None = None) -> Decision:
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
            # The full certificate was issued with the physical command.  On
            # the sole pending frame, recheck both possible next inputs
            # (current or leased) against newly observed hazards without
            # extending a constant-action requirement past acknowledgement.
            certified = (
                self._certify(snapshot, 1)
                if required_action.focused
                else self._certify_selected(snapshot, 1, (required_action,))
            )
            leased = next(
                (candidate for candidate in certified if candidate.action == required_action),
                None,
            )
            if leased is None:
                return Decision(
                    None,
                    certified,
                    0.0,
                    1,
                    "input-lease-unsafe",
                    1,
                )
            return Decision(
                leased.action,
                certified,
                leased.clearance,
                1,
                "ok",
                1,
            )
        effort_horizon = adaptive_horizon(snapshot)
        dense_corner_planning = needs_dense_corner_planning(snapshot)
        age_zero_certified = ()
        discouraged = frozenset()
        precomputed_current_effort = None
        precomputed_current_horizon = 0
        if (
            len(snapshot.bullets) >= 350
            and effort_horizon > HARD_SAFETY_HORIZON
            and not dense_corner_planning
        ):
            # Stage 4 f10061 had all nine Hard-4 actions available, but a
            # redundant h6 pass over 535 bullets took 35.6 ms and aged the
            # otherwise open decision beyond its delivery authority. First
            # establish the unchanged hard set; spend h6 only when that set is
            # already constrained, as it was at the f10137 dead-end branch.
            # f4091 repeated the same timing failure at 392 bullets: Hard-4
            # and h8 both contained all nine actions, while the redundant h8
            # solve reached 45.1 ms. Start this publication path at 350, but
            # below 400 retain h8 unless every hard path still has a full
            # focused Hard-4 segment of clearance. f2760 had nine hard actions
            # but only 2.33 px on its weakest path; h8 correctly rejected the
            # up-right dead end that Hard-4 alone selected.
            if self.kernel is not None:
                combined_method = getattr(
                    type(self.kernel),
                    "certify_delivery_sets_with_selected",
                    None,
                )
                if len(snapshot.bullets) >= 400 and combined_method is not None:
                    current = action_from_input(snapshot.input_mask)
                    # Stage 4 f10171's held up-right path survived h6 but not
                    # h7. Waiting for the ordinary h6 probe to fail left the
                    # corrective up-left decision two frames too late for
                    # publication. Probe only the already-held action one
                    # ranking frame farther; Hard-4 eligibility is unchanged.
                    precomputed_current_horizon = effort_horizon + 1
                    (
                        certified,
                        age_zero_certified,
                        precomputed_current_effort,
                    ) = self.kernel.certify_delivery_sets_with_selected(
                        snapshot,
                        HARD_SAFETY_HORIZON,
                        precomputed_current_horizon,
                        (current,),
                        collision_margin=0.35,
                    )
                else:
                    certified, age_zero_certified = self.kernel.certify_delivery_sets(
                        snapshot,
                        HARD_SAFETY_HORIZON,
                        collision_margin=0.35,
                    )
            else:
                certified = self._certify(snapshot, HARD_SAFETY_HORIZON)
                if not certified:
                    age_zero_certified = certify_actions(
                        snapshot,
                        HARD_SAFETY_HORIZON,
                        DELIVERY_DELAYS[:-1],
                    )
            # Two Stage 4 density CEs (f2625 and f2912) still had eight
            # Hard-4 actions, but the second h6 pass took 18.6/23.5 ms and let
            # the held input reach an empty set. The earlier f10137 dead end
            # needed h6 only after the hard set had narrowed to roughly five
            # actions. Publish broad authority promptly; retain h6 once the
            # geometry is materially constrained. At the other extreme,
            # f10142 had only right/up-right/down-right; Hard-4 already chose
            # the same up-right as h6, while the extra pass took 18.8 ms.
            # Publish immediately once at most three directions remain.
            broad_authority = len(certified) >= len(ACTIONS) - 2
            comfortable_authority = bool(certified) and min(
                candidate.clearance for candidate in certified
            ) > snapshot.focus_speed * HARD_SAFETY_HORIZON + 0.35
            if (
                self.kernel is not None
                and len(snapshot.bullets) >= 400
                and broad_authority
                and not comfortable_authority
            ):
                # Stage 4 f10151 still had eight Hard-4 actions, so the dense
                # fast path correctly avoided a second full pass. Its held
                # up-left action was the sole candidate already absent at h6,
                # however, and continuity carried it into the f10155 empty
                # set. Probe only that held action. This stays a soft ranking
                # signal: the unchanged Hard-4 set remains authoritative, and
                # a discouraged action remains selectable when it is alone.
                current = action_from_input(snapshot.input_mask)
                if any(candidate.action == current for candidate in certified):
                    current_effort = (
                        precomputed_current_effort
                        if precomputed_current_effort is not None
                        else self.kernel.certify_selected(
                            snapshot,
                            effort_horizon,
                            (current,),
                            collision_margin=0.35,
                        )
                    )
                    if not current_effort:
                        discouraged = frozenset((current,))
            narrow_combined_authority = (
                0 < len(certified) <= 3
                and precomputed_current_effort is not None
            )
            broad_expiring_held = (
                broad_authority
                and len(snapshot.bullets) >= 400
                and precomputed_current_effort is not None
                and not precomputed_current_effort
            )
            retained_dense_single_wall_held = (
                broad_authority
                and len(snapshot.bullets) >= 400
                and bool(precomputed_current_effort)
                and not near_two_walls(snapshot, 20)
                and boundary_relief(
                    snapshot,
                    action_from_input(snapshot.input_mask),
                    20,
                ) < 0
            )
            if narrow_combined_authority:
                # Stage 4 f2652 had down/down-left/down-right at Hard-4 but
                # only the first two at h6; f2665 had stay/up/down at Hard-4
                # but only stay/down at h6. Treating every narrow hard action
                # as equally durable selected the short path in both cases
                # and emptied at f2668. The combined dense pass already
                # proves the held action through h7. Reuse it when present;
                # only when the held action is unavailable, certify the three
                # or fewer replacement candidates at h6 using cached hazards.
                effort_certified = (
                    precomputed_current_effort
                    if precomputed_current_effort
                    else self._certify_dense_subset(
                        snapshot,
                        effort_horizon,
                        tuple(candidate.action for candidate in certified),
                    )
                )
            elif (
                len(certified) <= 3
                or broad_expiring_held
                or (
                    broad_authority
                    and not retained_dense_single_wall_held
                    and (
                        comfortable_authority
                        or (
                            len(snapshot.bullets) >= 400
                            and precomputed_current_effort is None
                        )
                    )
                )
            ):
                effort_horizon = HARD_SAFETY_HORIZON
                effort_certified = certified
            elif certified:
                # Dense Stage 4 f2709 already proved the held up-right action
                # safe through h6 in the combined native pass, then spent
                # 57.2 ms rebuilding all 487-bullet h6 branches and expired.
                # Reuse that selective proposal when it survives.  If it does
                # not, the native bridge now reuses the prepared hazards for
                # the full search.  Stage 4 f10251 then rejects a newly chosen
                # up-left path outside its four h6 survivors.  The Hard-4 set
                # above remains unchanged either way. Stage 5 f3064 still had
                # seven hard replacements after the held down-left path failed
                # the combined h7 probe. A second full h6 pass found up-left
                # but took 29 ms, so publication aged two frames and the held
                # path reached an empty set. The broad-expiring-held case above
                # now publishes from Hard-4 immediately; sets of six or fewer
                # retain this longer replacement search. Stage 5 f2569 exposed
                # the converse: held down still passed h7 near the sole bottom
                # wall, but the comfortable broad-set path discarded that
                # evidence and switched to down-right, which became the later
                # dead end at f2583. Retain an already-proved held proposal in
                # that single-wall case; the expiring path still replaces it.
                effort_certified = (
                    precomputed_current_effort
                    if precomputed_current_effort
                    else self._certify_dense_subset(
                        snapshot,
                        effort_horizon,
                        tuple(candidate.action for candidate in certified),
                    )
                )
            else:
                effort_certified = ()
        elif (
            self.kernel is not None
            and hasattr(self.kernel, "certify_pair_with_age_zero")
            and effort_horizon > HARD_SAFETY_HORIZON
        ):
            certified, effort_certified, age_zero_certified = (
                self.kernel.certify_pair_with_age_zero(
                    snapshot,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                    collision_margin=0.35,
                )
            )
        elif (
            self.kernel is not None
            and hasattr(self.kernel, "certify_delivery_sets")
            and effort_horizon == HARD_SAFETY_HORIZON
        ):
            certified, age_zero_certified = self.kernel.certify_delivery_sets(
                snapshot,
                HARD_SAFETY_HORIZON,
                collision_margin=0.35,
            )
            effort_certified = certified
        elif self.kernel is not None and effort_horizon > HARD_SAFETY_HORIZON:
            certified, effort_certified = self.kernel.certify_pair(
                snapshot, HARD_SAFETY_HORIZON, effort_horizon, collision_margin=0.35
            )
        else:
            certified = self._certify(snapshot, HARD_SAFETY_HORIZON)
            effort_certified = (
                self._certify(snapshot, effort_horizon)
                if certified and effort_horizon > HARD_SAFETY_HORIZON
                else certified
            )
        fast_laser_hard = ()
        fast_laser_long = ()
        if effort_horizon >= 16 and needs_normal_speed(snapshot):
            fast_laser_hard, fast_laser_long = self._certify_selected_pair(
                snapshot,
                HARD_SAFETY_HORIZON,
                LASER_SPEED_HORIZON,
                FAST_ACTIONS,
            )
            if fast_laser_hard:
                certified = tuple(certified) + tuple(fast_laser_hard)
        held_action = action_from_input(snapshot.input_mask)
        if (
            not held_action.focused
            and not any(
                candidate.action == held_action for candidate in certified
            )
        ):
            # Stage 4 f12034 crossed the radial threshold that disables the
            # broad fast-laser proposal while up-left-fast was already held.
            # That exact path remained native-safe through h40, but dropping
            # it from the next Hard-4 set discarded its delivery slack and
            # stopped at f12036. Preserve only the physically held action,
            # and only after an independent unchanged hard/effort proof; this
            # does not authorize any other source-normal action.
            held_fast_hard, held_fast_effort = self._certify_selected_pair(
                snapshot,
                HARD_SAFETY_HORIZON,
                effort_horizon,
                (held_action,),
            )
            if held_fast_hard:
                certified = tuple(certified) + tuple(held_fast_hard)
                effort_certified = (
                    tuple(effort_certified) + tuple(held_fast_effort)
                )
        fast_recovery_long = ()
        if not certified:
            # Stage 4 f4773 had no focused Hard-4 action at the lower-left
            # boundary, while source-normal down/down-left/down-right all
            # passed the same delivery and transition authority; two also
            # survived h12. Expand the control state only after the focused
            # action space is empty, and require independent Hard-4 proof.
            fast_recovery_hard, fast_recovery_long = self._certify_selected_pair(
                snapshot,
                HARD_SAFETY_HORIZON,
                effort_horizon,
                FAST_ACTIONS,
            )
            if fast_recovery_hard:
                certified = fast_recovery_hard
                effort_certified = fast_recovery_long
        if not certified:
            if self.kernel is None:
                age_zero_certified = certify_actions(
                    snapshot,
                    HARD_SAFETY_HORIZON,
                    DELIVERY_DELAYS[:-1],
                )
            if age_zero_certified:
                chosen = self.ranker.choose(snapshot, age_zero_certified)
                return Decision(
                    chosen.action,
                    age_zero_certified,
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
                effort_horizon,
            )
        durable = frozenset(
            candidate.action
            for candidate in effort_certified
        )
        laser_survivors = frozenset()
        mixed_laser_ranked = bool(fast_laser_long)
        if fast_laser_long:
            # Stage 4 f12102 followed the sole focused corridor for 42 frames,
            # but the source laser sweep at that radius moved 2.46 px/frame
            # while focus limited Reimu to 2.0.  Source-normal movement had
            # three constant h56 survivors on the saved path.  These actions
            # have their own unchanged Hard-4 delivery certificates above.
            durable = frozenset(
                candidate.action for candidate in fast_laser_long
            )
        elif needs_active_mixed_replan(snapshot, effort_horizon):
            # At Stage 4 f15032, down-left survived both the short mixed
            # rollout and a laser-only h24 rollout, but had no continuation
            # when bullets and the active rotating laser were rolled out
            # together.  Rank the unchanged Hard-4 actions by that joint
            # evidence.  Warning lasers stay on the cheap path: the saved
            # warning snapshot made this search take longer than one frame.
            # The adaptive h16 requirement also excludes dense f6301, where
            # a 251-bullet joint search took 64 ms and expired at delivery.
            # Stationary full-length lasers are excluded too: f7209's five
            # straight lasers made this search take 52.4 ms without adding
            # the rotating-corridor evidence this branch exists to provide.
            mixed_laser_scores = (
                self.kernel.replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    LASER_EFFORT_HORIZON,
                    collision_margin=0.35,
                )
                if self.kernel is not None
                else replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    LASER_EFFORT_HORIZON,
                )
            )
            best_mixed_laser_score = max(mixed_laser_scores.values(), default=0)
            if best_mixed_laser_score:
                durable = frozenset(
                    action for action, score in mixed_laser_scores.items()
                    if score == best_mixed_laser_score
                )
                mixed_laser_ranked = True
        if (
            not mixed_laser_ranked
            and durable
            and snapshot.lasers
            and effort_horizon < LASER_EFFORT_HORIZON
        ):
            laser_survivors = frozenset(
                candidate.action
                for candidate in self._certify(
                    isolate_lasers(snapshot),
                    LASER_EFFORT_HORIZON,
                )
            )
            refined_durable = durable & laser_survivors
            if refined_durable:
                durable = refined_durable
        pre_boundary_corridor = (
            not snapshot.lasers
            and 100 <= len(snapshot.bullets) < 220
            and len(snapshot.enemies) <= 1
            and len(certified) == len(ACTIONS)
            and 0 < len(durable) <= 5
            and not any(
                boundary_relief(snapshot, action, 20) != 0
                for action in ACTIONS
            )
            and any(
                boundary_relief(snapshot, action, 20 + effort_horizon) != 0
                for action in ACTIONS
            )
        )
        if pre_boundary_corridor:
            # Stage 4 f16924 was still outside the 20-frame bottom warning,
            # so five constant h12 survivors were ranked alike and down won
            # on clearance.  It then became the shrinking last frontier and
            # reached an empty Hard-4 set at f16949.  The already-prepared h12
            # hazards gave down-right five safe second actions versus four for
            # down.  Use that cheap two-segment evidence just before a narrowed
            # corridor enters the warning band; eligibility remains Hard-4.
            corridor_scores = (
                self.kernel.replanning_scores(
                    snapshot,
                    effort_certified,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                    collision_margin=0.35,
                )
                if self.kernel is not None
                else replanning_scores(
                    snapshot,
                    effort_certified,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                )
            )
            best_corridor_score = max(corridor_scores.values(), default=0)
            if best_corridor_score:
                durable = frozenset(
                    action for action, score in corridor_scores.items()
                    if score == best_corridor_score
                )
        dense_boundary_corridor = (
            not snapshot.lasers
            and 220 <= len(snapshot.bullets) < 400
            and len(snapshot.enemies) <= 1
            and len(certified) < len(ACTIONS)
            and 0 < len(durable) <= 4
            and effort_horizon == 8
            and any(
                boundary_relief(snapshot, action, 20) != 0
                for action in ACTIONS
            )
        )
        if dense_boundary_corridor:
            # Stage 5 f3200 had down/right/down-right at h8. Ordinary wall
            # relief preferred the tangent right path, but the already
            # prepared h8 hazards gave it four second-segment continuations
            # versus five for down-right; the tangent path had no h20 survivor
            # and reached an empty Hard-4 set at f3235. A later physical branch
            # reached the same geometry with four h8 survivors at f3233. Its
            # tangent left path had four continuations versus seven for down,
            # and then disappeared by h12 before the set emptied at f3264.
            # Reuse the bounded h8 two-segment score once both hard and the
            # at-most-four-way durable sets narrow.
            # The saved 338-bullet state measured 1.65 ms median and 3.19 ms
            # max, versus 9.43/21.83 ms for an extra constant h20 scan.
            corridor_scores = (
                self.kernel.replanning_scores(
                    snapshot,
                    effort_certified,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                    collision_margin=0.35,
                )
                if self.kernel is not None
                else replanning_scores(
                    snapshot,
                    effort_certified,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                )
            )
            best_corridor_score = max(corridor_scores.values(), default=0)
            if best_corridor_score:
                durable = frozenset(
                    action for action, score in corridor_scores.items()
                    if score == best_corridor_score
                )
        repairable = frozenset()
        single_wall_trap = durable and all(
            heads_toward_single_wall(snapshot, action)
            for action in durable
        )
        early_boundary_trap = (
            not snapshot.lasers
            and not dense_corner_planning
            and not single_wall_trap
            and durable
            and all(
                boundary_relief(snapshot, action, 20) < 0
                for action in durable
            )
        )
        # The generic wall repair below ranks a first segment when some later
        # continuation exists, but it does not retain which continuation made
        # that score viable. In Stage 5's f3218 dense corner, applying it to
        # h12 would choose stay and allow the next decision to reverse before
        # the modeled split. Keep the directly certified h12 constant frontier
        # in this one bounded case; if it is empty, the ordinary repair and
        # last-frontier fallbacks below still run.
        if (
            durable
            and len(certified) == len(ACTIONS)
            and len(snapshot.enemies) <= 1
            and effort_horizon >= 8
            and (
                single_wall_trap
                or early_boundary_trap
            )
        ):
            # Stage 4 f12461's sole constant h12 proposal descended into the
            # bottom wall, although the existing two-segment model proved the
            # current horizontal corridor still had a valid continuation.
            # Bullet-only f4658 and f4540 similarly had positive two-segment
            # continuations one Hard-4 segment before the ordinary boundary
            # lookahead, while every constant proposal spent remaining room.
            # Rotating lasers are deliberately excluded from this extension.
            # Only explore while Hard-4 is fully open: f6364 already had just
            # six hard actions, and this extra search aged a sufficient h12
            # decision by three frames. Keep such non-wall continuations in
            # the soft tier. Multi-enemy f1565 is excluded because this second
            # branch search took 44.4 ms; the fixed Hard-4 set above remains
            # the authority.
            wall_scores = (
                self.kernel.replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                    collision_margin=0.35,
                )
                if self.kernel is not None
                else replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    effort_horizon,
                )
            )
            if early_boundary_trap:
                viable = frozenset(
                    action for action, score in wall_scores.items() if score > 0
                )
                best_relief = max(
                    (
                        boundary_relief(snapshot, action, 20)
                        for action in viable
                    ),
                    default=0,
                )
                durable = frozenset(
                    action for action in viable
                    if boundary_relief(snapshot, action, 20) == best_relief
                )
            else:
                wall_continuations = frozenset(
                    action
                    for action, score in wall_scores.items()
                    if score > 0
                    and not heads_toward_single_wall(snapshot, action)
                )
                best_wall_score = max(
                    (wall_scores.get(action, 0) for action in durable),
                    default=0,
                )
                if best_wall_score:
                    durable = frozenset(
                        action
                        for action in durable
                        if wall_scores.get(action, 0) == best_wall_score
                    )
                durable |= wall_continuations
        if not durable and effort_horizon >= 8:
            # Stage 4 entered a corner because the adaptive layer allocated 16
            # frames but the fallback repair proposal discarded everything
            # after frame 8.  Spend the existing soft budget; hard eligibility
            # remains the fixed four-frame set above.
            repair_horizon = effort_horizon
            scores = (
                self.kernel.replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    repair_horizon,
                    collision_margin=0.35,
                )
                if self.kernel is not None
                else replanning_scores(
                    snapshot,
                    certified,
                    HARD_SAFETY_HORIZON,
                    repair_horizon,
                )
            )
            best_score = max(scores.values(), default=0)
            if best_score:
                repairable = frozenset(
                    action for action, score in scores.items() if score == best_score
                )
        if (
            not durable
            and not repairable
            and effort_horizon > HARD_SAFETY_HORIZON + 1
        ):
            # Physical Stage 4 branches exhausted the full constant-action
            # and two-segment proposals while one complete mixed-hazard action
            # still survived substantially longer than the boundary heuristic's
            # choice. Preserve the longest nonempty frontier for soft ranking.
            durable = frozenset(
                candidate.action
                for candidate in self._last_viable_frontier(
                    snapshot,
                    HARD_SAFETY_HORIZON + 1,
                    effort_horizon - 1,
                )
            )
        if (
            not durable
            and not repairable
            and snapshot.lasers
            and effort_horizon < LASER_EFFORT_HORIZON
        ):
            laser_survivors = frozenset(
                candidate.action
                for candidate in self._certify(
                    isolate_lasers(snapshot),
                    LASER_EFFORT_HORIZON,
                )
            )
            retained = retained_current_corridor(
                snapshot,
                frozenset(candidate.action for candidate in certified),
                laser_survivors,
            )
            if retained is not None:
                # Continuity only: do not steer into a new laser-only route
                # after the mixed proposal and its repair have both failed.
                durable = frozenset((retained,))
        chosen = self.ranker.choose(
            snapshot,
            certified,
            durable,
            repairable,
            repair_span=HARD_SAFETY_HORIZON,
            discouraged_actions=discouraged,
        )
        held_horizon = (
            effort_horizon
            if any(candidate.action == held_action for candidate in effort_certified)
            else HARD_SAFETY_HORIZON
        )
        if (
            precomputed_current_effort
            and any(
                candidate.action == held_action
                for candidate in precomputed_current_effort
            )
        ):
            held_horizon = max(held_horizon, precomputed_current_horizon)
        if (
            held_horizon == HARD_SAFETY_HORIZON
            and any(candidate.action == held_action for candidate in certified)
            and effort_horizon > HARD_SAFETY_HORIZON + 1
        ):
            held_horizon = max(
                held_horizon,
                self._longest_selected_horizon(
                    snapshot,
                    HARD_SAFETY_HORIZON + 1,
                    effort_horizon - 1,
                    (held_action,),
                ),
            )
        if any(candidate.action == held_action for candidate in fast_laser_long):
            held_horizon = max(held_horizon, LASER_SPEED_HORIZON)
        if any(candidate.action == held_action for candidate in fast_recovery_long):
            held_horizon = max(held_horizon, effort_horizon)
        return Decision(
            chosen.action,
            certified,
            chosen.clearance,
            HARD_SAFETY_HORIZON,
            "ok",
            effort_horizon,
            len(durable),
            len(repairable),
            held_horizon,
        )

import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from th06.model import ACTIONS, CONTROL_ACTIONS, Bullet, SafeAction, Snapshot
from th06.kernels.safety import NativeSafetyKernel
from th06.ranking import ProposalRanker, preferred_route_reference_actions
from th06.solver import (
    BASE_POLICY_HORIZON,
    EFFORT_HORIZONS,
    HARD_SAFETY_HORIZON,
    SAME_FRAME_DECISION_BUDGET_MS,
    TERMINAL_DEADLINE_GUARD_MS,
    EffortController,
    Solver,
)


def snapshot(**changes) -> Snapshot:
    values = dict(
        frame=100,
        stage=1,
        player_state=0,
        x=192.0,
        y=380.0,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.828427,
        focus_diagonal_speed=1.414214,
        frame_multiplier=1.0,
        input_mask=0x04,
        bullets=(),
        laser_count=0,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
    )
    values.update(changes)
    return Snapshot(**values)


class ManualClock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds

    def advance_ms(self, milliseconds: float) -> None:
        self.seconds += milliseconds / 1000.0


class ProgressiveKernel:
    def __init__(
        self,
        clock: ManualClock,
        hard,
        frontiers=None,
        scores=None,
        scores_by_horizon=None,
        hard_ms=1.0,
    ):
        self.clock = clock
        self.hard = hard
        self.frontiers = frontiers or {}
        self.scores = scores or {}
        self.scores_by_horizon = scores_by_horizon or {}
        self.hard_ms = hard_ms
        self.calls = []

    def certify_selected_delivery_sets(
        self, state, horizon, actions, collision_margin
    ):
        self.calls.append(("hard", horizon, tuple(actions)))
        self.clock.advance_ms(self.hard_ms)
        return self.hard, self.hard

    def prepare(self, state, horizon):
        self.calls.append(("prepare", horizon))
        self.clock.advance_ms(1.0)

    def certify_selected(self, state, horizon, actions, collision_margin):
        self.calls.append(("frontier", horizon, tuple(actions)))
        self.clock.advance_ms(0.5)
        allowed = frozenset(actions)
        return tuple(
            candidate
            for candidate in self.frontiers.get(horizon, self.hard)
            if candidate.action in allowed
        )

    def nominal_policy_counts(
        self, state, candidates, segment_length, horizon, collision_margin
    ):
        self.calls.append(("policy", horizon, tuple(candidates)))
        self.clock.advance_ms(1.0)
        return self.scores_by_horizon.get(horizon, self.scores)


class BudgetedProgressiveKernel(ProgressiveKernel):
    def __init__(
        self,
        *args,
        budgeted_ms_by_horizon=None,
        flexible_completed_horizon=None,
        flexible_reached_maximum=True,
        reachability_by_horizon=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.budgeted_ms_by_horizon = budgeted_ms_by_horizon or {}
        self.flexible_completed_horizon = flexible_completed_horizon
        self.flexible_reached_maximum = flexible_reached_maximum
        self.reachability_by_horizon = reachability_by_horizon

    def nominal_policy_counts_budgeted(
        self,
        state,
        candidates,
        segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(
            ("budgeted_policy", horizon, budget_ms, tuple(candidates))
        )
        required_ms = self.budgeted_ms_by_horizon.get(horizon, 1.0)
        if required_ms > budget_ms:
            self.clock.advance_ms(budget_ms)
            return None
        self.clock.advance_ms(required_ms)
        scores = self.scores_by_horizon.get(horizon, self.scores)
        allowed = frozenset(candidate.action for candidate in candidates)
        return {
            action: score for action, score in scores.items()
            if action in allowed
        }

    def boolean_reachability_progressive(
        self,
        state,
        candidates,
        segment_length,
        minimum_horizon,
        maximum_horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append((
            "progressive",
            minimum_horizon,
            maximum_horizon,
            budget_ms,
            tuple(candidates),
        ))
        available = (
            self.reachability_by_horizon
            if self.reachability_by_horizon is not None
            else self.scores_by_horizon
        )
        available_horizons = tuple(
            horizon for horizon in available
            if minimum_horizon <= horizon <= maximum_horizon
        )
        if self.flexible_completed_horizon is not None:
            affordable_horizons = (self.flexible_completed_horizon,)
        else:
            affordable_horizons = tuple(
                horizon for horizon in available_horizons
                if self.budgeted_ms_by_horizon.get(horizon, 1.0)
                <= budget_ms
            )
        if not affordable_horizons:
            self.clock.advance_ms(budget_ms)
            return None
        completed_horizon = max(affordable_horizons)
        required_ms = self.budgeted_ms_by_horizon.get(
            completed_horizon, 1.0
        )
        self.clock.advance_ms(required_ms)
        scores = (
            self.reachability_by_horizon.get(completed_horizon, {})
            if self.reachability_by_horizon is not None
            else self.scores_by_horizon.get(
                completed_horizon,
                self.scores_by_horizon.get(minimum_horizon, self.scores),
            )
        )
        allowed = frozenset(candidate.action for candidate in candidates)
        if self.reachability_by_horizon is None:
            best = max(
                (score for action, score in scores.items() if action in allowed),
                default=0,
            )
            scores = {
                action: int(score == best and best > 0)
                for action, score in scores.items()
            }
        return (
            completed_horizon,
            {
                action: score for action, score in scores.items()
                if action in allowed
            },
            self.flexible_reached_maximum
            and completed_horizon == maximum_horizon,
        )


class TerminalRefinementKernel(BudgetedProgressiveKernel):
    def __init__(self, *args, terminal_scores_by_horizon, **kwargs):
        super().__init__(*args, **kwargs)
        self.terminal_scores_by_horizon = terminal_scores_by_horizon

    def terminal_counts_budgeted(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("terminal_counts", horizon, tuple(candidates)))
        self.clock.advance_ms(min(1.0, budget_ms))
        if budget_ms < 1.0:
            return None
        allowed = frozenset(candidate.action for candidate in candidates)
        return {
            action: score for action, score
            in self.terminal_scores_by_horizon[horizon].items()
            if action in allowed
        }

    def segment_terminal_counts_progressive(
        self,
        _state,
        candidates,
        _segment_length,
        minimum_horizon,
        maximum_horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append((
            "terminal_progressive",
            minimum_horizon,
            maximum_horizon,
            tuple(candidates),
        ))
        self.clock.advance_ms(min(1.0, budget_ms))
        if budget_ms < 1.0:
            return None
        if (
            self.flexible_completed_horizon is not None
            and minimum_horizon > self.flexible_completed_horizon
        ):
            return None
        completed_horizon = min(
            maximum_horizon,
            (
                self.flexible_completed_horizon
                if self.flexible_completed_horizon is not None
                else maximum_horizon
            ),
        )
        scores_horizon = (
            completed_horizon
            if completed_horizon in self.terminal_scores_by_horizon
            else self.flexible_completed_horizon
        )
        if scores_horizon not in self.terminal_scores_by_horizon:
            return None
        allowed = frozenset(candidate.action for candidate in candidates)
        return (
            completed_horizon,
            {
                action: score for action, score
                in self.terminal_scores_by_horizon[
                    scores_horizon
                ].items()
                if action in allowed
            },
            completed_horizon == maximum_horizon,
        )


class DeliveryReplanningKernel(TerminalRefinementKernel):
    def __init__(
        self,
        *args,
        delivery_scores,
        delivery_ms=1.0,
        delivery_robustness_complete=True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.delivery_scores = delivery_scores
        self.delivery_ms = delivery_ms
        self.delivery_robustness_complete = delivery_robustness_complete

    def replanning_scores_budgeted(
        self,
        _state,
        candidates,
        segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append((
            "delivery_replanning",
            segment_length,
            horizon,
            tuple(candidate.action for candidate in candidates),
        ))
        if self.delivery_ms > budget_ms:
            self.clock.advance_ms(budget_ms)
            return None
        self.clock.advance_ms(self.delivery_ms)
        allowed = frozenset(candidate.action for candidate in candidates)
        return {
            action: score for action, score in self.delivery_scores.items()
            if action in allowed
        }

    def replanning_scores_progressive_budgeted(self, *args, **kwargs):
        # Preserve the retired keyword in this test double so the regression
        # fails if a predicted horizon is ever allowed to suppress an
        # affordable exact refinement again.
        robustness = kwargs.pop("robustness", True)
        scores = self.replanning_scores_budgeted(*args, **kwargs)
        if (
            scores is not None
            and (
                not robustness
                or not self.delivery_robustness_complete
            )
        ):
            scores = {
                action: int(score > 0)
                for action, score in scores.items()
            }
        return (
            None
            if scores is None
            else (
                scores,
                robustness and self.delivery_robustness_complete,
            )
        )


class CoarseMacroKernel(TerminalRefinementKernel):
    def __init__(
        self,
        *args,
        coarse_frontier,
        macro_scores,
        macro_ms=1.0,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.coarse_frontier = coarse_frontier
        self.macro_scores = macro_scores
        self.macro_ms = macro_ms

    def certify_selected_budgeted(
        self,
        _state,
        horizon,
        actions,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("coarse_frontier", horizon, tuple(actions)))
        self.clock.advance_ms(min(0.25, budget_ms))
        if budget_ms < 0.25:
            return None
        allowed = frozenset(actions)
        return tuple(
            candidate for candidate in (
                self.hard
                if horizon <= BASE_POLICY_HORIZON
                else self.coarse_frontier
            )
            if candidate.action in allowed
        )

    def macro_tail_scores_budgeted(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("macro_tail", horizon, tuple(candidates)))
        if self.macro_ms > budget_ms:
            self.clock.advance_ms(budget_ms)
            return None
        self.clock.advance_ms(self.macro_ms)
        allowed = frozenset(candidate.action for candidate in candidates)
        return {
            action: score for action, score in self.macro_scores.items()
            if action in allowed
        }


class PublicationFragileKernel(BudgetedProgressiveKernel):
    def __init__(self, *args, extended_safe=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.extended_safe = extended_safe

    def certify_selected_extended_delivery(
        self,
        _state,
        _horizon,
        actions,
        collision_margin,
    ):
        self.calls.append(("extended", tuple(actions)))
        self.clock.advance_ms(0.1)
        if not self.extended_safe:
            return ()
        allowed = frozenset(actions)
        return tuple(
            candidate for candidate in self.hard
            if candidate.action in allowed
        )

class AnytimePolicyTests(unittest.TestCase):
    def setUp(self):
        state = snapshot()
        self.hard = tuple(
            SafeAction(action, 10.0 - index, state.x, state.y)
            for index, action in enumerate(ACTIONS[:3])
        )

    def solver(self, kernel, clock, budget=12.5):
        solver = Solver(decision_budget_ms=budget, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        return solver

    def test_boolean_reachability_charges_projection_to_native_budget(self):
        kernel = object.__new__(NativeSafetyKernel)
        kernel._prepare_reusable = lambda *_args: (None, None, None, None)
        received_budgets = []

        def progressive(*arguments):
            received_budgets.append(arguments[18])
            return 1

        kernel.progressive_viability_function = progressive
        with patch(
            "th06.kernels.safety.time.perf_counter",
            side_effect=(10.0, 10.003),
        ):
            result = kernel.boolean_reachability_progressive(
                snapshot(),
                self.hard,
                HARD_SAFETY_HORIZON,
                BASE_POLICY_HORIZON,
                20,
                collision_margin=0.35,
                budget_ms=10.0,
            )

        self.assertIsNone(result)
        self.assertEqual(len(received_budgets), 1)
        self.assertAlmostEqual(received_budgets[0], 7.0)

    def test_hard_authority_is_computed_before_soft_work(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(clock, self.hard)
        solver = self.solver(kernel, clock)

        decision = solver.decide(snapshot())

        self.assertEqual(kernel.calls[0][0], "hard")
        self.assertEqual(kernel.calls[1], ("prepare", EFFORT_HORIZONS[0]))
        self.assertEqual(decision.safe_actions, self.hard)

    def test_affordable_frontier_uses_deepest_measured_rung(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(clock, self.hard)
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.rollout_ms_per_work = 0.0

        horizons = []
        for offset in range(4):
            decision = solver.decide(replace(snapshot(), frame=100 + offset))
            horizons.append(decision.effort_horizon)

        self.assertEqual(horizons, [20, 20, 20, 20])

    def test_frontier_contraction_triggers_general_policy_only(self):
        clock = ManualClock()
        up = self.hard[1].action
        outsider = ACTIONS[4]
        kernel = ProgressiveKernel(
            clock,
            self.hard,
            frontiers={6: self.hard[:-1]},
            scores={
                self.hard[0].action: 2,
                up: 5,
                self.hard[2].action: 1,
                outsider: 99,
            },
        )
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 6

        decision = solver.decide(snapshot())

        self.assertEqual(decision.safe_actions, self.hard)
        self.assertEqual(decision.action, up)
        self.assertIn("policy", [call[0] for call in kernel.calls])
        self.assertNotIn(outsider, {item.action for item in decision.safe_actions})

    def test_two_segment_policy_is_a_regular_affordable_rung(self):
        clock = ManualClock()
        up = self.hard[1].action
        kernel = ProgressiveKernel(
            clock,
            self.hard,
            scores={
                self.hard[0].action: 2,
                up: 5,
                self.hard[2].action: 1,
            },
        )
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 6

        decision = solver.decide(snapshot())

        self.assertEqual(decision.effort_horizon, 20)
        self.assertEqual(decision.action, up)
        self.assertIn("policy", [call[0] for call in kernel.calls])

    def test_frontier_contraction_progressively_deepens_policy(self):
        clock = ManualClock()
        up = self.hard[1].action
        kernel = ProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: self.hard[:-1]},
            scores_by_horizon={
                8: {candidate.action: 3 for candidate in self.hard},
                12: {
                    self.hard[0].action: 2,
                    up: 7,
                    self.hard[2].action: 1,
                },
            },
        )
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 8

        decision = solver.decide(snapshot())

        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "policy"],
            [8, 12, 16],
        )
        self.assertEqual(decision.action, up)
        self.assertEqual(decision.effort_horizon, 20)

    def test_constant_lower_bound_precedes_branching_search(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: self.hard[:-1]},
            scores_by_horizon={
                8: {candidate.action: 3 for candidate in self.hard},
                12: {candidate.action: 2 for candidate in self.hard},
            },
        )
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 12

        solver.decide(snapshot())

        calls = [(call[0], call[1]) for call in kernel.calls]
        self.assertLess(calls.index(("frontier", 12)), calls.index(("policy", 8)))

    def test_progressive_reachability_uses_fresh_completed_evidence(self):
        clock = ManualClock()
        deep_action = self.hard[2].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            scores_by_horizon={
                8: {
                    self.hard[0].action: 5,
                    self.hard[1].action: 3,
                    deep_action: 1,
                },
                16: {
                    self.hard[0].action: 2,
                    self.hard[1].action: 4,
                    deep_action: 9,
                },
            },
            budgeted_ms_by_horizon={16: 4.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_action)
        self.assertEqual(decision.effort_horizon, 16)
        self.assertEqual(decision.held_horizon, 16)
        self.assertNotIn("policy", [call[0] for call in kernel.calls])
        progressive = next(
            call for call in kernel.calls if call[0] == "progressive"
        )
        self.assertEqual(progressive[1:3], (8, 20))
        self.assertEqual(progressive[4], self.hard)

    def test_boolean_membership_keeps_every_winning_first_action(self):
        clock = ManualClock()
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            reachability_by_horizon={
                16: {
                    self.hard[0].action: 1,
                    self.hard[1].action: 1,
                    self.hard[2].action: 0,
                },
            },
            budgeted_ms_by_horizon={16: 2.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, self.hard[0].action)
        self.assertEqual(decision.effort_horizon, 16)
        self.assertEqual(decision.effort_safe_count, 2)

    def test_exact_terminal_states_refine_boolean_winners_only(self):
        clock = ManualClock()
        kernel = TerminalRefinementKernel(
            clock,
            self.hard,
            reachability_by_horizon={
                16: {
                    self.hard[0].action: 1,
                    self.hard[1].action: 1,
                    self.hard[2].action: 0,
                },
            },
            terminal_scores_by_horizon={
                8: {
                    self.hard[0].action: 3,
                    self.hard[1].action: 5,
                    self.hard[2].action: 0,
                },
                12: {
                    self.hard[0].action: 7,
                    self.hard[1].action: 9,
                    self.hard[2].action: 0,
                },
                16: {
                    self.hard[0].action: 11,
                    self.hard[1].action: 13,
                    self.hard[2].action: 0,
                },
            },
        )
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, self.hard[1].action)
        self.assertEqual(decision.effort_horizon, 16)
        self.assertEqual(decision.effort_safe_count, 1)
        self.assertEqual(
            [
                call[1:3] for call in kernel.calls
                if call[0] == "terminal_progressive"
            ],
            [(8, 8), (12, 16)],
        )
        self.assertNotEqual(decision.action, self.hard[2].action)

    def test_terminal_ladder_extends_beyond_coarse_limit(self):
        clock = ManualClock()
        deep_action = self.hard[1].action
        kernel = TerminalRefinementKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                12: {
                    self.hard[0].action: 4,
                    deep_action: 9,
                    self.hard[2].action: 2,
                },
            },
            flexible_completed_horizon=12,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 8

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_action)
        self.assertEqual(decision.effort_horizon, 12)
        self.assertIn(("prepare", 16), kernel.calls)
        self.assertEqual(
            [
                call[1:3] for call in kernel.calls
                if call[0] == "terminal_progressive"
            ],
            [(8, 8), (12, 16)],
        )

    def test_completed_base_rung_can_probe_next_rung_from_residual(self):
        clock = ManualClock()
        shallow = self.hard[0]
        deep = self.hard[1]

        class ViabilityFirstKernel(DeliveryReplanningKernel):
            def replanning_viability_budgeted(
                self,
                _state,
                candidates,
                segment_length,
                horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "delivery_viability",
                    segment_length,
                    horizon,
                    tuple(candidate.action for candidate in candidates),
                ))
                if budget_ms < 1.0:
                    self.clock.advance_ms(budget_ms)
                    return None
                self.clock.advance_ms(1.0)
                return {
                    candidate.action: 1 for candidate in candidates
                }

        kernel = ViabilityFirstKernel(
            clock,
            self.hard,
            delivery_scores={
                shallow.action: 9,
                deep.action: 5,
                self.hard[2].action: 1,
            },
            delivery_ms=100.0,
            terminal_scores_by_horizon={
                12: {
                    shallow.action: 4,
                    deep.action: 12,
                    self.hard[2].action: 2,
                },
            },
            scores_by_horizon={},
            flexible_completed_horizon=12,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: HARD_SAFETY_HORIZON

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep.action)
        self.assertEqual(decision.effort_horizon, 12)
        self.assertIn(
            "delivery_viability",
            [call[0] for call in kernel.calls],
        )
        self.assertNotIn(
            "delivery_replanning",
            [call[0] for call in kernel.calls],
        )
        self.assertIn(("prepare", 12), kernel.calls)
        self.assertIn(
            (12, 12),
            [
                call[1:3] for call in kernel.calls
                if call[0] == "terminal_progressive"
            ],
        )
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_next_terminal_projection_completes_before_deeper_promotion(self):
        clock = ManualClock()
        shallow = self.hard[0]
        deep = self.hard[1]

        class NextRungKernel(DeliveryReplanningKernel):
            def replanning_viability_budgeted(
                self,
                _state,
                candidates,
                segment_length,
                horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "delivery_viability",
                    segment_length,
                    horizon,
                    tuple(candidate.action for candidate in candidates),
                ))
                if budget_ms < 1.0:
                    self.clock.advance_ms(budget_ms)
                    return None
                self.clock.advance_ms(1.0)
                return {
                    candidate.action: 1 for candidate in candidates
                }

            def prepare(self, _state, horizon):
                self.calls.append(("prepare", horizon))
                self.clock.advance_ms(4.0 if horizon == 12 else 9.5)

        kernel = NextRungKernel(
            clock,
            self.hard,
            delivery_scores={
                candidate.action: 1 for candidate in self.hard
            },
            delivery_ms=100.0,
            terminal_scores_by_horizon={
                12: {
                    shallow.action: 3,
                    deep.action: 9,
                    self.hard[2].action: 1,
                },
            },
            scores_by_horizon={},
            flexible_completed_horizon=12,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep.action)
        self.assertGreaterEqual(decision.effort_horizon, 12)
        self.assertEqual(
            [call for call in kernel.calls if call[0] == "prepare"],
            [("prepare", 12)],
        )
        self.assertIn(
            (12, 12),
            [
                call[1:3] for call in kernel.calls
                if call[0] == "terminal_progressive"
            ],
        )
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_base_terminal_rung_survives_coarse_limit_six(self):
        clock = ManualClock()
        local_action = self.hard[1].action
        kernel = TerminalRefinementKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                8: {
                    self.hard[0].action: 4,
                    local_action: 9,
                    self.hard[2].action: 2,
                },
            },
            flexible_completed_horizon=8,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 6

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, local_action)
        self.assertEqual(decision.effort_horizon, 8)
        self.assertIn(("prepare", 8), kernel.calls)
        self.assertIn(("prepare", 16), kernel.calls)
        calls = [
            call[1:3] for call in kernel.calls
            if call[0] == "terminal_progressive"
        ]
        self.assertEqual(calls[0], (8, 8))
        self.assertIn((12, 16), calls)

    def test_base_projection_completes_before_coalesced_deep_prepare(self):
        clock = ManualClock()
        deep_action = self.hard[1].action

        class MeasuredProjectionKernel(TerminalRefinementKernel):
            def prepare(self, _state, horizon):
                self.calls.append(("prepare", horizon))
                self.clock.advance_ms({8: 2.5, 12: 3.8, 16: 6.0}[horizon])

            def segment_terminal_counts_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                minimum_horizon,
                maximum_horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "terminal_progressive",
                    minimum_horizon,
                    maximum_horizon,
                    tuple(candidates),
                ))
                required_ms = {8: 0.4, 16: 1.0}[maximum_horizon]
                self.clock.advance_ms(min(required_ms, budget_ms))
                if budget_ms < required_ms:
                    return None
                allowed = frozenset(
                    candidate.action for candidate in candidates
                )
                completed_horizon = (
                    12 if maximum_horizon == 16 else maximum_horizon
                )
                return (
                    completed_horizon,
                    {
                        action: score for action, score
                        in self.terminal_scores_by_horizon[
                            completed_horizon
                        ].items()
                        if action in allowed
                    },
                    completed_horizon == maximum_horizon,
                )

        kernel = MeasuredProjectionKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                8: {candidate.action: 9 for candidate in self.hard},
                12: {
                    self.hard[0].action: 4,
                    deep_action: 9,
                    self.hard[2].action: 2,
                },
            },
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 8

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_action)
        self.assertEqual(decision.effort_horizon, 12)
        self.assertEqual(
            [
                call[:3] for call in kernel.calls
                if call[0] in {"prepare", "terminal_progressive"}
            ],
            [
                ("prepare", 8),
                ("terminal_progressive", 8, 8),
                ("prepare", 16),
                ("terminal_progressive", 12, 16),
            ],
        )

    def test_promoted_projection_cost_protects_completed_local_result(self):
        clock = ManualClock()
        local = self.hard[0].action
        witness = self.hard[1].action

        class PromotedProjectionKernel(CoarseMacroKernel):
            def prepare(self, _state, horizon):
                self.calls.append(("prepare", horizon))
                self.clock.advance_ms({8: 0.0, 16: 2.5}.get(horizon, 10.0))

        kernel = PromotedProjectionKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                8: {candidate.action: 1 for candidate in self.hard},
                16: {
                    local: 9,
                    witness: 5,
                    self.hard[2].action: 1,
                },
            },
            coarse_frontier=(self.hard[1],),
            macro_scores={local: 0, witness: 1},
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 8

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, local)
        self.assertEqual(decision.effort_horizon, 16)
        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "prepare"],
            [8, 16],
        )
        self.assertNotIn("coarse_frontier", {call[0] for call in kernel.calls})
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_coarse_projection_extends_only_while_each_rung_fits(self):
        clock = ManualClock()
        local = self.hard[0].action
        witness = self.hard[1].action

        class GrowingProjectionKernel(CoarseMacroKernel):
            def prepare(self, _state, horizon):
                self.calls.append(("prepare", horizon))
                self.clock.advance_ms({
                    8: 0.0,
                    16: 1.0,
                    24: 2.0,
                    32: 3.0,
                    40: 4.0,
                    48: 5.0,
                }[horizon])

        kernel = GrowingProjectionKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                16: {
                    local: 9,
                    witness: 5,
                    self.hard[2].action: 1,
                },
            },
            flexible_completed_horizon=16,
            coarse_frontier=(self.hard[1],),
            macro_scores={local: 0, witness: 1},
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, witness)
        self.assertEqual(decision.effort_horizon, 32)
        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "prepare"],
            [8, 16, 24, 32],
        )
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_budgeted_coarse_macro_adjudicates_local_winner_and_long_witness(self):
        clock = ManualClock()
        local = self.hard[0].action
        witness = self.hard[1].action
        kernel = CoarseMacroKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                16: {
                    local: 9,
                    witness: 5,
                    self.hard[2].action: 1,
                },
            },
            flexible_completed_horizon=16,
            coarse_frontier=(self.hard[1],),
            macro_scores={local: 0, witness: 1},
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, witness)
        self.assertEqual(decision.effort_horizon, 48)
        self.assertEqual(
            next(call for call in kernel.calls if call[0] == "macro_tail")[2],
            (self.hard[0], self.hard[1]),
        )
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_timed_out_coarse_macro_preserves_completed_local_result(self):
        clock = ManualClock()
        local = self.hard[0].action
        witness = self.hard[1].action
        kernel = CoarseMacroKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                16: {
                    local: 9,
                    witness: 5,
                    self.hard[2].action: 1,
                },
            },
            flexible_completed_horizon=16,
            coarse_frontier=(self.hard[1],),
            macro_scores={local: 0, witness: 1},
            macro_ms=100.0,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, local)
        self.assertEqual(decision.effort_horizon, 16)
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_deep_constant_scan_discards_on_residual_budget_timeout(self):
        clock = ManualClock()
        deep_action = self.hard[1].action

        class BudgetedConstantKernel(TerminalRefinementKernel):
            def certify_selected_budgeted(
                self,
                _state,
                horizon,
                actions,
                collision_margin,
                budget_ms,
            ):
                self.calls.append(
                    ("budgeted_frontier", horizon, budget_ms, tuple(actions))
                )
                self.clock.advance_ms(budget_ms)
                return None

        kernel = BudgetedConstantKernel(
            clock,
            self.hard,
            terminal_scores_by_horizon={
                12: {
                    self.hard[0].action: 4,
                    deep_action: 9,
                    self.hard[2].action: 2,
                },
            },
            flexible_completed_horizon=12,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_action)
        self.assertEqual(decision.effort_horizon, 12)
        calls = [call for call in kernel.calls if call[0] == "budgeted_frontier"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], 16)
        self.assertGreater(calls[0][2], 0.0)
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_missing_extended_authority_caps_only_current_effort(self):
        clock = ManualClock()
        shallow_action = self.hard[0].action
        deep_action = self.hard[1].action
        kernel = PublicationFragileKernel(
            clock,
            self.hard,
            frontiers={12: ()},
            scores_by_horizon={
                8: {
                    shallow_action: 9,
                    deep_action: 2,
                    self.hard[2].action: 1,
                },
                12: {
                    shallow_action: 2,
                    deep_action: 9,
                    self.hard[2].action: 1,
                },
            },
            budgeted_ms_by_horizon={8: 3.0, 12: 6.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 12

        fragile = solver.decide(snapshot())

        self.assertEqual(fragile.safe_actions, self.hard)
        self.assertEqual(fragile.action, shallow_action)
        self.assertEqual(fragile.effort_horizon, HARD_SAFETY_HORIZON)
        self.assertNotIn(
            "progressive",
            [call[0] for call in kernel.calls],
        )
        self.assertLessEqual(clock.seconds * 1000.0, SAME_FRAME_DECISION_BUDGET_MS)

        kernel.extended_safe = True
        kernel.calls.clear()
        second_started_ms = clock.seconds * 1000.0
        robust = solver.decide(snapshot(frame=101))

        self.assertEqual(robust.safe_actions, self.hard)
        self.assertEqual(robust.action, deep_action)
        self.assertGreaterEqual(robust.effort_horizon, 12)
        self.assertLessEqual(
            clock.seconds * 1000.0 - second_started_ms,
            12.5,
        )

    def test_completed_progressive_rung_needs_no_intermediate_recompute(self):
        clock = ManualClock()
        deep_action = self.hard[2].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: ()},
            scores_by_horizon={
                8: {
                    self.hard[0].action: 5,
                    self.hard[1].action: 3,
                    deep_action: 1,
                },
                12: {
                    self.hard[0].action: 2,
                    self.hard[1].action: 8,
                    deep_action: 1,
                },
                16: {
                    self.hard[0].action: 1,
                    self.hard[1].action: 2,
                    deep_action: 10,
                },
            },
            budgeted_ms_by_horizon={16: 4.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.observe_policy(
            snapshot(),
            len(self.hard),
            16,
            6.0,
        )

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_action)
        self.assertEqual(decision.effort_horizon, 16)
        self.assertNotIn("policy", [call[0] for call in kernel.calls])
        self.assertEqual(
            [call[0] for call in kernel.calls].count("progressive"),
            1,
        )

    def test_progressive_timeout_publishes_last_complete_rung(self):
        clock = ManualClock()
        base_action = self.hard[0].action
        fallback_action = self.hard[1].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: ()},
            scores_by_horizon={
                8: {
                    self.hard[0].action: 5,
                    fallback_action: 3,
                    self.hard[2].action: 1,
                },
                12: {
                    self.hard[0].action: 2,
                    fallback_action: 8,
                    self.hard[2].action: 1,
                },
                16: {
                    self.hard[0].action: 1,
                    fallback_action: 2,
                    self.hard[2].action: 10,
                },
            },
            budgeted_ms_by_horizon={12: 2.0, 16: 20.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, fallback_action)
        self.assertEqual(decision.effort_horizon, 12)
        self.assertEqual(
            [call[0] for call in kernel.calls].count("progressive"),
            1,
        )
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_frame_granular_rung_can_retain_nonconstant_action(self):
        clock = ManualClock()
        retained_action = self.hard[0].action
        excluded_action = self.hard[1].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: ()},
            scores_by_horizon={
                8: {
                    retained_action: 4,
                    excluded_action: 5,
                    self.hard[2].action: 1,
                },
                12: {
                    retained_action: 2,
                    excluded_action: 8,
                    self.hard[2].action: 1,
                },
                16: {
                    retained_action: 1,
                    excluded_action: 10,
                    self.hard[2].action: 2,
                },
            },
            budgeted_ms_by_horizon={12: 2.0, 16: 20.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, excluded_action)
        self.assertNotEqual(decision.action, retained_action)
        self.assertEqual(decision.effort_horizon, 12)
        self.assertIn("frontier", [call[0] for call in kernel.calls])

    def test_progressive_reachability_evaluates_every_hard_action(self):
        clock = ManualClock()
        current = self.hard[0]
        lower_winner = self.hard[1]
        constant_winner = self.hard[2]
        omitted = SafeAction(ACTIONS[3], 1.0, 192.0, 380.0)
        hard = self.hard + (omitted,)
        kernel = BudgetedProgressiveKernel(
            clock,
            hard,
            frontiers={16: (constant_winner,)},
            scores_by_horizon={
                8: {
                    current.action: 2,
                    lower_winner.action: 9,
                    constant_winner.action: 4,
                    omitted.action: 1,
                },
                16: {
                    current.action: 3,
                    lower_winner.action: 12,
                    constant_winner.action: 8,
                    omitted.action: 99,
                },
            },
            budgeted_ms_by_horizon={16: 2.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        progressive = next(
            call for call in kernel.calls if call[0] == "progressive"
        )
        self.assertEqual(
            {candidate.action for candidate in progressive[4]},
            {candidate.action for candidate in hard},
        )
        self.assertEqual(decision.action, omitted.action)

    def test_deepest_complete_progressive_rung_can_reverse_shallow_choice(self):
        clock = ManualClock()
        current = self.hard[0]
        lower_winner = self.hard[1]
        constant_survivor = self.hard[2]
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={16: (lower_winner, constant_survivor)},
            scores_by_horizon={
                12: {
                    current.action: 9,
                    lower_winner.action: 10,
                    constant_survivor.action: 5,
                },
                16: {
                    current.action: 20,
                    lower_winner.action: 12,
                    constant_survivor.action: 8,
                },
            },
            budgeted_ms_by_horizon={12: 2.0, 16: 2.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.observe_policy_timeout(snapshot(), 16)

        decision = solver.decide(snapshot())

        progressive = next(
            call for call in kernel.calls if call[0] == "progressive"
        )
        self.assertEqual(
            {candidate.action for candidate in progressive[4]},
            {
                current.action,
                lower_winner.action,
                constant_survivor.action,
            },
        )
        self.assertEqual(decision.action, current.action)

    def test_delivery_aware_local_micro_constrains_nominal_winner(self):
        clock = ManualClock()
        fragile = self.hard[0]
        robust_winner = self.hard[1]
        robust_other = self.hard[2]
        kernel = DeliveryReplanningKernel(
            clock,
            self.hard,
            delivery_scores={
                fragile.action: 0,
                robust_winner.action: 5,
                robust_other.action: 5,
            },
            terminal_scores_by_horizon={
                16: {
                    fragile.action: 20,
                    robust_winner.action: 12,
                    robust_other.action: 8,
                },
            },
            scores_by_horizon={
                16: {
                    fragile.action: 20,
                    robust_winner.action: 12,
                    robust_other.action: 8,
                },
            },
            budgeted_ms_by_horizon={16: 2.0},
            flexible_completed_horizon=16,
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, robust_winner.action)
        self.assertEqual(decision.effort_horizon, 16)
        self.assertIn(
            (
                "delivery_replanning",
                HARD_SAFETY_HORIZON,
                BASE_POLICY_HORIZON,
                tuple(candidate.action for candidate in self.hard),
            ),
            kernel.calls,
        )

    def test_deeper_continuation_ranks_inside_delivery_viability(self):
        clock = ManualClock()
        local_winner = self.hard[0]
        deep_winner = self.hard[1]
        other = self.hard[2]
        kernel = DeliveryReplanningKernel(
            clock,
            self.hard,
            delivery_scores={
                local_winner.action: 5,
                deep_winner.action: 3,
                other.action: 1,
            },
            terminal_scores_by_horizon={
                16: {
                    local_winner.action: 8,
                    deep_winner.action: 20,
                    other.action: 4,
                },
            },
            scores_by_horizon={
                16: {
                    local_winner.action: 8,
                    deep_winner.action: 20,
                    other.action: 4,
                },
            },
            budgeted_ms_by_horizon={16: 2.0},
            flexible_completed_horizon=16,
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_winner.action)
        progressive = next(
            call for call in kernel.calls
            if call[0] == "terminal_progressive"
        )
        self.assertEqual(
            {candidate.action for candidate in progressive[3]},
            {candidate.action for candidate in self.hard},
        )

    def test_repeated_pickup_gate_rejects_nominal_reversal(self):
        clock = ManualClock()
        state = snapshot()
        stay = SafeAction(ACTIONS[0], 10.0, state.x, state.y)
        left = SafeAction(ACTIONS[3], 9.0, state.x, state.y)
        right = SafeAction(ACTIONS[4], 8.0, state.x, state.y)
        hard = (stay, left, right)

        class RepeatedPickupKernel(DeliveryReplanningKernel):
            def replanning_viability_budgeted(
                self,
                _state,
                candidates,
                _segment_length,
                _horizon,
                collision_margin,
                budget_ms,
            ):
                self.clock.advance_ms(min(1.0, budget_ms))
                return {
                    candidate.action: 1 for candidate in candidates
                }

            def delivery_segment_viability_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                minimum_horizon,
                maximum_horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "repeated_pickup",
                    minimum_horizon,
                    maximum_horizon,
                    tuple(candidate.action for candidate in candidates),
                ))
                self.clock.advance_ms(min(1.0, budget_ms))
                allowed = frozenset(
                    candidate.action for candidate in candidates
                )
                return (
                    maximum_horizon,
                    {
                        action: int(action in (stay.action, left.action))
                        for action in allowed
                    },
                    True,
                )

        kernel = RepeatedPickupKernel(
            clock,
            hard,
            delivery_scores={candidate.action: 1 for candidate in hard},
            terminal_scores_by_horizon={
                12: {
                    stay.action: 8,
                    left.action: 10,
                    right.action: 20,
                },
            },
            flexible_completed_horizon=12,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(state)

        self.assertEqual(decision.action, left.action)
        repeated = next(
            call for call in kernel.calls if call[0] == "repeated_pickup"
        )
        self.assertEqual(repeated[1:3], (12, 12))
        terminal = next(
            call for call in kernel.calls
            if call[0] == "terminal_progressive"
        )
        self.assertNotIn(right.action, {
            candidate.action for candidate in terminal[3]
        })
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_empty_repeated_pickup_rung_prunes_deeper_same_model(self):
        clock = ManualClock()
        state = snapshot()
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS[:3]
        )

        class EmptyRepeatedPickupKernel(DeliveryReplanningKernel):
            def replanning_viability_budgeted(
                self,
                _state,
                candidates,
                _segment_length,
                _horizon,
                collision_margin,
                budget_ms,
            ):
                self.clock.advance_ms(min(1.0, budget_ms))
                return {
                    candidate.action: 1 for candidate in candidates
                }

            def delivery_segment_viability_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                minimum_horizon,
                maximum_horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "repeated_pickup",
                    minimum_horizon,
                    maximum_horizon,
                    tuple(candidate.action for candidate in candidates),
                ))
                self.clock.advance_ms(min(1.0, budget_ms))
                return (
                    maximum_horizon,
                    {candidate.action: 0 for candidate in candidates},
                    True,
                )

        kernel = EmptyRepeatedPickupKernel(
            clock,
            hard,
            delivery_scores={candidate.action: 1 for candidate in hard},
            terminal_scores_by_horizon={
                12: {candidate.action: 1 for candidate in hard},
            },
            reachability_by_horizon={
                20: {candidate.action: 0 for candidate in hard},
            },
            flexible_completed_horizon=20,
        )
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.choose_limit = lambda *_args: 20

        decision = solver.decide(state)

        self.assertIsNotNone(decision.action)
        self.assertIn("repeated_pickup", [call[0] for call in kernel.calls])
        self.assertNotIn("progressive", [call[0] for call in kernel.calls])
        self.assertNotIn("policy", [call[0] for call in kernel.calls])
        self.assertEqual(
            solver.effort.next_decision_budget_cap_ms,
            SAME_FRAME_DECISION_BUDGET_MS,
        )

        leased = solver.decide(
            snapshot(frame=101),
            required_action=hard[0].action,
        )

        self.assertEqual(leased.reason, "ok")
        self.assertIsNone(solver.effort.decision_budget_cap_ms)
        self.assertEqual(
            solver.effort.next_decision_budget_cap_ms,
            SAME_FRAME_DECISION_BUDGET_MS,
        )

        kernel.calls.clear()
        solver.effort.continuation_extension_affordable = (
            lambda *_args: False
        )
        solver.decide(snapshot(frame=102))

        self.assertEqual(
            solver.effort.decision_budget_cap_ms,
            SAME_FRAME_DECISION_BUDGET_MS,
        )
        self.assertIn(
            "delivery_replanning",
            [call[0] for call in kernel.calls],
        )
        self.assertNotIn("prepare", [call[0] for call in kernel.calls])

    def test_admitted_deeper_rung_follows_complete_local_viability(self):
        clock = ManualClock()
        shallow_winner = self.hard[0]
        deep_winner = self.hard[1]

        class ViabilityFirstKernel(DeliveryReplanningKernel):
            def replanning_viability_budgeted(
                self,
                _state,
                candidates,
                segment_length,
                horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "delivery_viability",
                    segment_length,
                    horizon,
                    tuple(candidate.action for candidate in candidates),
                ))
                if budget_ms < 1.0:
                    self.clock.advance_ms(budget_ms)
                    return None
                self.clock.advance_ms(1.0)
                return {
                    candidate.action: 1 for candidate in candidates
                }

        kernel = ViabilityFirstKernel(
            clock,
            self.hard,
            delivery_scores={
                shallow_winner.action: 9,
                deep_winner.action: 3,
                self.hard[2].action: 1,
            },
            delivery_ms=100.0,
            terminal_scores_by_horizon={
                16: {
                    shallow_winner.action: 4,
                    deep_winner.action: 20,
                    self.hard[2].action: 2,
                },
            },
            scores_by_horizon={},
            flexible_completed_horizon=16,
        )
        solver = self.solver(kernel, clock)
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_winner.action)
        self.assertIn(
            "delivery_viability",
            [call[0] for call in kernel.calls],
        )
        self.assertNotIn(
            "delivery_replanning",
            [call[0] for call in kernel.calls],
        )
        self.assertEqual(decision.effort_horizon, 16)
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_each_promoted_local_rung_rechecks_delivery_viability(self):
        clock = ManualClock()
        state = snapshot()
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS[:3]
        )
        shallow = hard[0].action
        deep_robust = hard[1].action

        class DeepViabilityKernel(DeliveryReplanningKernel):
            def replanning_viability_budgeted(
                self,
                _state,
                candidates,
                _segment_length,
                _horizon,
                collision_margin,
                budget_ms,
            ):
                self.clock.advance_ms(min(1.0, budget_ms))
                return {
                    candidate.action: 1 for candidate in candidates
                }

            def delivery_segment_viability_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                minimum_horizon,
                maximum_horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "repeated_pickup",
                    minimum_horizon,
                    maximum_horizon,
                    tuple(candidate.action for candidate in candidates),
                ))
                self.clock.advance_ms(min(1.0, budget_ms))
                allowed = frozenset(
                    candidate.action for candidate in candidates
                )
                viable = (
                    frozenset((deep_robust,))
                    if maximum_horizon >= 20
                    else allowed
                )
                return (
                    maximum_horizon,
                    {
                        action: int(action in viable)
                        for action in allowed
                    },
                    True,
                )

        kernel = DeepViabilityKernel(
            clock,
            hard,
            delivery_scores={candidate.action: 1 for candidate in hard},
            terminal_scores_by_horizon={
                12: {
                    shallow: 20,
                    deep_robust: 10,
                    hard[2].action: 1,
                },
                16: {
                    shallow: 20,
                    deep_robust: 10,
                    hard[2].action: 1,
                },
                20: {
                    shallow: 100,
                    deep_robust: 10,
                    hard[2].action: 1,
                },
            },
            flexible_completed_horizon=20,
        )
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.choose_limit = lambda *_args: 20

        decision = solver.decide(state)

        self.assertEqual(decision.action, deep_robust)
        self.assertEqual(
            [
                call[1:3] for call in kernel.calls
                if call[0] == "repeated_pickup"
            ],
            [(12, 12), (16, 16), (20, 20)],
        )
        self.assertNotIn(
            ("terminal_progressive", 16, 20),
            [call[:3] for call in kernel.calls],
        )

        measured_kernel = DeepViabilityKernel(
            clock,
            hard,
            delivery_scores={candidate.action: 1 for candidate in hard},
            terminal_scores_by_horizon={
                12: {
                    shallow: 20,
                    deep_robust: 10,
                    hard[2].action: 1,
                },
                16: {
                    shallow: 20,
                    deep_robust: 10,
                    hard[2].action: 1,
                },
                20: {
                    shallow: 100,
                    deep_robust: 10,
                    hard[2].action: 1,
                },
            },
            flexible_completed_horizon=20,
        )
        measured_solver = self.solver(
            measured_kernel,
            clock,
            budget=100.0,
        )
        measured_solver.effort.choose_limit = lambda *_args: 20
        measured_solver.effort.projection_ms_per_work = 0.0

        measured = measured_solver.decide(state)

        self.assertEqual(measured.action, deep_robust)
        self.assertEqual(
            [
                call[1:3] for call in measured_kernel.calls
                if call[0] == "repeated_pickup"
            ],
            [(12, 12), (16, 16), (20, 20)],
        )
        measured_calls = [
            call[:3] for call in measured_kernel.calls
            if call[0] in {
                "prepare",
                "repeated_pickup",
                "terminal_progressive",
            }
        ]
        self.assertLess(
            measured_calls.index(("prepare", 12)),
            measured_calls.index(("terminal_progressive", 12, 12)),
        )
        self.assertLess(
            measured_calls.index(("terminal_progressive", 12, 12)),
            measured_calls.index(("prepare", 20)),
        )
        self.assertLess(
            measured_calls.index(("terminal_progressive", 12, 12)),
            measured_calls.index(("repeated_pickup", 16, 16)),
        )

        class BudgetConsumingGateKernel(DeepViabilityKernel):
            def delivery_segment_viability_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                minimum_horizon,
                maximum_horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "repeated_pickup",
                    minimum_horizon,
                    maximum_horizon,
                    tuple(candidate.action for candidate in candidates),
                    budget_ms,
                ))
                self.clock.advance_ms(budget_ms)
                return (
                    maximum_horizon,
                    {candidate.action: 1 for candidate in candidates},
                    True,
                )

        reserved_clock = ManualClock()
        reserved_kernel = BudgetConsumingGateKernel(
            reserved_clock,
            hard,
            delivery_scores={candidate.action: 1 for candidate in hard},
            terminal_scores_by_horizon={
                12: {
                    shallow: 1,
                    deep_robust: 20,
                    hard[2].action: 2,
                },
            },
            flexible_completed_horizon=12,
        )
        reserved_solver = self.solver(
            reserved_kernel,
            reserved_clock,
        )
        reserved_solver.effort.choose_limit = lambda *_args: 20
        reserved_solver.effort.projection_ms_per_work = 0.0

        reserved = reserved_solver.decide(state)

        self.assertEqual(reserved.action, deep_robust)
        self.assertIn(
            ("terminal_progressive", 12, 12),
            [call[:3] for call in reserved_kernel.calls],
        )
        repeated_call = next(
            call for call in reserved_kernel.calls
            if call[0] == "repeated_pickup"
        )
        self.assertLess(repeated_call[4], 5.0)

    def test_constrained_publication_budget_keeps_exact_local_ranking(self):
        clock = ManualClock()
        local_winner = self.hard[1]

        class ConstrainedKernel(DeliveryReplanningKernel):
            def replanning_viability_budgeted(
                self,
                _state,
                candidates,
                segment_length,
                horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append((
                    "delivery_viability",
                    segment_length,
                    horizon,
                    tuple(candidate.action for candidate in candidates),
                ))
                self.clock.advance_ms(min(1.0, budget_ms))
                return {
                    candidate.action: 1 for candidate in candidates
                }

            def prepare(self, _state, horizon):
                self.calls.append(("prepare", horizon))
                self.clock.advance_ms(4.0)

        kernel = ConstrainedKernel(
            clock,
            self.hard,
            delivery_scores={
                self.hard[0].action: 2,
                local_winner.action: 7,
                self.hard[2].action: 1,
            },
            delivery_ms=2.0,
            terminal_scores_by_horizon={},
            scores_by_horizon={},
        )
        solver = self.solver(kernel, clock)
        solver.effort.publication_scale = 0.5
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, local_winner.action)
        self.assertIn(
            "delivery_replanning",
            [call[0] for call in kernel.calls],
        )
        self.assertNotIn(
            "delivery_viability",
            [call[0] for call in kernel.calls],
        )
        self.assertNotIn(
            "prepare",
            [call[0] for call in kernel.calls],
        )

    def test_incomplete_local_robustness_preserves_viable_input(self):
        clock = ManualClock()
        kernel = DeliveryReplanningKernel(
            clock,
            self.hard,
            delivery_scores={
                candidate.action: 1 for candidate in self.hard
            },
            delivery_robustness_complete=False,
            terminal_scores_by_horizon={},
            scores_by_horizon={},
        )
        solver = self.solver(kernel, clock)
        solver.effort.publication_scale = 0.5
        solver.effort.choose_limit = (
            lambda *_args: HARD_SAFETY_HORIZON
        )

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, self.hard[0].action)
        self.assertEqual(decision.effort_horizon, BASE_POLICY_HORIZON)
        self.assertIn(
            "delivery_replanning",
            [call[0] for call in kernel.calls],
        )
        self.assertNotIn(
            "prepare",
            [call[0] for call in kernel.calls],
        )

    def test_constrained_budget_uses_measured_residual_for_next_rung(self):
        clock = ManualClock()
        local_winner = self.hard[0]
        deep_winner = self.hard[1]
        kernel = DeliveryReplanningKernel(
            clock,
            self.hard,
            delivery_scores={
                local_winner.action: 7,
                deep_winner.action: 3,
                self.hard[2].action: 1,
            },
            delivery_ms=1.0,
            terminal_scores_by_horizon={
                12: {
                    local_winner.action: 3,
                    deep_winner.action: 9,
                    self.hard[2].action: 1,
                },
            },
            scores_by_horizon={},
            flexible_completed_horizon=12,
        )
        solver = self.solver(kernel, clock)
        solver.effort.publication_scale = 0.5
        solver.effort.projection_ms_per_work = 0.0
        solver.effort.projection_frame = 100
        solver.effort.policy_rate_by_horizon[12] = 0.0
        solver.effort.policy_frame_by_horizon[12] = 100
        solver.effort.choose_limit = lambda *_args: 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, deep_winner.action)
        self.assertIn(("prepare", 12), kernel.calls)
        self.assertIn(
            (12, 12),
            [
                call[1:3] for call in kernel.calls
                if call[0] == "terminal_progressive"
            ],
        )
        self.assertNotIn(("prepare", 16), kernel.calls)
        self.assertLessEqual(clock.seconds * 1000.0, 6.25)

    def test_constrained_next_rung_charges_fresh_soft_projection(self):
        controller = EffortController(6.25)
        state = snapshot()
        controller.projection_ms_per_work = 4.0 / (
            controller.projection_work(state, 12)
        )
        controller.projection_frame = state.frame
        controller.policy_rate_by_horizon[12] = 0.0
        controller.policy_frame_by_horizon[12] = state.frame

        self.assertFalse(controller.continuation_extension_affordable(
            state,
            3,
            8,
            12,
            2.0,
        ))

    def test_local_micro_uses_residual_budget_when_ladder_is_closed(self):
        for robustness_complete in (False, True):
            with self.subTest(
                robustness_complete=robustness_complete,
            ):
                clock = ManualClock()
                fragile = self.hard[0]
                robust = self.hard[1]
                kernel = DeliveryReplanningKernel(
                    clock,
                    self.hard,
                    delivery_scores={
                        fragile.action: 0,
                        robust.action: 3,
                        self.hard[2].action: 5,
                    },
                    delivery_robustness_complete=robustness_complete,
                    terminal_scores_by_horizon={},
                    scores_by_horizon={},
                )
                solver = self.solver(kernel, clock)
                solver.effort.choose_limit = (
                    lambda *_args: HARD_SAFETY_HORIZON
                )

                decision = solver.decide(snapshot())

                self.assertEqual(
                    decision.action,
                    (
                        self.hard[2].action
                        if robustness_complete
                        else robust.action
                    ),
                )
                self.assertEqual(
                    decision.effort_horizon,
                    BASE_POLICY_HORIZON,
                )
                self.assertIn(
                    "delivery_replanning",
                    [call[0] for call in kernel.calls],
                )
                self.assertIn(
                    "terminal_progressive",
                    [call[0] for call in kernel.calls],
                )
                self.assertIn(
                    "prepare",
                    [call[0] for call in kernel.calls],
                )

    def test_zero_delivery_continuation_keeps_nominal_fallback(self):
        clock = ManualClock()
        nominal_other = self.hard[0]
        turn_capable = self.hard[1]
        kernel = DeliveryReplanningKernel(
            clock,
            self.hard,
            delivery_scores={
                candidate.action: 0 for candidate in self.hard
            },
            terminal_scores_by_horizon={
                16: {
                    nominal_other.action: 8,
                    turn_capable.action: 20,
                    self.hard[2].action: 4,
                },
            },
            scores_by_horizon={
                16: {
                    nominal_other.action: 8,
                    turn_capable.action: 20,
                    self.hard[2].action: 4,
                },
            },
            budgeted_ms_by_horizon={16: 2.0},
            flexible_completed_horizon=16,
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, turn_capable.action)
        self.assertEqual(decision.effort_horizon, 16)

    def test_empty_constant_frontier_cannot_shorten_flexible_candidates(self):
        clock = ManualClock()
        current = self.hard[0]
        lower_winner = self.hard[1]
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: (), 16: ()},
            scores_by_horizon={
                8: {
                    current.action: 2,
                    lower_winner.action: 9,
                    self.hard[2].action: 1,
                },
                16: {
                    current.action: 12,
                    lower_winner.action: 8,
                    self.hard[2].action: 99,
                },
            },
            budgeted_ms_by_horizon={16: 2.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        decision = solver.decide(snapshot())

        progressive = next(
            call for call in kernel.calls if call[0] == "progressive"
        )
        self.assertEqual(
            {candidate.action for candidate in progressive[4]},
            {candidate.action for candidate in self.hard},
        )
        self.assertEqual(decision.action, self.hard[2].action)

    def test_partial_progressive_rung_is_stable_on_next_frame(self):
        clock = ManualClock()
        base_action = self.hard[0].action
        lower_action = self.hard[1].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: ()},
            scores_by_horizon={
                8: {
                    base_action: 5,
                    lower_action: 3,
                    self.hard[2].action: 1,
                },
                12: {
                    base_action: 2,
                    lower_action: 8,
                    self.hard[2].action: 1,
                },
                16: {
                    base_action: 1,
                    lower_action: 2,
                    self.hard[2].action: 10,
                },
            },
            budgeted_ms_by_horizon={12: 2.0, 16: 20.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        first = solver.decide(snapshot())
        kernel.calls.clear()
        second = solver.decide(snapshot(frame=101))

        self.assertEqual(first.action, lower_action)
        self.assertEqual(first.effort_horizon, 12)
        self.assertEqual(second.action, lower_action)
        self.assertEqual(second.effort_horizon, 12)
        self.assertEqual(
            [call[0] for call in kernel.calls].count("progressive"),
            1,
        )

    def test_newly_affordable_progressive_rung_publishes_next_frame(self):
        clock = ManualClock()
        base_action = self.hard[0].action
        lower_action = self.hard[1].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: ()},
            scores_by_horizon={
                8: {
                    base_action: 5,
                    lower_action: 3,
                    self.hard[2].action: 1,
                },
                12: {
                    base_action: 2,
                    lower_action: 8,
                    self.hard[2].action: 1,
                },
                16: {
                    base_action: 1,
                    lower_action: 2,
                    self.hard[2].action: 10,
                },
            },
            budgeted_ms_by_horizon={12: 20.0, 16: 20.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        state = snapshot()
        solver.effort.policy_rate_by_horizon[12] = 100.0 / (
            solver.effort.rollout_work(state, len(self.hard), 12)
        )
        solver.effort.policy_frame_by_horizon[12] = 0

        first = solver.decide(state)
        kernel.budgeted_ms_by_horizon[12] = 2.0
        kernel.calls.clear()
        next_state = snapshot(frame=101)
        self.assertFalse(
            solver.effort.policy_affordable(
                next_state,
                len(self.hard),
                12,
                2.0,
            )
        )
        second_started_ms = clock.seconds * 1000.0

        second = solver.decide(next_state)

        self.assertEqual(first.action, base_action)
        self.assertEqual(first.effort_horizon, 8)
        self.assertEqual(second.action, lower_action)
        self.assertEqual(second.effort_horizon, 12)
        self.assertEqual(
            [call[0] for call in kernel.calls].count("progressive"),
            1,
        )
        self.assertNotIn("policy", [call[0] for call in kernel.calls])
        self.assertLessEqual(
            clock.seconds * 1000.0 - second_started_ms,
            12.5,
        )

    def test_progressive_deadline_preserves_completed_lower_rung(self):
        clock = ManualClock()
        fallback_action = self.hard[1].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: ()},
            scores_by_horizon={
                8: {
                    self.hard[0].action: 5,
                    fallback_action: 3,
                    self.hard[2].action: 1,
                },
                12: {
                    self.hard[0].action: 2,
                    fallback_action: 8,
                    self.hard[2].action: 1,
                },
                16: {
                    self.hard[0].action: 1,
                    fallback_action: 2,
                    self.hard[2].action: 10,
                },
            },
            budgeted_ms_by_horizon={12: 2.0, 16: 20.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.observe_policy(snapshot(), len(self.hard), 16, 2.0)

        decision = solver.decide(snapshot())

        self.assertEqual(decision.action, fallback_action)
        self.assertEqual(decision.effort_horizon, 12)
        progressive = next(
            call for call in kernel.calls if call[0] == "progressive"
        )
        self.assertNotIn("policy", [call[0] for call in kernel.calls])
        self.assertEqual(progressive[1:3], (8, 20))
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_progressive_reachability_never_uses_shallow_shortlist(self):
        clock = ManualClock()
        state = snapshot()
        hard = tuple(
            SafeAction(action, 10.0 - index, state.x, state.y)
            for index, action in enumerate(ACTIONS[:6])
        )
        retained = hard[0].action
        alternate = hard[1].action
        shallow = hard[2].action
        kernel = BudgetedProgressiveKernel(
            clock,
            hard,
            frontiers={16: (hard[2],)},
            scores_by_horizon={
                8: {
                    retained: 8,
                    alternate: 8,
                    shallow: 8,
                    **{candidate.action: 1 for candidate in hard[3:]},
                },
                12: {
                    retained: 2,
                    alternate: 3,
                    shallow: 10,
                    **{candidate.action: 1 for candidate in hard[3:]},
                },
                16: {
                    retained: 20,
                    alternate: 15,
                    shallow: 10,
                    **{candidate.action: 1 for candidate in hard[3:]},
                },
            },
            budgeted_ms_by_horizon={12: 1.0, 16: 4.0},
        )
        solver = self.solver(kernel, clock)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.observe_policy(state, len(hard), 16, 6.0)

        decision = solver.decide(state)

        progressive = next(
            call for call in kernel.calls if call[0] == "progressive"
        )
        self.assertEqual(progressive[4], hard)
        self.assertEqual(decision.action, retained)
        self.assertEqual(decision.effort_horizon, 16)

    @unittest.skipUnless(os.name == "nt", "native policy needs Windows")
    def test_native_budgeted_constant_is_complete_or_discarded(self):
        state = snapshot()
        kernel = NativeSafetyKernel()
        hard = kernel.certify(
            state,
            HARD_SAFETY_HORIZON,
            collision_margin=0.35,
        )
        actions = tuple(candidate.action for candidate in hard)
        expected = kernel.certify_selected(
            state,
            16,
            actions,
            collision_margin=0.35,
        )

        completed = kernel.certify_selected_budgeted(
            state,
            16,
            actions,
            collision_margin=0.35,
            budget_ms=1000.0,
        )
        expired = kernel.certify_selected_budgeted(
            state,
            16,
            actions,
            collision_margin=0.35,
            budget_ms=0.000001,
        )

        self.assertEqual(completed, expected)
        self.assertIsNone(expired)

    @unittest.skipUnless(os.name == "nt", "native policy needs Windows")
    def test_native_budgeted_policy_is_complete_or_discarded(self):
        state = snapshot()
        kernel = NativeSafetyKernel()
        candidates = kernel.certify(
            state,
            HARD_SAFETY_HORIZON,
            collision_margin=0.35,
        )
        expected = kernel.nominal_policy_counts(
            state,
            candidates,
            HARD_SAFETY_HORIZON,
            16,
            collision_margin=0.35,
        )

        completed = kernel.nominal_policy_counts_budgeted(
            state,
            candidates,
            HARD_SAFETY_HORIZON,
            16,
            collision_margin=0.35,
            budget_ms=1000.0,
        )
        expired = kernel.nominal_policy_counts_budgeted(
            state,
            candidates,
            HARD_SAFETY_HORIZON,
            16,
            collision_margin=0.35,
            budget_ms=0.000001,
        )

        self.assertEqual(completed, expected)
        self.assertIsNone(expired)

    @unittest.skipUnless(os.name == "nt", "native policy needs Windows")
    def test_native_macro_tail_uses_full_control_alphabet_and_discards_timeout(self):
        state = snapshot(x=192.0, y=224.0)
        kernel = NativeSafetyKernel()
        candidates = kernel.certify(
            state,
            HARD_SAFETY_HORIZON,
            collision_margin=0.35,
        )
        completed = kernel.macro_tail_scores_budgeted(
            state,
            candidates,
            HARD_SAFETY_HORIZON,
            8,
            collision_margin=0.35,
            budget_ms=1000.0,
        )
        expired = kernel.macro_tail_scores_budgeted(
            state,
            candidates,
            HARD_SAFETY_HORIZON,
            8,
            collision_margin=0.35,
            budget_ms=0.000001,
        )

        self.assertGreater(max(completed.values()), len(ACTIONS))
        self.assertIsNone(expired)

    def test_unaffordable_policy_rung_does_not_skip_to_deeper_search(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(
            clock,
            self.hard,
            frontiers={12: self.hard[:-1]},
        )
        solver = self.solver(kernel, clock, budget=10.0)
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 12
        state = snapshot()
        solver.effort.policy_rate_by_horizon[8] = 100.0 / (
            solver.effort.rollout_work(state, len(self.hard), 8)
        )
        solver.effort.policy_frame_by_horizon[8] = state.frame
        solver.effort.policy_rate_by_horizon[12] = 0.0
        solver.effort.policy_frame_by_horizon[12] = state.frame

        solver.decide(state)

        self.assertNotIn("policy", [call[0] for call in kernel.calls])

    def test_stale_nominal_cost_does_not_block_progressive_rung(self):
        clock = ManualClock()
        expected = self.hard[1].action
        kernel = BudgetedProgressiveKernel(
            clock,
            self.hard,
            scores_by_horizon={
                8: {
                    self.hard[0].action: 2,
                    expected: 9,
                    self.hard[2].action: 1,
                },
            },
            budgeted_ms_by_horizon={8: 1.0},
        )
        solver = self.solver(kernel, clock)
        state = snapshot()
        solver.effort.rollout_ms_per_work = 10.0 / (
            solver.effort.rollout_work(state, len(self.hard), 8)
        )
        solver.effort.rollout_frame = state.frame
        solver.effort.last_limit = 8
        solver.effort.policy_rate_by_horizon[8] = 100.0 / (
            solver.effort.rollout_work(state, len(self.hard), 8)
        )
        solver.effort.policy_frame_by_horizon[8] = state.frame

        decision = solver.decide(state)

        call_names = [call[0] for call in kernel.calls]
        self.assertNotIn("budgeted_policy", call_names)
        self.assertIn("progressive", call_names)
        self.assertNotIn("policy", [call[0] for call in kernel.calls])
        self.assertEqual(decision.action, expected)
        self.assertEqual(decision.effort_horizon, 8)
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_spent_hard_deadline_skips_all_soft_work(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(clock, self.hard, hard_ms=20.0)
        solver = self.solver(kernel, clock, budget=12.5)

        decision = solver.decide(snapshot())

        self.assertEqual(decision.effort_horizon, HARD_SAFETY_HORIZON)
        self.assertEqual([call[0] for call in kernel.calls], ["hard"])

    def test_first_soft_probe_uses_measured_hard_cost(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(clock, self.hard, hard_ms=6.0)
        solver = self.solver(kernel, clock, budget=10.0)

        decision = solver.decide(snapshot())

        self.assertEqual(decision.effort_horizon, HARD_SAFETY_HORIZON)
        self.assertEqual([call[0] for call in kernel.calls], ["hard"])

    def test_cost_estimate_uses_continuous_work_not_scene_bands(self):
        controller = EffortController(12.5)
        controller.rollout_ms_per_work = 0.0005
        sparse = snapshot()
        controller.rollout_frame = sparse.frame
        dense = snapshot(
            bullets=tuple(
                Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
                for _ in range(200)
            )
        )

        controller.last_limit = EFFORT_HORIZONS[-1]
        sparse_limit = controller.choose_limit(sparse, 9, 1.0)
        controller.last_limit = EFFORT_HORIZONS[-1]
        dense_limit = controller.choose_limit(dense, 9, 1.0)

        self.assertGreater(sparse_limit, dense_limit)

    def test_compute_ladder_has_promotion_hysteresis(self):
        controller = EffortController(12.0)
        state = snapshot()
        h6_work = controller.rollout_work(state, 3, 6)
        controller.rollout_ms_per_work = 9.5 / h6_work
        controller.rollout_frame = state.frame

        controller.last_limit = HARD_SAFETY_HORIZON
        promoted = controller.choose_limit(state, 3, 2.0)
        controller.last_limit = 6
        retained = controller.choose_limit(state, 3, 2.0)

        self.assertEqual(promoted, HARD_SAFETY_HORIZON)
        self.assertEqual(retained, 6)

    def test_promotion_can_cross_multiple_affordable_rungs(self):
        controller = EffortController(12.5)
        state = snapshot()
        controller.rollout_ms_per_work = 6.0 / controller.rollout_work(
            state, 3, 8
        )
        controller.rollout_frame = state.frame
        controller.last_limit = HARD_SAFETY_HORIZON

        promoted = controller.choose_limit(state, 3, 3.0)

        self.assertEqual(promoted, 8)

    def test_stale_rollout_cost_yields_to_current_hard_measurement(self):
        controller = EffortController(10.0)
        state = snapshot(frame=300)
        h6_work = controller.rollout_work(state, 3, 6)
        controller.rollout_ms_per_work = 20.0 / h6_work
        controller.rollout_frame = 0

        self.assertEqual(controller.choose_limit(state, 3, 1.0), 20)

    def test_fresh_rollout_cost_remains_authoritative(self):
        controller = EffortController(10.0)
        state = snapshot(frame=300)
        h6_work = controller.rollout_work(state, 3, 6)
        controller.rollout_ms_per_work = 20.0 / h6_work
        controller.rollout_frame = state.frame

        self.assertEqual(
            controller.choose_limit(state, 3, 1.0),
            HARD_SAFETY_HORIZON,
        )

    def test_repeated_current_cost_reopens_first_policy_rung(self):
        controller = EffortController(10.0)
        state = snapshot(frame=300)
        h6_work = controller.rollout_work(state, 3, 6)
        controller.rollout_ms_per_work = 20.0 / h6_work
        controller.rollout_frame = state.frame

        first = controller.choose_limit(state, 3, 1.0)
        second = controller.choose_limit(
            snapshot(frame=301),
            3,
            1.0,
        )

        self.assertEqual(first, HARD_SAFETY_HORIZON)
        self.assertEqual(second, 8)

    def test_measured_projection_reopens_only_an_affordable_base_rung(self):
        controller = EffortController(12.5)
        bullets = tuple(
            Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
            for _ in range(180)
        )
        state = snapshot(bullets=bullets)
        controller.rollout_ms_per_work = 20.0 / controller.rollout_work(
            state,
            18,
            BASE_POLICY_HORIZON,
        )
        controller.rollout_frame = state.frame
        controller.observe_projection(
            state,
            BASE_POLICY_HORIZON,
            3.4,
        )

        first = controller.choose_limit(state, 18, 4.5)
        second = controller.choose_limit(
            replace(state, frame=state.frame + 1),
            18,
            4.5,
        )
        dense = replace(
            state,
            frame=state.frame + 2,
            bullets=bullets * 4,
        )
        rejected_dense = controller.choose_limit(dense, 18, 9.9)

        self.assertEqual(first, HARD_SAFETY_HORIZON)
        self.assertEqual(second, BASE_POLICY_HORIZON)
        self.assertEqual(rejected_dense, HARD_SAFETY_HORIZON)

    def test_stale_expensive_projection_gets_one_base_remeasurement(self):
        controller = EffortController(12.5)
        state = snapshot(frame=300)
        controller.rollout_ms_per_work = 20.0 / controller.rollout_work(
            state,
            18,
            BASE_POLICY_HORIZON,
        )
        controller.rollout_frame = state.frame
        controller.observe_projection(
            replace(state, frame=0),
            BASE_POLICY_HORIZON,
            20.0,
        )

        probe = controller.choose_limit(state, 18, 8.0)
        controller.observe_projection(
            state,
            BASE_POLICY_HORIZON,
            20.0,
        )
        fresh = controller.choose_limit(
            replace(state, frame=301),
            18,
            8.0,
        )

        self.assertEqual(probe, BASE_POLICY_HORIZON)
        self.assertEqual(fresh, HARD_SAFETY_HORIZON)

    def test_stale_projection_remeasurement_replaces_expired_rate(self):
        controller = EffortController(12.5)
        old_state = snapshot(frame=0)
        current = snapshot(frame=300)
        controller.observe_projection(
            old_state,
            BASE_POLICY_HORIZON,
            20.0,
        )

        controller.observe_projection(
            current,
            BASE_POLICY_HORIZON,
            1.0,
        )

        estimate = (
            controller.projection_ms_per_work
            * controller.projection_work(current, BASE_POLICY_HORIZON)
        )
        self.assertAlmostEqual(estimate, 1.0)
        self.assertEqual(controller.projection_frame, current.frame)

    def test_stale_projection_probe_preserves_publication_guard(self):
        controller = EffortController(12.5)
        state = snapshot(frame=300)
        controller.rollout_ms_per_work = 20.0 / controller.rollout_work(
            state,
            18,
            BASE_POLICY_HORIZON,
        )
        controller.rollout_frame = state.frame
        controller.observe_projection(
            replace(state, frame=0),
            BASE_POLICY_HORIZON,
            20.0,
        )

        limit = controller.choose_limit(
            state,
            18,
            controller.budget_ms() - TERMINAL_DEADLINE_GUARD_MS,
        )

        self.assertEqual(limit, HARD_SAFETY_HORIZON)

    def test_stale_deep_policy_cost_yields_to_fresh_lower_rung(self):
        controller = EffortController(10.0)
        state = snapshot(frame=300)
        h12_work = controller.rollout_work(state, 3, 12)
        controller.policy_rate_by_horizon[8] = 1.0 / (
            controller.rollout_work(state, 3, 8)
        )
        controller.policy_frame_by_horizon[8] = state.frame
        controller.policy_rate_by_horizon[12] = 20.0 / h12_work
        controller.policy_frame_by_horizon[12] = 0

        self.assertTrue(controller.policy_affordable(state, 3, 12, 2.0))

    def test_fresh_deep_policy_cost_remains_authoritative(self):
        controller = EffortController(10.0)
        state = snapshot(frame=300)
        h12_work = controller.rollout_work(state, 3, 12)
        controller.policy_rate_by_horizon[8] = 1.0 / (
            controller.rollout_work(state, 3, 8)
        )
        controller.policy_frame_by_horizon[8] = state.frame
        controller.policy_rate_by_horizon[12] = 20.0 / h12_work
        controller.policy_frame_by_horizon[12] = state.frame

        self.assertFalse(controller.policy_affordable(state, 3, 12, 2.0))

    def test_stale_cost_does_not_pollute_fresh_deep_measurement(self):
        controller = EffortController(10.0)
        state = snapshot(frame=300)
        h8_work = controller.rollout_work(state, 3, 8)
        h12_work = controller.rollout_work(state, 3, 12)
        controller.policy_rate_by_horizon[8] = 1.0 / h8_work
        controller.policy_frame_by_horizon[8] = state.frame
        controller.policy_rate_by_horizon[12] = 20.0 / h12_work
        controller.policy_frame_by_horizon[12] = 0

        controller.observe_policy(state, 3, 12, 4.0)

        self.assertLess(
            controller.policy_rate_by_horizon[12] * h12_work,
            8.0,
        )
        self.assertEqual(controller.policy_frame_by_horizon[12], state.frame)

    def test_policy_timeout_evidence_expires_and_completion_replaces_it(self):
        controller = EffortController(10.0)
        state = snapshot(frame=300)

        controller.observe_policy_timeout(state, 16)

        self.assertTrue(controller.policy_probe_evidence_fresh(state, 16))
        self.assertTrue(controller.policy_probe_timeout_fresh(state, 16))
        self.assertFalse(
            controller.policy_probe_evidence_fresh(
                snapshot(frame=361),
                16,
            )
        )
        self.assertFalse(
            controller.policy_probe_timeout_fresh(
                snapshot(frame=361),
                16,
            )
        )

        controller.observe_policy(snapshot(frame=362), 3, 16, 2.0)

        self.assertFalse(
            controller.policy_probe_timeout_fresh(
                snapshot(frame=362),
                16,
            )
        )
        self.assertNotIn(
            16,
            controller.policy_probe_timeout_frame_by_horizon,
        )

    def test_stale_publication_reduces_next_soft_budget(self):
        controller = EffortController(12.5)
        before = controller.budget_ms()
        controller.last_limit = EFFORT_HORIZONS[-1]

        controller.observe_publication(True)

        self.assertLess(controller.budget_ms(), before)
        self.assertEqual(controller.last_limit, HARD_SAFETY_HORIZON)

    def test_two_fresh_publications_release_transient_budget_penalty(self):
        controller = EffortController(12.5)
        state = snapshot(
            bullets=tuple(
                Bullet(20.0, 20.0, 0.0, 0.0, 2.0, 2.0, 1)
                for _ in range(300)
            )
        )
        controller.rollout_ms_per_work = 20.0 / controller.rollout_work(
            state,
            3,
            BASE_POLICY_HORIZON,
        )
        controller.rollout_frame = state.frame
        controller.last_limit = EFFORT_HORIZONS[-1]

        controller.observe_publication(True)
        reduced = controller.budget_ms()
        first = controller.choose_limit(state, 3, 2.4)
        controller.observe_publication(False)
        second = controller.choose_limit(
            replace(state, frame=101),
            3,
            2.4,
        )
        controller.observe_publication(False)
        restored = controller.budget_ms()
        third = controller.choose_limit(
            replace(state, frame=102),
            3,
            2.4,
        )
        fourth = controller.choose_limit(
            replace(state, frame=103),
            3,
            2.4,
        )

        self.assertLess(reduced, 12.5)
        self.assertEqual(restored, 12.5)
        self.assertEqual(first, HARD_SAFETY_HORIZON)
        self.assertEqual(second, HARD_SAFETY_HORIZON)
        self.assertEqual(third, HARD_SAFETY_HORIZON)
        self.assertEqual(fourth, BASE_POLICY_HORIZON)

    def test_commitment_requires_a_fresh_preferred_certificate(self):
        ranker = ProposalRanker()
        preferred = frozenset((self.hard[-1].action,))

        first = ranker.choose(snapshot(), self.hard, preferred)
        second = ranker.choose(
            replace(snapshot(), frame=101),
            self.hard,
        )

        self.assertEqual(first.action, self.hard[-1].action)
        self.assertEqual(second.action, self.hard[0].action)

    def test_no_fresh_proposal_retains_hard_certified_current_input(self):
        state = snapshot(input_mask=0x04)
        current = ACTIONS[0]
        larger_clearance = ACTIONS[1]
        candidates = (
            SafeAction(current, 1.0, state.x, state.y),
            SafeAction(larger_clearance, 100.0, state.x, state.y),
        )

        chosen = ProposalRanker().choose(state, candidates)

        self.assertEqual(chosen.action, current)

    def test_route_reference_only_breaks_ties_inside_allowed_actions(self):
        stay = CONTROL_ACTIONS[0]
        up = CONTROL_ACTIONS[1]
        down = CONTROL_ACTIONS[2]
        left = CONTROL_ACTIONS[3]
        candidates = (
            SafeAction(stay, 10.0, 125.0, 118.0),
            SafeAction(up, 10.0, 125.0, 116.0),
            SafeAction(down, 10.0, 125.0, 120.0),
            SafeAction(left, 10.0, 123.0, 118.0),
        )

        unrestricted = preferred_route_reference_actions(
            candidates,
            frozenset(candidate.action for candidate in candidates),
        )
        stronger_survival = preferred_route_reference_actions(
            candidates,
            frozenset((stay, up)),
        )

        self.assertEqual(unrestricted, frozenset((down,)))
        self.assertEqual(stronger_survival, frozenset((stay,)))

    def test_expired_directional_proposal_releases_when_neutral_is_hard(self):
        ranker = ProposalRanker()
        right_fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "right_fast"
        )
        stay_fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "stay_fast"
        )
        candidates = (
            SafeAction(right_fast, 10.0, 168.0, 230.0),
            SafeAction(stay_fast, 9.0, 152.0, 230.0),
        )

        proposed = ranker.choose(
            snapshot(input_mask=0x00),
            candidates,
            frozenset((right_fast,)),
            commitment_frames=4,
        )
        held = ranker.choose(
            snapshot(frame=102, input_mask=0x80),
            candidates,
        )
        released = ranker.choose(
            snapshot(frame=104, input_mask=0x80),
            candidates,
        )

        self.assertEqual(proposed.action, right_fast)
        self.assertEqual(held.action, right_fast)
        self.assertEqual(released.action, stay_fast)

    def test_expired_proposal_does_not_relax_hard_to_release_direction(self):
        ranker = ProposalRanker()
        right_fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "right_fast"
        )
        candidate = SafeAction(right_fast, 10.0, 168.0, 230.0)

        ranker.choose(
            snapshot(input_mask=0x00),
            (candidate,),
            frozenset((right_fast,)),
            commitment_frames=2,
        )
        held = ranker.choose(
            snapshot(frame=102, input_mask=0x80),
            (candidate,),
        )

        self.assertEqual(held.action, right_fast)

    def test_full_fresh_tie_direction_is_still_a_bounded_soft_proposal(self):
        ranker = ProposalRanker()
        stay_fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "stay_fast"
        )
        right_fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "right_fast"
        )
        candidates = (
            SafeAction(stay_fast, 10.0, 152.0, 230.0),
            SafeAction(right_fast, 10.0, 168.0, 230.0),
        )

        chosen = ranker.choose(
            snapshot(x=152.0, y=230.0, input_mask=0x00),
            candidates,
            frozenset((stay_fast, right_fast)),
            commitment_frames=4,
        )

        self.assertEqual(chosen.action, right_fast)
        self.assertEqual(ranker.committed_action, right_fast)
        self.assertEqual(ranker.commit_until_frame, 104)

    def test_equal_continuation_prefers_focused_correction_reserve(self):
        state = snapshot(input_mask=0x01)
        focused = next(
            action for action in CONTROL_ACTIONS
            if action.name == "left"
        )
        fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "left_fast"
        )
        candidates = (
            SafeAction(focused, 10.0, 180.0, state.y),
            SafeAction(fast, 10.0, 160.0, state.y),
        )

        chosen = ProposalRanker().choose(
            state,
            candidates,
            frozenset((focused, fast)),
        )

        self.assertEqual(chosen.action, focused)

    def test_fresh_preferred_commitment_renews_before_clearance_chatter(self):
        state = snapshot(input_mask=0x04)
        stay = next(
            action for action in CONTROL_ACTIONS
            if action.name == "stay"
        )
        left = next(
            action for action in CONTROL_ACTIONS
            if action.name == "left"
        )
        right = next(
            action for action in CONTROL_ACTIONS
            if action.name == "right"
        )
        preferred = frozenset((stay, left))
        ranker = ProposalRanker()

        first = ranker.choose(
            state,
            (
                SafeAction(stay, 33.0, 207.865, 428.426),
                SafeAction(left, 32.0, 205.865, 428.426),
                SafeAction(right, 100.0, 209.865, 428.426),
            ),
            preferred,
            commitment_frames=4,
        )
        renewed = ranker.choose(
            replace(state, frame=104),
            (
                SafeAction(stay, 31.966, 207.865, 428.426),
                SafeAction(left, 32.275, 205.865, 428.426),
                SafeAction(right, 100.0, 209.865, 428.426),
            ),
            preferred,
            commitment_frames=4,
        )

        self.assertEqual(first.action, stay)
        self.assertEqual(renewed.action, stay)
        self.assertEqual(ranker.commit_until_frame, 108)


if __name__ == "__main__":
    unittest.main()

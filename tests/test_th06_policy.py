import unittest
from dataclasses import replace

from th06.model import ACTIONS, Bullet, SafeAction, Snapshot
from th06.ranking import ProposalRanker
from th06.solver import (
    EFFORT_HORIZONS,
    HARD_SAFETY_HORIZON,
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

    def test_hard_authority_is_computed_before_soft_work(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(clock, self.hard)
        solver = self.solver(kernel, clock)

        decision = solver.decide(snapshot())

        self.assertEqual(kernel.calls[0][0], "hard")
        self.assertEqual(kernel.calls[1], ("prepare", EFFORT_HORIZONS[0]))
        self.assertEqual(decision.safe_actions, self.hard)

    def test_affordable_frontier_promotes_one_rung_per_decision(self):
        clock = ManualClock()
        kernel = ProgressiveKernel(clock, self.hard)
        solver = self.solver(kernel, clock, budget=100.0)
        solver.effort.rollout_ms_per_work = 0.0

        horizons = []
        for offset in range(4):
            decision = solver.decide(replace(snapshot(), frame=100 + offset))
            horizons.append(decision.effort_horizon)

        self.assertEqual(horizons, list(EFFORT_HORIZONS))

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

        self.assertEqual(decision.effort_horizon, 8)
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
            [8, 12],
        )
        self.assertEqual(decision.action, up)
        self.assertEqual(decision.effort_horizon, 12)

    def test_policy_rung_precedes_more_distant_constant_frontier(self):
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
        self.assertLess(calls.index(("policy", 8)), calls.index(("frontier", 12)))
        self.assertLess(calls.index(("frontier", 12)), calls.index(("policy", 12)))

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

        controller.last_limit = HARD_SAFETY_HORIZON
        promoted = controller.choose_limit(state, 3, 2.0)
        controller.last_limit = 6
        retained = controller.choose_limit(state, 3, 2.0)

        self.assertEqual(promoted, HARD_SAFETY_HORIZON)
        self.assertEqual(retained, 6)

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

    def test_stale_publication_reduces_next_soft_budget(self):
        controller = EffortController(12.5)
        before = controller.budget_ms()
        controller.last_limit = EFFORT_HORIZONS[-1]

        controller.observe_publication(True)

        self.assertLess(controller.budget_ms(), before)
        self.assertEqual(controller.last_limit, HARD_SAFETY_HORIZON)

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


if __name__ == "__main__":
    unittest.main()

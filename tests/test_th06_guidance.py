import os
import unittest
from dataclasses import replace

from counterexample_corpus import ACTION_BY_NAME, decode_snapshot, load_cases
from th06.guidance import (
    TerminalGuidance,
    preferred_target_actions,
    terminal_guidance_scores,
)
from th06.kernels.safety import NativeSafetyKernel
from th06.model import ACTIONS, SafeAction, Snapshot
from th06.safety import certify_actions
from th06.solver import Solver


def snapshot(**changes) -> Snapshot:
    values = dict(
        frame=100,
        stage=1,
        player_state=0,
        x=8.0,
        y=432.0,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2**0.5,
        focus_diagonal_speed=2**0.5,
        frame_multiplier=1.0,
        input_mask=0x14,
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

    def advance_ms(self, value: float) -> None:
        self.seconds += value / 1000.0


class GuidanceKernel:
    def __init__(self, clock: ManualClock, hard) -> None:
        self.clock = clock
        self.hard = hard
        self.calls = []

    def certify_selected_delivery_sets(
        self, _state, _horizon, _actions, collision_margin
    ):
        self.clock.advance_ms(0.1)
        return self.hard, self.hard

    def prepare(self, _state, horizon):
        self.calls.append(("prepare", horizon))

    def certify_selected(self, _state, horizon, actions, collision_margin):
        allowed = frozenset(actions)
        return tuple(item for item in self.hard if item.action in allowed)

    def nominal_policy_counts(
        self, _state, candidates, _segment_length, horizon, collision_margin
    ):
        self.calls.append(("policy", horizon))
        self.clock.advance_ms(0.2)
        return {
            item.action: 9 if item.action.name == "right" else 1
            for item in candidates
        }

    def terminal_guidance(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        target=None,
    ):
        self.calls.append(("target" if target else "acquire", horizon))
        self.clock.advance_ms(0.2)
        return {
            item.action: TerminalGuidance(
                terminal_count=(
                    2 if item.action.name == "right" else 1
                ),
                free_clearance=12.0,
                free_x=80.0,
                free_y=120.0,
                target_distance_squared=(
                    1.0 if item.action.name == "down_right" else 9.0
                ),
            )
            for item in candidates
        }


class ConstantFrontierKernel(GuidanceKernel):
    def certify_selected(self, _state, horizon, actions, collision_margin):
        allowed = frozenset(actions)
        candidates = tuple(
            item for item in self.hard if item.action in allowed
        )
        if horizon >= 8:
            return tuple(
                item for item in candidates if item.action.name == "right"
            )
        return candidates

    def nominal_policy_counts(
        self, _state, candidates, _segment_length, horizon, collision_margin
    ):
        self.calls.append(("policy", horizon))
        self.clock.advance_ms(0.2)
        return {item.action: 0 for item in candidates}

class TerminalGuidanceTests(unittest.TestCase):
    def replay_target_case(self, case, kernel=None):
        values = case["input"]
        source = decode_snapshot(values["acquisition_snapshot"])
        source_hard = (
            kernel.certify(source, 4, collision_margin=0.35)
            if kernel is not None
            else certify_actions(source, 4)
        )
        acquisition_action = ACTION_BY_NAME[values["acquisition_action"]]
        source_candidates = tuple(
            item for item in source_hard
            if item.action == acquisition_action
        )
        source_guidance = (
            kernel.terminal_guidance(
                source,
                source_candidates,
                values["segment_length"],
                values["acquisition_horizon"],
                collision_margin=0.35,
            )
            if kernel is not None
            else terminal_guidance_scores(
                source,
                source_candidates,
                values["segment_length"],
                values["acquisition_horizon"],
            )
        )
        acquired = source_guidance[acquisition_action]
        expected = case["expect"]
        self.assertEqual(
            acquired.terminal_count, expected["terminal_count"]
        )
        self.assertAlmostEqual(
            acquired.free_clearance,
            expected["free_clearance"],
            places=4,
        )
        self.assertAlmostEqual(
            acquired.free_x, expected["target"][0], places=4
        )
        self.assertAlmostEqual(
            acquired.free_y, expected["target"][1], places=4
        )

        tracking = decode_snapshot(values["tracking_snapshot"])
        tracking_hard = (
            kernel.certify(tracking, 4, collision_margin=0.35)
            if kernel is not None
            else certify_actions(tracking, 4)
        )
        target = (acquired.free_x, acquired.free_y)
        tracking_guidance = (
            kernel.terminal_guidance(
                tracking,
                tracking_hard,
                values["segment_length"],
                values["tracking_horizon"],
                collision_margin=0.35,
                target=target,
            )
            if kernel is not None
            else terminal_guidance_scores(
                tracking,
                tracking_hard,
                values["segment_length"],
                values["tracking_horizon"],
                target,
            )
        )
        preferred = preferred_target_actions(
            tracking_guidance,
            frozenset(item.action for item in tracking_hard),
        )
        if "tracking_terminal_count" in expected:
            self.assertEqual(
                max(
                    tracking_guidance[action].terminal_count
                    for action in preferred
                ),
                expected["tracking_terminal_count"],
            )
        best_distance = next(
            tracking_guidance[action].target_distance_squared
            for action in preferred
        )
        self.assertAlmostEqual(
            best_distance,
            expected["tracking_distance_squared"],
            places=3,
        )
        self.assertEqual(
            sorted(
                action.name for action in preferred
            ),
            sorted(expected["tracking_actions"]),
        )

    def test_reference_target_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "terminal_target_sequence"
        )
        self.assertTrue(cases, "terminal target corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_target_case(case)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_target_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "terminal_target_sequence"
        )
        self.assertTrue(cases, "terminal target corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_target_case(case, kernel)

    def test_empty_corner_target_is_inside_the_reachable_free_region(self):
        state = snapshot()
        hard = certify_actions(state, 4)

        guidance = terminal_guidance_scores(state, hard, 4, 8)
        best = max(item.free_clearance for item in guidance.values())
        value = next(
            item
            for item in guidance.values()
            if item.free_clearance == best
        )
        self.assertGreater(value.free_x, state.x)
        self.assertLess(value.free_y, state.y)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_matches_reference_terminal_values(self):
        state = snapshot()
        hard = certify_actions(state, 4)
        reference = terminal_guidance_scores(
            state, hard, 4, 8, target=(24.0, 416.0)
        )
        native = NativeSafetyKernel().terminal_guidance(
            state,
            hard,
            4,
            8,
            collision_margin=0.35,
            target=(24.0, 416.0),
        )

        self.assertEqual(reference.keys(), native.keys())
        for action in reference:
            with self.subTest(action=action.name):
                self.assertEqual(
                    reference[action].terminal_count,
                    native[action].terminal_count,
                )
                self.assertAlmostEqual(
                    reference[action].free_clearance,
                    native[action].free_clearance,
                    places=4,
                )
                self.assertAlmostEqual(
                    reference[action].target_distance_squared,
                    native[action].target_distance_squared,
                    places=3,
                )

    def test_unique_local_plan_acquires_then_tracks_one_target(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = GuidanceKernel(clock, hard)
        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 6

        proposed = solver.decide(state)
        self.assertEqual(proposed.action.name, "right")
        self.assertEqual(solver.pending_target_action.name, "right")

        acquired = solver.decide(
            replace(state, frame=101, input_mask=0x84)
        )
        self.assertEqual(acquired.action.name, "right")
        self.assertEqual(solver.guidance_target, (80.0, 120.0))
        self.assertIsNone(solver.pending_target_action)

        guided = solver.decide(
            replace(state, frame=102, input_mask=0x84)
        )
        self.assertEqual(guided.action.name, "right")
        self.assertIn("acquire", {call[0] for call in kernel.calls})
        self.assertIn("target", {call[0] for call in kernel.calls})

    def test_pending_target_cannot_acquire_before_native_pickup(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = GuidanceKernel(clock, hard)
        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 8
        solver.pending_target_action = next(
            action for action in ACTIONS if action.name == "right"
        )
        solver.pending_target_horizon = 8

        solver.decide(state)

        self.assertNotIn("acquire", {call[0] for call in kernel.calls})
        self.assertIsNone(solver.guidance_target)

    def test_target_deadline_does_not_shorten_survival_ladder(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = GuidanceKernel(clock, hard)
        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.guidance_target = (80.0, 120.0)
        solver.guidance_deadline = state.frame + 5

        solver.decide(state)

        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "target"],
            [8, 12, 16],
        )

    def test_unique_constant_frontier_can_anchor_a_target(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = ConstantFrontierKernel(clock, hard)
        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 6

        decision = solver.decide(state)

        self.assertEqual(decision.action.name, "right")
        self.assertEqual(solver.pending_target_action.name, "right")
        self.assertEqual(solver.pending_target_horizon, 8)


if __name__ == "__main__":
    unittest.main()

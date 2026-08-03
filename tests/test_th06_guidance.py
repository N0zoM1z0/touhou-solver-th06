import os
import unittest
from dataclasses import replace

from counterexample_corpus import ACTION_BY_NAME, decode_snapshot, load_cases
from th06.guidance import (
    TerminalGuidance,
    preferred_target_actions,
    terminal_guidance_scores,
    terminal_reachability_counts,
)
from th06.kernels.safety import NativeSafetyKernel
from th06.model import (
    ACTIONS,
    CONTROL_ACTIONS,
    SafeAction,
    Snapshot,
    action_from_input,
)
from th06.safety import certify_actions
from th06.solver import Solver
from th06.viability import nominal_policy_scores, replanning_scores


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


class DeepFrontierGuidanceKernel(GuidanceKernel):
    def certify_selected(self, _state, horizon, actions, collision_margin):
        allowed = frozenset(actions)
        candidates = tuple(
            item for item in self.hard if item.action in allowed
        )
        if horizon >= 16:
            return tuple(
                item
                for item in candidates
                if item.action.name == "up_left"
            )
        return candidates


class RankedDeepFrontierGuidanceKernel(GuidanceKernel):
    def __init__(self, clock: ManualClock, hard) -> None:
        super().__init__(clock, hard)
        self.target_candidates = []

    def certify_selected(self, _state, horizon, actions, collision_margin):
        allowed = frozenset(actions)
        candidates = tuple(
            item for item in self.hard if item.action in allowed
        )
        if horizon >= 12:
            return tuple(
                item
                for item in candidates
                if item.action.name in ("left", "up_right")
            )
        if horizon >= 8:
            return tuple(
                item
                for item in candidates
                if item.action.name in (
                    "stay", "left", "up_right", "down_left"
                )
            )
        return candidates

    def terminal_guidance(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        target=None,
    ):
        self.calls.append(("target", horizon))
        self.target_candidates.append(
            (horizon, tuple(item.action.name for item in candidates))
        )
        self.clock.advance_ms(0.2)
        counts = (
            {"left": 2, "up_right": 1}
            if horizon == 8
            else {"left": 1, "up_right": 2}
        )
        return {
            item.action: TerminalGuidance(
                terminal_count=counts.get(item.action.name, 1),
                free_clearance=12.0,
                free_x=80.0,
                free_y=120.0,
                target_distance_squared=9.0,
            )
            for item in candidates
        }

    def nominal_policy_counts_budgeted(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("budgeted_policy", horizon))
        self.clock.advance_ms(min(1.0, budget_ms))
        if budget_ms < 1.0:
            return None
        return {
            item.action: (
                2
                if item.action.name in ("left", "up_right")
                else 1
            )
            for item in candidates
        }

    def boolean_reachability_progressive(
        self,
        _state,
        candidates,
        _segment_length,
        minimum_horizon,
        maximum_horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("progressive_counts", maximum_horizon))
        self.clock.advance_ms(min(1.0, budget_ms))
        return (
            16,
            {
                item.action: (
                    1 if item.action.name in ("left", "up_right") else 0
                )
                for item in candidates
            },
            maximum_horizon == 16,
        )


class SurvivalBeforeShallowTargetKernel(GuidanceKernel):
    def certify_selected(self, _state, horizon, actions, collision_margin):
        allowed = frozenset(actions)
        candidates = tuple(
            item for item in self.hard if item.action in allowed
        )
        if horizon >= 16:
            return tuple(
                item
                for item in candidates
                if item.action.name in ("stay", "up", "left", "up_left")
            )
        return candidates

    def nominal_policy_counts_budgeted(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("budgeted_policy", horizon))
        self.clock.advance_ms(min(1.0, budget_ms))
        if horizon == 16:
            return None
        return {
            item.action: 10 if item.action.name == "stay" else 1
            for item in candidates
        }

    def boolean_reachability_progressive(
        self,
        _state,
        candidates,
        _segment_length,
        minimum_horizon,
        maximum_horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("progressive_counts", maximum_horizon))
        self.clock.advance_ms(min(1.0, budget_ms))
        return (
            16,
            {
                item.action: 1 if item.action.name == "stay" else 0
                for item in candidates
            },
            maximum_horizon == 16,
        )


class BudgetedReachabilityKernel(GuidanceKernel):
    def nominal_policy_counts_budgeted(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("budgeted_policy", horizon))
        self.clock.advance_ms(min(1.0, budget_ms))
        return {
            item.action: 20 if item.action.name == "left" else 1
            for item in candidates
        }

    def terminal_counts_budgeted(
        self,
        _state,
        candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(
            (
                "budgeted_counts",
                horizon,
                tuple(item.action.name for item in candidates),
            )
        )
        self.clock.advance_ms(min(1.0, budget_ms))
        return {
            item.action: 5 if item.action.name == "down" else 4
            for item in candidates
        }

    def boolean_reachability_progressive(
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
            "progressive_counts",
            minimum_horizon,
            maximum_horizon,
            tuple(item.action.name for item in candidates),
        ))
        self.clock.advance_ms(min(1.0, budget_ms))
        return (
            maximum_horizon,
            {
                item.action: 1 if item.action.name == "down" else 0
                for item in candidates
            },
            True,
        )


class TimedOutReachabilityKernel(BudgetedReachabilityKernel):
    def nominal_policy_counts_budgeted(
        self,
        _state,
        _candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("budgeted_policy", horizon))
        self.clock.advance_ms(min(0.1, budget_ms))
        return None

    def terminal_counts_budgeted(
        self,
        _state,
        _candidates,
        _segment_length,
        horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append(("budgeted_counts", horizon, ()))
        self.clock.advance_ms(budget_ms)
        return None

    def boolean_reachability_progressive(
        self,
        _state,
        _candidates,
        _segment_length,
        minimum_horizon,
        maximum_horizon,
        collision_margin,
        budget_ms,
    ):
        self.calls.append((
            "progressive_counts", minimum_horizon, maximum_horizon, ()
        ))
        self.clock.advance_ms(budget_ms)
        return None


class ShortlistedReachabilityKernel(BudgetedReachabilityKernel):
    def certify_selected(self, _state, horizon, actions, collision_margin):
        allowed = frozenset(actions)
        candidates = tuple(
            item for item in self.hard if item.action in allowed
        )
        if horizon >= 16:
            return tuple(
                item for item in candidates
                if item.action.name in ("stay", "down")
            )
        return candidates


class TerminalGuidanceTests(unittest.TestCase):
    def replay_target_frontier_adjudication_case(self, case, kernel=None):
        values = case["input"]
        source = decode_snapshot(values["acquisition_snapshot"])
        track = decode_snapshot(values["tracking_snapshot"])
        if kernel is None:
            certify = lambda state, horizon: certify_actions(state, horizon)
            terminal = lambda state, candidates, horizon, target=None: (
                terminal_guidance_scores(
                    state,
                    candidates,
                    values["segment_length"],
                    horizon,
                    target,
                )
            )
            policy = lambda state, candidates, horizon: nominal_policy_scores(
                state,
                candidates,
                values["segment_length"],
                horizon,
            )
        else:
            certify = lambda state, horizon: kernel.certify(
                state, horizon, collision_margin=0.35
            )
            terminal = lambda state, candidates, horizon, target=None: (
                kernel.terminal_guidance(
                    state,
                    candidates,
                    values["segment_length"],
                    horizon,
                    collision_margin=0.35,
                    target=target,
                )
            )
            policy = lambda state, candidates, horizon: (
                kernel.nominal_policy_counts(
                    state,
                    candidates,
                    values["segment_length"],
                    horizon,
                    collision_margin=0.35,
                )
            )

        expected = case["expect"]
        source_hard = certify(source, 4)
        acquisition_action = ACTION_BY_NAME[values["acquisition_action"]]
        source_candidate = tuple(
            item for item in source_hard
            if item.action == acquisition_action
        )
        acquired = terminal(
            source,
            source_candidate,
            values["acquisition_horizon"],
        )[acquisition_action]
        target = (acquired.free_x, acquired.free_y)
        self.assertEqual(
            acquired.terminal_count,
            expected["acquisition_terminal_count"],
        )
        self.assertAlmostEqual(
            acquired.free_clearance,
            expected["acquisition_free_clearance"],
            places=4,
        )
        self.assertAlmostEqual(target[0], expected["target"][0], places=4)
        self.assertAlmostEqual(target[1], expected["target"][1], places=4)

        hard = certify(track, 4)
        self.assertEqual(
            [item.action.name for item in hard],
            expected["hard_actions"],
        )
        frontiers = {
            horizon: certify(track, horizon)
            for horizon in (8, 12, 16)
        }
        for horizon, frontier in frontiers.items():
            self.assertEqual(
                [item.action.name for item in frontier],
                expected["frontier_actions_by_horizon"][str(horizon)],
            )

        deepest = frontiers[values["frontier_horizon"]]
        deepest_actions = frozenset(item.action for item in deepest)
        shallow = terminal(
            track,
            hard,
            values["guidance_horizon"],
            target,
        )
        restricted = preferred_target_actions(shallow, deepest_actions)
        self.assertEqual(
            sorted(action.name for action in restricted),
            sorted(expected["shallow_restricted_actions"]),
        )

        scores = policy(
            track,
            deepest,
            values["adjudication_horizon"],
        )
        self.assertEqual(
            {action.name: score for action, score in scores.items()},
            expected["adjudication_scores"],
        )
        best = max(scores.values())
        self.assertEqual(
            sorted(
                action.name for action, score in scores.items()
                if score == best
            ),
            sorted(expected["adjudication_actions"]),
        )

    def test_reference_target_frontier_adjudication_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "target_frontier_adjudication"
        )
        self.assertTrue(cases, "target frontier adjudication corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_target_frontier_adjudication_case(case)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_target_frontier_adjudication_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "target_frontier_adjudication"
        )
        self.assertTrue(cases, "target frontier adjudication corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_target_frontier_adjudication_case(case, kernel)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_budgeted_terminal_guidance_is_complete_or_discarded(self):
        state = snapshot(x=192.0, y=380.0)
        kernel = NativeSafetyKernel()
        hard = kernel.certify(state, 4, collision_margin=0.35)
        expected = kernel.terminal_guidance(
            state,
            hard,
            4,
            20,
            collision_margin=0.35,
        )

        completed = kernel.terminal_guidance_budgeted(
            state,
            hard,
            4,
            20,
            collision_margin=0.35,
            budget_ms=1000.0,
        )
        expired = kernel.terminal_guidance_budgeted(
            state,
            hard,
            4,
            20,
            collision_margin=0.35,
            budget_ms=0.000001,
        )

        self.assertEqual(completed, expected)
        self.assertIsNone(expired)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_budgeted_terminal_counts_are_complete_or_discarded(self):
        state = snapshot(x=192.0, y=380.0)
        kernel = NativeSafetyKernel()
        hard = kernel.certify(state, 4, collision_margin=0.35)
        guidance = kernel.terminal_guidance(
            state,
            hard,
            4,
            20,
            collision_margin=0.35,
        )
        expected = {
            action: value.terminal_count
            for action, value in guidance.items()
        }

        completed = kernel.terminal_counts_budgeted(
            state,
            hard,
            4,
            20,
            collision_margin=0.35,
            budget_ms=1000.0,
        )
        expired = kernel.terminal_counts_budgeted(
            state,
            hard,
            4,
            20,
            collision_margin=0.35,
            budget_ms=0.000001,
        )

        self.assertEqual(completed, expected)
        self.assertIsNone(expired)

    def replay_flexible_reachability_case(self, case, kernel=None):
        values = case["input"]
        state = decode_snapshot(values["snapshot"])
        if kernel is None:
            hard = certify_actions(state, 4)
            shallow = nominal_policy_scores(
                state,
                hard,
                values["segment_length"],
                values["flexible_horizon"],
            )
            fixed = {
                action: value.terminal_count
                for action, value in terminal_guidance_scores(
                    state,
                    hard,
                    values["segment_length"],
                    values["fixed_horizon"],
                ).items()
            }
            flexible = terminal_reachability_counts(
                state,
                hard,
                values["segment_length"],
                values["flexible_horizon"],
            )
        else:
            hard = kernel.certify(state, 4, collision_margin=0.35)
            shallow = kernel.nominal_policy_counts(
                state,
                hard,
                values["segment_length"],
                values["flexible_horizon"],
                collision_margin=0.35,
            )
            fixed = kernel.terminal_counts(
                state,
                hard,
                values["segment_length"],
                values["fixed_horizon"],
                collision_margin=0.35,
            )
            result = kernel.flexible_terminal_counts_progressive(
                state,
                hard,
                values["segment_length"],
                values["flexible_horizon"],
                values["flexible_horizon"],
                collision_margin=0.35,
                budget_ms=1000.0,
            )
            self.assertIsNotNone(result)
            completed, flexible, reached_maximum = result
            self.assertEqual(completed, values["flexible_horizon"])
            self.assertTrue(reached_maximum)

        expected = case["expect"]
        self.assertEqual(
            [item.action.name for item in hard],
            expected["hard_actions"],
        )
        self.assertEqual(
            {action.name: score for action, score in shallow.items()},
            expected["shallow_scores"],
        )
        self.assertEqual(
            sorted(
                action.name for action, score in shallow.items()
                if score == max(shallow.values())
            ),
            sorted(expected["shallow_actions"]),
        )
        self.assertEqual(
            {action.name: score for action, score in fixed.items()},
            expected["fixed_counts"],
        )
        self.assertEqual(
            sorted(
                action.name for action, score in fixed.items()
                if score == max(fixed.values())
            ),
            sorted(expected["fixed_actions"]),
        )
        self.assertEqual(
            {action.name: score for action, score in flexible.items()},
            expected["flexible_counts"],
        )
        self.assertEqual(
            sorted(
                action.name for action, score in flexible.items()
                if score == max(flexible.values())
            ),
            sorted(expected["flexible_actions"]),
        )
        self.assertIn(values["observed_action"], expected["fixed_actions"])
        self.assertNotIn(
            values["observed_action"], expected["flexible_actions"]
        )

    def test_reference_flexible_reachability_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "flexible_reachability_divergence"
        )
        self.assertTrue(cases, "flexible reachability corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_flexible_reachability_case(case)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_flexible_reachability_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "flexible_reachability_divergence"
        )
        self.assertTrue(cases, "flexible reachability corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_flexible_reachability_case(case, kernel)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_progressive_flexible_counts_are_complete_or_discarded(self):
        case = next(
            case for case in load_cases()
            if case.get("runner") == "flexible_reachability_divergence"
        )
        values = case["input"]
        state = decode_snapshot(values["snapshot"])
        kernel = NativeSafetyKernel()
        hard = kernel.certify(state, 4, collision_margin=0.35)

        completed = kernel.flexible_terminal_counts_progressive(
            state,
            hard,
            4,
            8,
            10,
            collision_margin=0.35,
            budget_ms=1000.0,
        )
        expired = kernel.flexible_terminal_counts_progressive(
            state,
            hard,
            4,
            8,
            20,
            collision_margin=0.35,
            budget_ms=0.000001,
        )

        self.assertIsNotNone(completed)
        horizon, counts, reached_maximum = completed
        self.assertEqual(horizon, 10)
        self.assertTrue(reached_maximum)
        self.assertEqual(
            counts,
            terminal_reachability_counts(state, hard, 4, horizon),
        )
        self.assertIsNone(expired)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_progressive_counts_cover_every_physical_first_action(self):
        state = snapshot(x=192.0, y=380.0, input_mask=0x04)
        kernel = NativeSafetyKernel()
        hard = kernel.certify_selected(
            state,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        )
        self.assertEqual(len(hard), len(CONTROL_ACTIONS))

        for horizon in (8, 12, 16):
            with self.subTest(horizon=horizon):
                expected = kernel.terminal_counts(
                    state,
                    hard,
                    4,
                    horizon,
                    collision_margin=0.35,
                )
                result = kernel.segment_terminal_counts_progressive(
                    state,
                    hard,
                    4,
                    8,
                    horizon,
                    collision_margin=0.35,
                    budget_ms=1000.0,
                )
                self.assertIsNotNone(result)
                completed, counts, reached_maximum = result
                self.assertEqual(completed, horizon)
                self.assertTrue(reached_maximum)
                self.assertEqual(counts, expected)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_progressive_route_guidance_matches_exact_query(self):
        state = snapshot(x=192.0, y=380.0, input_mask=0x04)
        kernel = NativeSafetyKernel()
        hard = kernel.certify_selected(
            state,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        )

        for action in CONTROL_ACTIONS:
            with self.subTest(action=action.name):
                candidate = next(
                    item for item in hard if item.action == action
                )
                result = kernel.segment_terminal_guidance_progressive(
                    state,
                    hard,
                    4,
                    8,
                    16,
                    action,
                    collision_margin=0.35,
                    budget_ms=1000.0,
                )
                expected = kernel.terminal_guidance(
                    state,
                    (candidate,),
                    4,
                    16,
                    collision_margin=0.35,
                )[action]

                self.assertIsNotNone(result)
                completed, counts, reached_maximum, guidance = result
                self.assertEqual(completed, 16)
                self.assertTrue(reached_maximum)
                self.assertIsNotNone(guidance)
                self.assertEqual(guidance.terminal_count, counts[action])
                self.assertEqual(
                    guidance.terminal_count,
                    expected.terminal_count,
                )
                self.assertAlmostEqual(
                    guidance.free_clearance,
                    expected.free_clearance,
                    places=4,
                )
                self.assertAlmostEqual(
                    guidance.free_x,
                    expected.free_x,
                    places=4,
                )
                self.assertAlmostEqual(
                    guidance.free_y,
                    expected.free_y,
                    places=4,
                )

    def replay_segment_terminal_progressive_case(self, case, kernel=None):
        values = case["input"]
        expected = case["expect"]
        state = decode_snapshot(values["snapshot"])
        if kernel is None:
            hard = certify_actions(state, 4, actions=CONTROL_ACTIONS)
        else:
            hard = kernel.certify_selected(
                state,
                4,
                CONTROL_ACTIONS,
                collision_margin=0.35,
            )
        self.assertEqual(
            [candidate.action.name for candidate in hard],
            expected["hard_actions"],
        )

        delivery_viable = None
        if "replanning_scores" in expected:
            scores = (
                replanning_scores(
                    state,
                    hard,
                    split=values["segment_length"],
                    horizon=8,
                )
                if kernel is None
                else kernel.replanning_scores(
                    state,
                    hard,
                    values["segment_length"],
                    8,
                    collision_margin=0.35,
                )
            )
            self.assertEqual(
                {action.name: score for action, score in scores.items()},
                expected["replanning_scores"],
            )
            best = max(scores.values(), default=0)
            self.assertGreater(best, 0)
            self.assertEqual(
                [
                    action.name for action, score in scores.items()
                    if score == best
                ],
                expected["replanning_actions"],
            )
            delivery_viable = frozenset(
                action for action, score in scores.items() if score > 0
            )
            if kernel is not None:
                viability = kernel.replanning_viability_budgeted(
                    state,
                    hard,
                    values["segment_length"],
                    8,
                    collision_margin=0.35,
                    budget_ms=1000.0,
                )
                self.assertEqual(
                    viability,
                    {
                        action: int(score > 0)
                        for action, score in scores.items()
                    },
                )
                progressive = (
                    kernel.replanning_scores_progressive_budgeted(
                        state,
                        hard,
                        values["segment_length"],
                        8,
                        collision_margin=0.35,
                        budget_ms=1000.0,
                    )
                )
                self.assertIsNotNone(progressive)
                progressive_scores, robustness_complete = progressive
                self.assertTrue(robustness_complete)
                self.assertEqual(progressive_scores, scores)

        constants_by_horizon = {}
        for raw_horizon, expected_actions in expected.get(
            "constant_actions_by_horizon", {}
        ).items():
            horizon = int(raw_horizon)
            constant = (
                certify_actions(state, horizon, actions=CONTROL_ACTIONS)
                if kernel is None
                else kernel.certify_selected(
                    state,
                    horizon,
                    CONTROL_ACTIONS,
                    collision_margin=0.35,
                )
            )
            constants_by_horizon[horizon] = constant
            self.assertEqual(
                [candidate.action.name for candidate in constant],
                expected_actions,
            )

        fixed_by_horizon = {}
        for raw_horizon, expected_scores in (
            expected["scores_by_horizon"].items()
        ):
            horizon = int(raw_horizon)
            scores = (
                {
                    action: value.terminal_count
                    for action, value in terminal_guidance_scores(
                        state,
                        hard,
                        values["segment_length"],
                        horizon,
                    ).items()
                }
                if kernel is None
                else kernel.terminal_counts(
                    state,
                    hard,
                    values["segment_length"],
                    horizon,
                    collision_margin=0.35,
                )
            )
            fixed_by_horizon[horizon] = scores
            self.assertEqual(
                {action.name: score for action, score in scores.items()},
                expected_scores,
            )
            best = max(scores.values())
            self.assertEqual(
                [
                    action.name for action, score in scores.items()
                    if score == best
                ],
                expected["actions_by_horizon"][raw_horizon],
            )
            eligible_expected = expected.get(
                "eligible_actions_by_horizon", {}
            ).get(raw_horizon)
            if eligible_expected is not None:
                self.assertIsNotNone(delivery_viable)
                eligible_best = max(
                    score for action, score in scores.items()
                    if action in delivery_viable
                )
                self.assertEqual(
                    [
                        action.name for action, score in scores.items()
                        if (
                            action in delivery_viable
                            and score == eligible_best
                        )
                    ],
                    eligible_expected,
                )

        reserve_expect = expected.get("publication_reserve")
        if reserve_expect is not None:
            horizon = reserve_expect["horizon"]
            scores = fixed_by_horizon[values["maximum_horizon"]]
            reserve = constants_by_horizon[horizon]
            reserve_best = max(
                scores[candidate.action] for candidate in reserve
            )
            self.assertEqual(reserve_best, reserve_expect["best_score"])
            self.assertEqual(
                [
                    candidate.action.name for candidate in reserve
                    if scores[candidate.action] == reserve_best
                ],
                reserve_expect["actions"],
            )

        if kernel is not None:
            result = kernel.segment_terminal_counts_progressive(
                state,
                hard,
                values["segment_length"],
                values["minimum_horizon"],
                values["maximum_horizon"],
                collision_margin=0.35,
                budget_ms=1000.0,
            )
            self.assertIsNotNone(result)
            completed, counts, reached_maximum = result
            self.assertEqual(completed, values["maximum_horizon"])
            self.assertTrue(reached_maximum)
            self.assertEqual(counts, fixed_by_horizon[completed])

    def test_reference_segment_terminal_progressive_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "segment_terminal_progressive"
        )
        self.assertTrue(cases, "segment terminal corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_segment_terminal_progressive_case(case)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_segment_terminal_progressive_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "segment_terminal_progressive"
        )
        self.assertTrue(cases, "segment terminal corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_segment_terminal_progressive_case(case, kernel)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_boolean_reachability_is_complete_or_discarded(self):
        state = snapshot(x=192.0, y=380.0, input_mask=0x04)
        kernel = NativeSafetyKernel()
        hard = kernel.certify_selected(
            state,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        )

        completed = kernel.boolean_reachability_progressive(
            state,
            hard,
            4,
            8,
            12,
            collision_margin=0.35,
            budget_ms=1000.0,
        )
        expired = kernel.boolean_reachability_progressive(
            state,
            hard,
            4,
            8,
            20,
            collision_margin=0.35,
            budget_ms=0.000001,
        )

        self.assertIsNotNone(completed)
        horizon, membership, reached_maximum = completed
        self.assertEqual(horizon, 12)
        self.assertTrue(reached_maximum)
        self.assertEqual(set(membership), set(CONTROL_ACTIONS))
        self.assertTrue(all(membership.values()))
        self.assertIsNone(expired)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_exact_terminal_states_preserve_f6659_escape_direction(self):
        case = next(
            item for item in load_cases()
            if item["id"] == "stage1-f6659-completed-deep-retry"
        )
        state = decode_snapshot(case["input"]["snapshot"])
        kernel = NativeSafetyKernel()
        hard = kernel.certify_selected(
            state,
            4,
            CONTROL_ACTIONS,
            collision_margin=0.35,
        )

        scores = kernel.terminal_counts(
            state,
            hard,
            4,
            16,
            collision_margin=0.35,
        )
        best = max(scores.values())

        self.assertEqual(
            {
                action.name for action, score in scores.items()
                if score == best
            },
            {"up_right", "up_right_fast"},
        )

    def replay_terminal_reachability_case(self, case, kernel=None):
        values = case["input"]
        state = decode_snapshot(values["snapshot"])
        if kernel is None:
            hard = certify_actions(state, 4)
            shallow = nominal_policy_scores(
                state,
                hard,
                values["segment_length"],
                values["shallow_horizon"],
            )
            guidance = terminal_guidance_scores(
                state,
                hard,
                values["segment_length"],
                values["reachability_horizon"],
            )
            frontier = certify_actions(
                state,
                values["reachability_horizon"],
            )
        else:
            hard = kernel.certify(state, 4, collision_margin=0.35)
            shallow = kernel.nominal_policy_counts(
                state,
                hard,
                values["segment_length"],
                values["shallow_horizon"],
                collision_margin=0.35,
            )
            guidance = kernel.terminal_guidance(
                state,
                hard,
                values["segment_length"],
                values["reachability_horizon"],
                collision_margin=0.35,
            )
            counts = kernel.terminal_counts(
                state,
                hard,
                values["segment_length"],
                values["reachability_horizon"],
                collision_margin=0.35,
            )
            self.assertEqual(
                counts,
                {
                    action: value.terminal_count
                    for action, value in guidance.items()
                },
            )
            frontier = kernel.certify(
                state,
                values["reachability_horizon"],
                collision_margin=0.35,
            )

        expected = case["expect"]
        self.assertEqual(
            [item.action.name for item in hard],
            expected["hard_actions"],
        )
        self.assertEqual(
            {action.name: score for action, score in shallow.items()},
            expected["shallow_scores"],
        )
        shallow_best = max(shallow.values())
        shallow_actions = {
            action.name for action, score in shallow.items()
            if score == shallow_best
        }
        self.assertEqual(shallow_actions, set(expected["shallow_actions"]))
        self.assertIn(values["observed_action"], shallow_actions)

        self.assertEqual(
            {
                action.name: value.terminal_count
                for action, value in guidance.items()
            },
            expected["terminal_counts"],
        )
        terminal_best = max(
            value.terminal_count for value in guidance.values()
        )
        terminal_actions = {
            action.name for action, value in guidance.items()
            if value.terminal_count == terminal_best
        }
        self.assertEqual(terminal_actions, set(expected["terminal_actions"]))
        self.assertNotIn(values["observed_action"], terminal_actions)
        self.assertEqual(
            [item.action.name for item in frontier],
            expected["constant_actions"],
        )

    def test_reference_terminal_reachability_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "terminal_reachability_divergence"
        )
        self.assertTrue(cases, "terminal reachability corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_terminal_reachability_case(case)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_terminal_reachability_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "terminal_reachability_divergence"
        )
        self.assertTrue(cases, "terminal reachability corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_terminal_reachability_case(case, kernel)

    def replay_terminal_shortlist_case(self, case, kernel=None):
        values = case["input"]
        state = decode_snapshot(values["snapshot"])
        if kernel is None:
            hard = certify_actions(state, 4)
            shallow = nominal_policy_scores(
                state,
                hard,
                values["segment_length"],
                values["shallow_horizon"],
            )
            constant = certify_actions(
                state,
                values["constant_horizon"],
                actions=tuple(item.action for item in hard),
            )
        else:
            hard = kernel.certify(state, 4, collision_margin=0.35)
            shallow = kernel.nominal_policy_counts(
                state,
                hard,
                values["segment_length"],
                values["shallow_horizon"],
                collision_margin=0.35,
            )
            constant = kernel.certify_selected(
                state,
                values["constant_horizon"],
                tuple(item.action for item in hard),
                collision_margin=0.35,
            )

        shallow_best = max(shallow.values())
        deep_actions = {
            action for action, score in shallow.items()
            if score == shallow_best
        }
        deep_actions.update(item.action for item in constant)
        deep_actions.add(action_from_input(state.input_mask))
        deep = tuple(
            item for item in hard if item.action in deep_actions
        )
        if kernel is None:
            guidance = terminal_guidance_scores(
                state,
                deep,
                values["segment_length"],
                values["reachability_horizon"],
            )
            counts = {
                action: value.terminal_count
                for action, value in guidance.items()
            }
        else:
            counts = kernel.terminal_counts(
                state,
                deep,
                values["segment_length"],
                values["reachability_horizon"],
                collision_margin=0.35,
            )

        expected = case["expect"]
        self.assertEqual(
            [item.action.name for item in hard],
            expected["hard_actions"],
        )
        self.assertEqual(
            {action.name: score for action, score in shallow.items()},
            expected["shallow_scores"],
        )
        self.assertEqual(
            [
                action.name for action, score in shallow.items()
                if score == shallow_best
            ],
            expected["shallow_actions"],
        )
        self.assertEqual(
            [item.action.name for item in constant],
            expected["constant_actions"],
        )
        self.assertEqual(
            [item.action.name for item in deep],
            expected["deep_candidate_actions"],
        )
        self.assertEqual(
            {action.name: score for action, score in counts.items()},
            expected["terminal_counts"],
        )
        terminal_best = max(counts.values())
        terminal_actions = [
            action.name for action, score in counts.items()
            if score == terminal_best
        ]
        self.assertEqual(terminal_actions, expected["terminal_actions"])
        self.assertIn(values["observed_action"], expected["shallow_actions"])
        self.assertNotIn(values["observed_action"], terminal_actions)

    def test_reference_terminal_shortlist_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "terminal_reachability_shortlist"
        )
        self.assertTrue(cases, "terminal shortlist corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_terminal_shortlist_case(case)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_terminal_shortlist_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "terminal_reachability_shortlist"
        )
        self.assertTrue(cases, "terminal shortlist corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_terminal_shortlist_case(case, kernel)

    def replay_frontier_rerank_case(self, case, kernel=None):
        values = case["input"]
        state = decode_snapshot(values["snapshot"])
        if kernel is None:
            hard = certify_actions(state, 4)
            frontier = certify_actions(
                state, values["frontier_horizon"]
            )
            guidance = terminal_guidance_scores(
                state,
                hard,
                values["segment_length"],
                values["guidance_horizon"],
                tuple(values["target"]),
            )
        else:
            hard = kernel.certify(state, 4, collision_margin=0.35)
            frontier = kernel.certify(
                state,
                values["frontier_horizon"],
                collision_margin=0.35,
            )
            guidance = kernel.terminal_guidance(
                state,
                hard,
                values["segment_length"],
                values["guidance_horizon"],
                collision_margin=0.35,
                target=tuple(values["target"]),
            )
        expected = case["expect"]
        self.assertEqual(
            sorted(item.action.name for item in frontier),
            sorted(expected["frontier_actions"]),
        )
        global_preferred = preferred_target_actions(
            guidance, frozenset(item.action for item in hard)
        )
        restricted = preferred_target_actions(
            guidance, frozenset(item.action for item in frontier)
        )
        self.assertEqual(
            sorted(action.name for action in global_preferred),
            sorted(expected["global_actions"]),
        )
        self.assertEqual(
            sorted(action.name for action in restricted),
            sorted(expected["restricted_actions"]),
        )

    def test_reference_frontier_rerank_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "target_frontier_rerank"
        )
        self.assertTrue(cases, "target frontier rerank corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_frontier_rerank_case(case)

    @unittest.skipUnless(os.name == "nt", "native guidance needs Windows")
    def test_native_frontier_rerank_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "target_frontier_rerank"
        )
        self.assertTrue(cases, "target frontier rerank corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                self.replay_frontier_rerank_case(case, kernel)

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

    def test_target_cannot_discard_focused_correction_reserve(self):
        focused = next(
            action for action in CONTROL_ACTIONS
            if action.name == "right"
        )
        fast = next(
            action for action in CONTROL_ACTIONS
            if action.name == "right_fast"
        )
        guidance = {
            focused: TerminalGuidance(9, 4.0, 200.0, 200.0, 9.0),
            fast: TerminalGuidance(9, 4.0, 200.0, 200.0, 1.0),
        }

        self.assertEqual(
            preferred_target_actions(
                guidance, frozenset((focused, fast))
            ),
            frozenset((focused,)),
        )

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

        class OrderedGuidanceKernel(GuidanceKernel):
            def certify_selected(
                self, state, horizon, actions, collision_margin
            ):
                self.calls.append(("frontier", horizon))
                return super().certify_selected(
                    state, horizon, actions, collision_margin
                )

        kernel = OrderedGuidanceKernel(clock, hard)
        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 6

        proposed = solver.decide(state)
        self.assertEqual(proposed.action.name, "right")
        self.assertEqual(solver.pending_target_action.name, "right")

        kernel.calls.clear()
        acquired = solver.decide(
            replace(state, frame=101, input_mask=0x84)
        )
        self.assertEqual(acquired.action.name, "right")
        self.assertEqual(solver.guidance_target, (80.0, 120.0))
        self.assertIsNone(solver.pending_target_action)
        call_names = [call[0] for call in kernel.calls]
        self.assertLess(
            call_names.index("frontier"),
            call_names.index("acquire"),
        )

        guided = solver.decide(
            replace(state, frame=102, input_mask=0x84)
        )
        self.assertEqual(guided.action.name, "right")
        self.assertIn("acquire", {call[0] for call in kernel.calls})
        self.assertIn("target", {call[0] for call in kernel.calls})

    def test_focus_variants_of_one_route_can_anchor_one_target(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in CONTROL_ACTIONS
        )
        clock = ManualClock()

        class DirectionalTieKernel(GuidanceKernel):
            def nominal_policy_counts(
                self,
                _state,
                candidates,
                _segment_length,
                horizon,
                collision_margin,
            ):
                self.calls.append(("policy", horizon))
                return {
                    item.action: (
                        9
                        if (item.action.dx, item.action.dy) == (1, 0)
                        else 1
                    )
                    for item in candidates
                }

        kernel = DirectionalTieKernel(clock, hard)
        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 6

        decision = solver.decide(state)

        self.assertEqual(decision.action.name, "right")
        self.assertEqual(
            {candidate.action.name for candidate in decision.safe_actions},
            {action.name for action in CONTROL_ACTIONS},
        )
        self.assertEqual(solver.pending_target_action.name, "right")

    def test_pending_target_retries_after_an_unaffordable_frame(self):
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

        solver.effort.target_affordable = lambda *_args: False
        kernel.calls.clear()
        deferred = solver.decide(
            replace(state, frame=101, input_mask=0x84)
        )
        self.assertEqual(deferred.action.name, "right")
        self.assertEqual(solver.pending_target_action.name, "right")
        self.assertIsNone(solver.guidance_target)
        self.assertNotIn("acquire", {call[0] for call in kernel.calls})

        solver.effort.target_affordable = lambda *_args: True
        acquired = solver.decide(
            replace(state, frame=102, input_mask=0x84)
        )
        self.assertEqual(acquired.action.name, "right")
        self.assertIsNone(solver.pending_target_action)
        self.assertEqual(solver.guidance_target, (80.0, 120.0))

    def test_progressive_survival_can_publish_optional_pending_target(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()

        class OptionalGuidanceKernel(GuidanceKernel):
            def segment_terminal_counts_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                _minimum_horizon,
                maximum_horizon,
                collision_margin,
                budget_ms,
            ):
                self.calls.append(("progressive", maximum_horizon))
                return (
                    maximum_horizon,
                    {
                        item.action: (
                            9 if item.action.name == "right" else 1
                        )
                        for item in candidates
                    },
                    True,
                )

            def segment_terminal_guidance_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                _minimum_horizon,
                maximum_horizon,
                guidance_action,
                collision_margin,
                budget_ms,
            ):
                self.calls.append(("progressive_guidance", maximum_horizon))
                counts = {
                    item.action: (
                        9 if item.action.name == "right" else 1
                    )
                    for item in candidates
                }
                return (
                    maximum_horizon,
                    counts,
                    True,
                    TerminalGuidance(
                        terminal_count=counts[guidance_action],
                        free_clearance=12.0,
                        free_x=80.0,
                        free_y=120.0,
                        target_distance_squared=float("inf"),
                    ),
                )

        kernel = OptionalGuidanceKernel(clock, hard)
        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16

        proposed = solver.decide(state)
        self.assertEqual(proposed.action.name, "right")
        self.assertEqual(solver.pending_target_action.name, "right")

        solver.effort.target_affordable = lambda *_args: False
        kernel.calls.clear()
        acquired = solver.decide(
            replace(state, frame=101, input_mask=0x84)
        )

        self.assertEqual(acquired.action.name, "right")
        self.assertEqual(solver.guidance_target, (80.0, 120.0))
        self.assertIsNone(solver.pending_target_action)
        self.assertIn(
            "progressive_guidance",
            {call[0] for call in kernel.calls},
        )
        self.assertNotIn("acquire", {call[0] for call in kernel.calls})

    def test_hard_endpoint_tracks_target_only_inside_survival_tie(self):
        state = snapshot(x=192.0, y=380.0, input_mask=0x84)
        hard = tuple(
            SafeAction(
                action,
                10.0,
                state.x + action.dx * 4.0,
                state.y + action.dy * 4.0,
            )
            for action in ACTIONS
        )
        clock = ManualClock()

        class TargetTieKernel(GuidanceKernel):
            def segment_terminal_counts_progressive(
                self,
                _state,
                candidates,
                _segment_length,
                _minimum_horizon,
                maximum_horizon,
                collision_margin,
                budget_ms,
            ):
                return (
                    maximum_horizon,
                    {
                        item.action: (
                            9
                            if item.action.name in ("stay", "up", "right")
                            else 1
                        )
                        for item in candidates
                    },
                    True,
                )

        solver = Solver(decision_budget_ms=100.0, clock=clock)
        solver.kernel = TargetTieKernel(clock, hard)
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.target_affordable = lambda *_args: False
        solver.guidance_target = (192.0, 300.0)
        solver.guidance_deadline = state.frame + 16

        decision = solver.decide(state)

        self.assertEqual(decision.action.name, "up")
        self.assertEqual(
            {item.action.name for item in decision.safe_actions},
            {action.name for action in ACTIONS},
        )

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

    def test_target_refinement_is_complete_or_discard_with_residual_budget(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()

        class TimedTargetKernel(GuidanceKernel):
            def terminal_guidance_budgeted(
                self,
                _state,
                _candidates,
                _segment_length,
                horizon,
                collision_margin,
                budget_ms,
                target=None,
            ):
                self.calls.append(("budgeted_target", horizon, budget_ms))
                self.clock.advance_ms(budget_ms)
                return None

        kernel = TimedTargetKernel(clock, hard)
        solver = Solver(decision_budget_ms=12.5, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.target_rate_by_kind["track"][8] = 0.0
        solver.effort.target_frame_by_kind["track"][8] = state.frame
        solver.guidance_target = (80.0, 120.0)
        solver.guidance_deadline = state.frame + 16

        decision = solver.decide(state)

        self.assertIsNotNone(decision.action)
        calls = [call for call in kernel.calls if call[0] == "budgeted_target"]
        self.assertEqual(len(calls), 1)
        self.assertGreater(calls[0][2], 0.0)
        self.assertNotIn("target", {call[0] for call in kernel.calls})
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_shallow_target_cannot_override_deeper_fresh_frontier(self):
        state = snapshot(x=192.0, y=380.0)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = DeepFrontierGuidanceKernel(clock, hard)
        solver = Solver(decision_budget_ms=12.5, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.target_rate_by_kind["track"].update(
            {8: 0.0, 12: 1.0}
        )
        solver.effort.target_frame_by_kind["track"].update(
            {8: state.frame, 12: state.frame}
        )
        solver.guidance_target = (80.0, 120.0)
        solver.guidance_deadline = state.frame + 16

        decision = solver.decide(state)

        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "target"],
            [8],
        )
        self.assertEqual(decision.action.name, "up_left")
        self.assertEqual(decision.effort_horizon, 20)

    def test_survival_policy_precedes_same_horizon_target_refinement(self):
        state = snapshot(x=192.0, y=380.0, input_mask=0x94)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = RankedDeepFrontierGuidanceKernel(clock, hard)
        solver = Solver(decision_budget_ms=12.5, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.target_rate_by_kind["track"].update(
            {8: 0.0, 12: 0.003, 16: 0.0}
        )
        solver.effort.target_frame_by_kind["track"].update(
            {8: state.frame, 12: state.frame, 16: state.frame}
        )
        solver.guidance_target = (80.0, 120.0)
        solver.guidance_deadline = state.frame + 16

        decision = solver.decide(state)

        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "target"],
            [16],
        )
        self.assertEqual(
            kernel.target_candidates,
            [
                (
                    16,
                    ("left", "up_right"),
                ),
            ],
        )
        deep_call = next(
            call for call in kernel.calls if call[0] == "progressive_counts"
        )
        self.assertEqual(deep_call, ("progressive_counts", 20))
        self.assertLess(
            kernel.calls.index(deep_call),
            kernel.calls.index(("target", 16)),
        )
        self.assertEqual(decision.action.name, "up_right")
        self.assertEqual(decision.effort_horizon, 16)

    def test_shallow_target_waits_when_survival_is_deeper(self):
        state = snapshot(x=20.569, y=23.221, input_mask=0x14)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = SurvivalBeforeShallowTargetKernel(clock, hard)
        solver = Solver(decision_budget_ms=12.5, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 16
        solver.effort.observe_policy_timeout(state, 16)
        solver.effort.target_rate_by_kind["track"][8] = 0.0
        solver.effort.target_frame_by_kind["track"][8] = state.frame
        solver.guidance_target = (17.25, 28.53)
        solver.guidance_deadline = state.frame + 15

        decision = solver.decide(state)

        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "progressive_counts"],
            [20],
        )
        self.assertNotIn("target", {call[0] for call in kernel.calls})
        self.assertEqual(decision.action.name, "stay")
        self.assertEqual(decision.effort_horizon, 16)

    def test_progressive_counts_precede_path_volume_and_soft_target(self):
        state = snapshot(x=364.0, y=161.858, input_mask=0x14)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = ShortlistedReachabilityKernel(clock, hard)
        solver = Solver(decision_budget_ms=12.5, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 20
        solver.guidance_target = (80.0, 120.0)
        solver.guidance_deadline = state.frame + 20

        decision = solver.decide(state)

        self.assertEqual(
            [call for call in kernel.calls if call[0] == "progressive_counts"],
            [(
                "progressive_counts",
                8,
                20,
                tuple(action.name for action in ACTIONS),
            )],
        )
        self.assertNotIn(
            "budgeted_policy",
            {call[0] for call in kernel.calls},
        )
        self.assertNotIn("target", {call[0] for call in kernel.calls})
        self.assertEqual(decision.action.name, "down")
        self.assertEqual(decision.effort_horizon, 20)

    def test_terminal_minimum_timeout_preserves_hard_authority(self):
        state = snapshot(x=364.0, y=161.858, input_mask=0x14)
        hard = tuple(
            SafeAction(action, 10.0, state.x, state.y)
            for action in ACTIONS
        )
        clock = ManualClock()
        kernel = TimedOutReachabilityKernel(clock, hard)
        solver = Solver(decision_budget_ms=12.5, clock=clock)
        solver.kernel = kernel
        solver.backend = "test"
        solver.effort.rollout_ms_per_work = 0.0
        solver.effort.last_limit = 20

        decision = solver.decide(state)

        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "budgeted_counts"],
            [8],
        )
        self.assertNotIn(
            "progressive_counts",
            {call[0] for call in kernel.calls},
        )
        self.assertEqual(
            [call[1] for call in kernel.calls if call[0] == "budgeted_policy"],
            [],
        )
        self.assertIn(decision.action, {item.action for item in hard})
        self.assertEqual(decision.effort_horizon, 4)
        self.assertLessEqual(clock.seconds * 1000.0, 12.5)

    def test_physical_discontinuity_discards_only_soft_plan_state(self):
        solver = Solver()
        solver.guidance_target = (80.0, 120.0)
        solver.guidance_deadline = 120
        solver.pending_target_action = ACTION_BY_NAME["right"]
        solver.pending_target_horizon = 16
        solver.ranker.committed_action = ACTION_BY_NAME["right"]
        solver.ranker.commit_until_frame = 120

        solver.reset_plan()

        self.assertIsNone(solver.guidance_target)
        self.assertIsNone(solver.pending_target_action)
        self.assertEqual(solver.pending_target_horizon, 4)
        self.assertIsNone(solver.ranker.committed_action)

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
        self.assertEqual(solver.pending_target_horizon, 20)


if __name__ == "__main__":
    unittest.main()

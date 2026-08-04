import os
import unittest
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
if __name__ == "__main__":
    unittest.main()

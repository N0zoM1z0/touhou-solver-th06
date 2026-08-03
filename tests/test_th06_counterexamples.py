import os
import unittest
from dataclasses import replace

from counterexample_corpus import (
    ACTION_BY_NAME,
    decode_snapshot,
    load_cases,
)
from th06.input_lease import (
    bounded_delivery_age,
    changed_action_delivery_supported,
    covered_current_retry,
    required_changed_action_delivery_delay,
)
from th06.hazards.world import forecast_world_births
from th06.model import (
    ACTIONS,
    CONTROL_ACTIONS,
    SafeAction,
    Snapshot,
    action_from_input,
)
from th06.ranking import ProposalRanker
from th06.kernels.safety import NativeSafetyKernel
from th06.safety import certify_actions
from th06.solver import Solver
from th06.viability import (
    delivery_segment_viability_scores,
    nominal_policy_scores,
)


class CounterexampleCorpusTests(unittest.TestCase):
    def test_repeated_pickup_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "delivery_segment_viability"
        )
        self.assertTrue(cases, "repeated-pickup corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                expected = case["expect"]
                state = decode_snapshot(values["snapshot"])
                hard = certify_actions(
                    state, values["segment_length"], actions=CONTROL_ACTIONS
                )
                viable = frozenset(expected["replanning_viable"])
                candidates = tuple(
                    candidate for candidate in hard
                    if candidate.action.name in viable
                )
                scores = delivery_segment_viability_scores(
                    state,
                    candidates,
                    values["segment_length"],
                    values["maximum_horizon"],
                )
                self.assertEqual(
                    {action.name: score for action, score in scores.items()},
                    expected["robust_scores"],
                )
                robust = frozenset(
                    action.name for action, score in scores.items() if score
                )
                self.assertEqual(robust, frozenset(expected["robust_actions"]))
                self.assertIn("right", viable)
                self.assertEqual(expected["nominal_actions"], ["right"])
                self.assertNotIn("right", robust)

    @unittest.skipUnless(os.name == "nt", "native policy needs Windows")
    def test_native_repeated_pickup_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "delivery_segment_viability"
        )
        self.assertTrue(cases, "repeated-pickup corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                expected = case["expect"]
                state = decode_snapshot(values["snapshot"])
                hard = kernel.certify_selected(
                    state,
                    values["segment_length"],
                    CONTROL_ACTIONS,
                    collision_margin=0.35,
                )
                viable = frozenset(expected["replanning_viable"])
                candidates = tuple(
                    candidate for candidate in hard
                    if candidate.action.name in viable
                )
                p8 = kernel.replanning_viability_budgeted(
                    state,
                    candidates,
                    values["segment_length"],
                    8,
                    collision_margin=0.35,
                    budget_ms=1000.0,
                )
                robust8 = kernel.delivery_segment_viability_progressive(
                    state,
                    candidates,
                    values["segment_length"],
                    8,
                    8,
                    collision_margin=0.35,
                    budget_ms=1000.0,
                )
                self.assertEqual(robust8[1], p8)
                robust = None
                for horizon in range(8, values["maximum_horizon"] + 1):
                    robust = kernel.delivery_segment_viability_progressive(
                        state,
                        candidates,
                        values["segment_length"],
                        horizon,
                        horizon,
                        collision_margin=0.35,
                        budget_ms=1000.0,
                    )
                    reference = delivery_segment_viability_scores(
                        state,
                        candidates,
                        values["segment_length"],
                        horizon,
                    )
                    self.assertEqual(robust[1], reference)
                self.assertIsNotNone(robust)
                self.assertEqual(
                    {action.name: score for action, score in robust[1].items()},
                    expected["robust_scores"],
                )
                expired = kernel.delivery_segment_viability_progressive(
                    state,
                    candidates,
                    values["segment_length"],
                    values["minimum_horizon"],
                    values["maximum_horizon"],
                    collision_margin=0.35,
                    budget_ms=0.000001,
                )
                self.assertIsNone(expired)

    def test_anytime_policy_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "anytime_policy"
        )
        self.assertTrue(cases, "anytime policy corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                solver = Solver(decision_budget_ms=100.0)
                solver.effort.rollout_ms_per_work = 0.0
                decision = None
                for offset in range(case["input"]["warmup_decisions"]):
                    decision = solver.decide(
                        replace(state, frame=state.frame + offset)
                    )
                self.assertIsNotNone(decision)
                expected_action = ACTION_BY_NAME[case["expect"]["action"]]
                self.assertEqual(
                    (decision.action.dx, decision.action.dy),
                    (expected_action.dx, expected_action.dy),
                )
                self.assertGreaterEqual(
                    decision.effort_horizon,
                    case["expect"]["effort_horizon"],
                )

    def test_anytime_solver_keeps_physical_snapshots_inside_hard_authority(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("snapshot") is not None
            or case.get("input", {}).get("snapshot") is not None
        )
        self.assertTrue(cases, "physical snapshot corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                raw = case.get("snapshot") or case["input"]["snapshot"]
                state = decode_snapshot(raw)
                hard = certify_actions(
                    state,
                    4,
                    actions=CONTROL_ACTIONS,
                )
                decision = Solver(decision_budget_ms=0.001).decide(state)
                if hard:
                    self.assertEqual(
                        tuple(candidate.action for candidate in decision.safe_actions),
                        tuple(candidate.action for candidate in hard),
                    )
                    self.assertIn(
                        decision.action,
                        {candidate.action for candidate in hard},
                    )
                else:
                    self.assertEqual(
                        decision.reason,
                        "hard-safe-set-empty",
                    )
                    if decision.action is not None:
                        self.assertIn(
                            decision.action,
                            {
                                candidate.action
                                for candidate in decision.safe_actions
                            },
                        )

    def test_action_factor_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "action_factor"
        )
        self.assertTrue(cases, "action-factor corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                expected = case["expect"]
                state = decode_snapshot(values["snapshot"])
                focused = certify_actions(
                    state,
                    values["hard_horizon"],
                    actions=ACTIONS,
                )
                control = certify_actions(
                    state,
                    values["hard_horizon"],
                    actions=CONTROL_ACTIONS,
                )
                constant = certify_actions(
                    state,
                    values["constant_horizon"],
                    actions=CONTROL_ACTIONS,
                )
                self.assertEqual(
                    [candidate.action.name for candidate in focused],
                    expected["focused_actions_h4"],
                )
                self.assertEqual(
                    [candidate.action.name for candidate in control],
                    expected["control_actions_h4"],
                )
                self.assertEqual(
                    [candidate.action.name for candidate in constant],
                    expected["constant_actions_h16"],
                )

    def test_ecl_forecast_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "ecl_forecast"
        )
        self.assertTrue(cases, "ECL forecast corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                horizon = case["input"]["horizon"]
                positions = ((state.x, state.y),) * horizon
                for mode in ("fail-closed", "nominal"):
                    forecast = forecast_world_births(
                        state, positions, rng_mode=mode
                    )
                    self.assertEqual(
                        forecast.covered_frames,
                        case["expect"]["covered_frames"][mode],
                        forecast.reason,
                    )
                    self.assertEqual(
                        [len(frame) for frame in forecast.births],
                        case["expect"]["birth_counts"][mode],
                    )

    def test_future_frontier_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "future_frontier"
        )
        self.assertTrue(cases, "future frontier corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                for horizon, expected in case["expect"]["actions_by_horizon"].items():
                    actual = certify_actions(state, int(horizon))
                    self.assertEqual(
                        sorted(candidate.action.name for candidate in actual),
                        sorted(expected),
                    )
                required_held_horizon = case["expect"].get(
                    "required_held_horizon"
                )
                if required_held_horizon is not None:
                    current = action_from_input(state.input_mask)
                    self.assertEqual(
                        current.name,
                        case["expect"]["observed_current_action"],
                    )
                    decision = Solver(decision_budget_ms=1e-9).decide(state)
                    self.assertGreaterEqual(
                        decision.held_horizon,
                        required_held_horizon,
                    )
                    self.assertTrue(
                        covered_current_retry(
                            state.frame,
                            state.frame
                            + case["expect"]["observed_delivery_age"],
                            decision.held_horizon,
                            current,
                            decision.safe_actions,
                        )
                    )

    def test_constant_policy_conflict_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "constant_policy_conflict"
        )
        self.assertTrue(cases, "constant/policy conflict corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                expected = case["expect"]
                state = decode_snapshot(values["snapshot"])
                hard = certify_actions(state, values["hard_horizon"])
                constant = certify_actions(
                    state, values["constant_horizon"]
                )
                scores = nominal_policy_scores(
                    state,
                    hard,
                    values["segment_length"],
                    values["policy_horizon"],
                )
                best = max(scores.values(), default=0)
                self.assertEqual(
                    [candidate.action.name for candidate in hard],
                    expected["hard_actions"],
                )
                self.assertEqual(
                    [candidate.action.name for candidate in constant],
                    expected["constant_actions"],
                )
                self.assertEqual(
                    {action.name: score for action, score in scores.items()},
                    expected["policy_scores"],
                )
                self.assertEqual(
                    [
                        action.name for action, score in scores.items()
                        if score == best
                    ],
                    expected["policy_best_actions"],
                )

    @unittest.skipUnless(os.name == "nt", "native policy needs Windows")
    def test_native_constant_policy_conflict_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "constant_policy_conflict"
        )
        self.assertTrue(cases, "constant/policy conflict corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                expected = case["expect"]
                state = decode_snapshot(values["snapshot"])
                hard = kernel.certify(
                    state,
                    values["hard_horizon"],
                    collision_margin=0.35,
                )
                constant = kernel.certify(
                    state,
                    values["constant_horizon"],
                    collision_margin=0.35,
                )
                scores = kernel.nominal_policy_counts(
                    state,
                    hard,
                    values["segment_length"],
                    values["policy_horizon"],
                    collision_margin=0.35,
                )
                self.assertEqual(
                    [candidate.action.name for candidate in constant],
                    expected["constant_actions"],
                )
                self.assertEqual(
                    {action.name: score for action, score in scores.items()},
                    expected["policy_scores"],
                )

    @unittest.skipUnless(os.name == "nt", "native macro corpus needs Windows")
    def test_native_coarse_macro_tail_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "coarse_macro_tail"
        )
        self.assertTrue(cases, "coarse macro-tail corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                expected = case["expect"]
                state = decode_snapshot(values["snapshot"])
                hard, _age_zero = kernel.certify_selected_delivery_sets(
                    state,
                    values["segment_length"],
                    CONTROL_ACTIONS,
                    collision_margin=0.35,
                )
                self.assertEqual(len(hard), expected["hard_count"])
                local_horizon, local_scores, _complete = (
                    kernel.segment_terminal_counts_progressive(
                        state,
                        hard,
                        values["segment_length"],
                        8,
                        values["local_horizon"],
                        collision_margin=0.35,
                        budget_ms=1000.0,
                    )
                )
                self.assertEqual(local_horizon, values["local_horizon"])
                local_best = max(local_scores.values())
                local_actions = frozenset(
                    action for action, score in local_scores.items()
                    if score == local_best
                )
                self.assertEqual(
                    sorted(action.name for action in local_actions),
                    sorted(expected["local_actions"]),
                )
                constant = kernel.certify_selected(
                    state,
                    values["coarse_horizon"],
                    tuple(candidate.action for candidate in hard),
                    collision_margin=0.35,
                )
                self.assertEqual(
                    [candidate.action.name for candidate in constant],
                    expected["constant_actions"],
                )
                shortlist_actions = local_actions | frozenset(
                    candidate.action for candidate in constant
                )
                shortlist = tuple(
                    candidate for candidate in hard
                    if candidate.action in shortlist_actions
                )
                macro_scores = kernel.macro_tail_scores_budgeted(
                    state,
                    shortlist,
                    values["segment_length"],
                    values["coarse_horizon"],
                    collision_margin=0.35,
                    budget_ms=1000.0,
                )
                self.assertEqual(
                    {action.name: score for action, score in macro_scores.items()},
                    expected["macro_scores"],
                )
                macro_best = max(macro_scores.values())
                self.assertEqual(
                    sorted(
                        action.name for action, score in macro_scores.items()
                        if score == macro_best
                    ),
                    sorted(expected["macro_actions"]),
                )

    @unittest.skipUnless(os.name == "nt", "native held authority needs Windows")
    def test_native_current_hold_authority_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("expect", {}).get("required_held_horizon")
            is not None
        )
        self.assertTrue(cases, "current hold authority corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                current = action_from_input(state.input_mask)
                held_horizon = case["expect"]["required_held_horizon"]
                hard, _age_zero, held = (
                    kernel.certify_delivery_sets_with_selected(
                        state,
                        4,
                        held_horizon,
                        (current,),
                        collision_margin=0.35,
                    )
                )
                self.assertEqual(
                    sorted(candidate.action.name for candidate in hard),
                    sorted(
                        candidate.action.name
                        for candidate in certify_actions(
                            state,
                            4,
                            actions=CONTROL_ACTIONS,
                        )
                    ),
                )
                self.assertEqual(
                    tuple(candidate.action for candidate in held),
                    (current,),
                )

    def test_frontier_precedence_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "frontier_precedence"
        )
        self.assertTrue(cases, "frontier precedence corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                hard = certify_actions(
                    state, case["input"]["hard_horizon"]
                )
                deep = certify_actions(
                    state, case["input"]["deep_horizon"]
                )
                hard_names = {candidate.action.name for candidate in hard}
                deep_names = {candidate.action.name for candidate in deep}
                shallow = case["input"]["shallow_proposal"]
                self.assertIn(shallow, hard_names)
                self.assertNotIn(shallow, deep_names)
                self.assertEqual(
                    sorted(deep_names),
                    sorted(case["expect"]["frontier_actions"]),
                )
                scores = nominal_policy_scores(
                    state,
                    hard,
                    case["input"]["segment_length"],
                    case["input"]["deep_horizon"],
                )
                best = max(scores.values(), default=0)
                self.assertEqual(
                    sorted(
                        action.name
                        for action, score in scores.items()
                        if score == best
                    ),
                    sorted(case["expect"]["policy_best_actions"]),
                )

    def test_physical_ranking_sequences(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "ranking_sequence"
        )
        self.assertTrue(cases, "ranking sequence corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                ranker = ProposalRanker()
                for step in case["input"]["steps"]:
                    state = Snapshot(
                        frame=step["frame"],
                        stage=3,
                        player_state=0,
                        x=step["x"],
                        y=step["y"],
                        half_width=1.25,
                        half_height=1.25,
                        normal_speed=4.0,
                        focus_speed=2.0,
                        normal_diagonal_speed=2.8284270763397217,
                        focus_diagonal_speed=1.4142135381698608,
                        frame_multiplier=1.0,
                        input_mask=step["input_mask"],
                        bullets=(),
                        laser_count=0,
                        in_menu=False,
                        time_stopped=False,
                        replay_or_demo=False,
                    )
                    candidates = tuple(
                        SafeAction(ACTION_BY_NAME[name], clearance, x, y)
                        for name, clearance, x, y in step["candidates"]
                    )
                    chosen = ranker.choose(
                        state,
                        candidates,
                        preferred_actions=frozenset(
                            ACTION_BY_NAME[name]
                            for name in step["durable_actions"]
                        ),
                        commitment_frames=case["input"]["repair_span"],
                    )
                    self.assertEqual(
                        chosen.action,
                        ACTION_BY_NAME[step["expect_action"]],
                    )

    def test_delivery_publication_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "delivery_publication"
        )
        self.assertTrue(cases, "delivery publication corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                delivery_age = bounded_delivery_age(
                    case["input"]["snapshot_frame"],
                    case["input"]["observed_frame"],
                )
                self.assertIsNotNone(delivery_age)
                self.assertEqual(
                    required_changed_action_delivery_delay(delivery_age),
                    case["expect"]["required_max_delay"],
                )
                supported = changed_action_delivery_supported(
                    delivery_age,
                    ACTION_BY_NAME[case["input"]["current_action"]],
                    ACTION_BY_NAME[case["input"]["proposed_action"]],
                    case["input"].get("certified_max_delay", 3),
                )
                self.assertEqual(supported, case["expect"]["publish"])

    @unittest.skipUnless(os.name == "nt", "native policy corpus needs Windows")
    def test_native_policy_volume_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "native_policy_volume"
        )
        self.assertTrue(cases, "native policy corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                hard = kernel.certify(state, 4, collision_margin=0.35)
                scores = kernel.nominal_policy_counts(
                    state,
                    hard,
                    case["input"]["segment_length"],
                    case["input"]["horizon"],
                    collision_margin=0.35,
                )
                best_score = max(scores.values(), default=0)
                self.assertEqual(best_score, case["expect"]["best_score"])
                self.assertEqual(
                    sorted(
                        action.name for action, score in scores.items()
                        if score == best_score
                    ),
                    sorted(case["expect"]["actions"]),
                )
                observed = case["expect"]["observed_dead_end"]
                self.assertEqual(
                    scores[ACTION_BY_NAME[observed["action"]]],
                    observed["score"],
                )

    def test_reference_policy_volume_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "native_policy_volume"
        )
        self.assertTrue(cases, "policy volume corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                hard = certify_actions(state, 4)
                scores = nominal_policy_scores(
                    state,
                    hard,
                    case["input"]["segment_length"],
                    case["input"]["horizon"],
                )
                best_score = max(scores.values(), default=0)
                self.assertEqual(best_score, case["expect"]["best_score"])
                self.assertEqual(
                    sorted(
                        action.name for action, score in scores.items()
                        if score == best_score
                    ),
                    sorted(case["expect"]["actions"]),
                )
                observed = case["expect"]["observed_dead_end"]
                self.assertEqual(
                    scores[ACTION_BY_NAME[observed["action"]]],
                    observed["score"],
                )
                solver_expect = case["expect"].get("solver")
                if solver_expect is not None:
                    solver = Solver(decision_budget_ms=100.0)
                    solver.effort.rollout_ms_per_work = 0.0
                    decision = None
                    for offset in range(solver_expect["warmup_decisions"]):
                        decision = solver.decide(
                            replace(state, frame=state.frame + offset)
                        )
                    self.assertIsNotNone(decision)
                    expected_action = ACTION_BY_NAME[
                        solver_expect["action"]
                    ]
                    self.assertEqual(
                        (decision.action.dx, decision.action.dy),
                        (expected_action.dx, expected_action.dy),
                    )
                    self.assertGreaterEqual(
                        decision.effort_horizon,
                        solver_expect["effort_horizon"],
                    )

    def test_reference_policy_horizon_divergence_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "policy_horizon_divergence"
        )
        self.assertTrue(cases, "policy horizon divergence corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                hard = certify_actions(state, 4)
                hard_expect = case["expect"].get("hard_actions")
                if hard_expect is not None:
                    self.assertEqual(
                        [candidate.action.name for candidate in hard],
                        hard_expect,
                    )
                constants_by_horizon = {}
                for horizon, expected in case["expect"].get(
                    "constant_actions_by_horizon",
                    {},
                ).items():
                    constant = certify_actions(state, int(horizon))
                    constants_by_horizon[int(horizon)] = constant
                    self.assertEqual(
                        sorted(candidate.action.name for candidate in constant),
                        sorted(expected),
                    )
                scores_by_horizon = {}
                for horizon in case["input"]["horizons"]:
                    scores = nominal_policy_scores(
                        state,
                        hard,
                        case["input"]["segment_length"],
                        horizon,
                    )
                    scores_by_horizon[horizon] = scores
                    best_score = max(scores.values(), default=0)
                    self.assertEqual(
                        best_score,
                        case["expect"]["best_score_by_horizon"][
                            str(horizon)
                        ],
                    )
                    self.assertEqual(
                        sorted(
                            action.name for action, score in scores.items()
                            if score == best_score
                        ),
                        sorted(
                            case["expect"]["actions_by_horizon"][
                                str(horizon)
                            ]
                        ),
                    )
                shortlist_expect = case["expect"].get("deep_shortlist")
                if shortlist_expect is not None:
                    lower_scores = scores_by_horizon[
                        shortlist_expect["lower_horizon"]
                    ]
                    lower_best = max(lower_scores.values(), default=0)
                    constant_actions = {
                        candidate.action for candidate in constants_by_horizon[
                            shortlist_expect["deep_horizon"]
                        ]
                    }
                    shortlist_actions = (
                        {
                            action for action, score in lower_scores.items()
                            if score == lower_best
                        }
                        | constant_actions
                    )
                    if (
                        not constant_actions
                        or shortlist_expect.get("retain_current", False)
                    ):
                        shortlist_actions.add(action_from_input(state.input_mask))
                    self.assertEqual(
                        sorted(action.name for action in shortlist_actions),
                        sorted(shortlist_expect["actions"]),
                    )
                    shortlist = tuple(
                        candidate for candidate in hard
                        if candidate.action in shortlist_actions
                    )
                    deep_scores = nominal_policy_scores(
                        state,
                        shortlist,
                        case["input"]["segment_length"],
                        shortlist_expect["deep_horizon"],
                    )
                    deep_best = max(deep_scores.values(), default=0)
                    self.assertEqual(deep_best, shortlist_expect["best_score"])
                    self.assertEqual(
                        sorted(
                            action.name for action, score in deep_scores.items()
                            if score == deep_best
                        ),
                        sorted(shortlist_expect["best_actions"]),
                    )
                fallback_action = case["expect"].get("fallback_action")
                if fallback_action is not None:
                    chosen = ProposalRanker().choose(state, hard)
                    self.assertEqual(
                        chosen.action,
                        ACTION_BY_NAME[fallback_action],
                    )

    def test_preferred_policy_ties_use_source_defined_free_space(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "policy_tie_free_space"
        )
        self.assertTrue(cases, "policy free-space tie corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                hard = certify_actions(state, 4)
                scores = nominal_policy_scores(
                    state,
                    hard,
                    case["input"]["segment_length"],
                    case["input"]["horizon"],
                )
                best_score = max(scores.values(), default=0)
                preferred = frozenset(
                    action for action, score in scores.items()
                    if score == best_score
                )
                expected = case["expect"]
                self.assertEqual(best_score, expected["best_score"])
                self.assertEqual(
                    sorted(action.name for action in preferred),
                    sorted(expected["actions"]),
                )

                ranker = ProposalRanker()
                ranker.committed_action = ACTION_BY_NAME[
                    expected["observed_committed_action"]
                ]
                ranker.commit_until_frame = state.frame + 4
                ranker.last_frame = state.frame - 1
                chosen = ranker.choose(state, hard, preferred)

                self.assertEqual(
                    chosen.action,
                    ACTION_BY_NAME[expected["chosen_action"]],
                )

    @unittest.skipUnless(os.name == "nt", "native policy needs Windows")
    def test_native_policy_horizon_divergence_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "policy_horizon_divergence"
        )
        self.assertTrue(cases, "policy horizon divergence corpus is empty")
        kernel = NativeSafetyKernel()
        for case in cases:
            with self.subTest(case=case["id"]):
                state = decode_snapshot(case["input"]["snapshot"])
                hard = kernel.certify(state, 4, collision_margin=0.35)
                hard_expect = case["expect"].get("hard_actions")
                if hard_expect is not None:
                    self.assertEqual(
                        [candidate.action.name for candidate in hard],
                        hard_expect,
                    )
                constants_by_horizon = {}
                for horizon, expected in case["expect"].get(
                    "constant_actions_by_horizon",
                    {},
                ).items():
                    constant = kernel.certify(
                        state,
                        int(horizon),
                        collision_margin=0.35,
                    )
                    constants_by_horizon[int(horizon)] = constant
                    self.assertEqual(
                        sorted(candidate.action.name for candidate in constant),
                        sorted(expected),
                    )
                scores_by_horizon = {}
                for horizon in case["input"]["horizons"]:
                    scores = kernel.nominal_policy_counts(
                        state,
                        hard,
                        case["input"]["segment_length"],
                        horizon,
                        collision_margin=0.35,
                    )
                    scores_by_horizon[horizon] = scores
                    best_score = max(scores.values(), default=0)
                    self.assertEqual(
                        best_score,
                        case["expect"]["best_score_by_horizon"][
                            str(horizon)
                        ],
                    )
                    self.assertEqual(
                        sorted(
                            action.name for action, score in scores.items()
                            if score == best_score
                        ),
                        sorted(
                            case["expect"]["actions_by_horizon"][
                                str(horizon)
                            ]
                        ),
                    )
                shortlist_expect = case["expect"].get("deep_shortlist")
                if shortlist_expect is not None:
                    lower_scores = scores_by_horizon[
                        shortlist_expect["lower_horizon"]
                    ]
                    lower_best = max(lower_scores.values(), default=0)
                    constant_actions = {
                        candidate.action for candidate in constants_by_horizon[
                            shortlist_expect["deep_horizon"]
                        ]
                    }
                    shortlist_actions = (
                        {
                            action for action, score in lower_scores.items()
                            if score == lower_best
                        }
                        | constant_actions
                    )
                    if (
                        not constant_actions
                        or shortlist_expect.get("retain_current", False)
                    ):
                        shortlist_actions.add(action_from_input(state.input_mask))
                    self.assertEqual(
                        sorted(action.name for action in shortlist_actions),
                        sorted(shortlist_expect["actions"]),
                    )
                    shortlist = tuple(
                        candidate for candidate in hard
                        if candidate.action in shortlist_actions
                    )
                    deep_scores = kernel.nominal_policy_counts(
                        state,
                        shortlist,
                        case["input"]["segment_length"],
                        shortlist_expect["deep_horizon"],
                        collision_margin=0.35,
                    )
                    deep_best = max(deep_scores.values(), default=0)
                    self.assertEqual(deep_best, shortlist_expect["best_score"])
                    self.assertEqual(
                        sorted(
                            action.name for action, score in deep_scores.items()
                            if score == deep_best
                        ),
                        sorted(shortlist_expect["best_actions"]),
                    )


if __name__ == "__main__":
    unittest.main()

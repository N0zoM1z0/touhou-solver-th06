import os
import unittest

from counterexample_corpus import (
    ACTION_BY_NAME,
    decode_snapshot,
    load_cases,
)
from th06.input_lease import (
    bounded_delivery_age,
    changed_action_delivery_supported,
    required_changed_action_delivery_delay,
)
from th06.hazards.world import forecast_world_births
from th06.model import SafeAction, Snapshot
from th06.ranking import ProposalRanker
from th06.kernels.safety import NativeSafetyKernel
from th06.safety import certify_actions
from th06.solver import Solver


class CounterexampleCorpusTests(unittest.TestCase):
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
                hard = certify_actions(state, 4)
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
                    self.assertIn(
                        decision.reason,
                        ("hard-safe-set-empty", "same-frame-delivery-only"),
                    )
                    if decision.action is not None:
                        self.assertIn(
                            decision.action,
                            {
                                candidate.action
                                for candidate in decision.safe_actions
                            },
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


if __name__ == "__main__":
    unittest.main()

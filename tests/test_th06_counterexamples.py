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
from th06.barrage_lab.stateful import step_nominal_battle_world
from th06.hazards.ecl import source_enemy_template
from th06.hazards.world import forecast_world_births
from th06.hazards.timeline import scheduled_timeline
from th06.model import (
    ACTIONS,
    CONTROL_ACTIONS,
    Bullet,
    EclInstruction,
    MessageInstruction,
    PlayerAttackState,
    SafeAction,
    Snapshot,
    StageTimelineInstruction,
    action_from_input,
)
from th06.native import _message_minimum_waits
from th06.ranking import ProposalRanker
from th06.kernels.safety import NativeSafetyKernel
from th06.routes.stage4_hard_reimu_a import timeline_phase
from th06.routes.stage1_hard_reimu_a import RANDOM_BODY_STREAM
from th06.safety import certify_actions
from th06.viability import (
    delivery_segment_viability_scores,
    nominal_policy_scores,
)


class CounterexampleCorpusTests(unittest.TestCase):
    def test_stage1_phase_policy_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "stage1_phase_policy"
        )
        self.assertTrue(cases, "Stage 1 phase-policy corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                state = RANDOM_BODY_STREAM.state(
                    case["input"]["timeline_time"]
                )
                expected = case["expect"]
                self.assertEqual(
                    RANDOM_BODY_STREAM.phase_id, expected["phase_id"]
                )
                self.assertEqual(state.state_id, expected["policy_state"])
                self.assertEqual(state.algorithm, expected["algorithm"])
                self.assertEqual(state.horizon, expected["horizon"])
                self.assertEqual(state.target, expected["target"])

    def test_nominal_spell_start_transition_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "nominal_spell_start_transition"
        )
        self.assertTrue(cases, "spell-start transition corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                program = tuple(
                    EclInstruction(**instruction)
                    for instruction in values["ecl_program"]
                )
                emitter = source_enemy_template(
                    program,
                    (program[0].address,),
                    0,
                    values["enemy"][0],
                    values["enemy"][1],
                    500,
                )
                self.assertIsNotNone(emitter)
                emitter = replace(
                    emitter,
                    slot=0,
                    is_boss=True,
                    boss_id=0,
                    has_been_in_bounds=True,
                )
                player_x, player_y = values["player"]
                attack = PlayerAttackState(
                    shots=(),
                    last_enemy_hit_x=-999.0,
                    last_enemy_hit_y=-999.0,
                    orb_state=3,
                    is_focus=True,
                    focus_timer_previous=-999,
                    focus_timer=0,
                    focus_timer_float=0.0,
                    fire_timer_previous=1,
                    fire_timer=2,
                    fire_timer_float=2.0,
                    orb_positions=(
                        (player_x - 8.0, player_y - 32.0),
                        (player_x + 8.0, player_y - 32.0),
                    ),
                    shot_type=0,
                    bomb_active=False,
                    spell_active=False,
                )
                root = Snapshot(
                    frame=case["origin"]["failure_frame"],
                    stage=case["origin"]["stage"],
                    player_state=0,
                    x=player_x,
                    y=player_y,
                    half_width=1.25,
                    half_height=1.25,
                    normal_speed=4.0,
                    focus_speed=2.0,
                    normal_diagonal_speed=2.8284270763397217,
                    focus_diagonal_speed=1.4142135381698608,
                    frame_multiplier=1.0,
                    input_mask=0x05,
                    bullets=tuple(Bullet(**bullet) for bullet in values["bullets"]),
                    laser_count=0,
                    in_menu=False,
                    time_stopped=False,
                    replay_or_demo=False,
                    spawners=(emitter,),
                    difficulty=2,
                    rank=16,
                    bullet_sizes=((3.0, 3.0),) * 16,
                    rng_seed=0x1234,
                    rng_generation=100,
                    current_power=9,
                    timeline_complete=True,
                    player_attack=attack,
                    effect_active_upper_bound=0,
                    item_active_upper_bound=0,
                    item_next_index=values["item_next_index"],
                )
                following = step_nominal_battle_world(
                    root, ACTION_BY_NAME["stay"]
                )
                expected = case["expect"]
                self.assertEqual(len(following.bullets), expected["bullet_count"])
                self.assertEqual(
                    [item.slot for item in following.item_states],
                    expected["item_slots"],
                )
                self.assertEqual(
                    [item.item_type for item in following.item_states],
                    expected["item_types"],
                )
                self.assertEqual(
                    [item.timer for item in following.item_states],
                    expected["item_timers"],
                )
                self.assertEqual(
                    following.item_next_index, expected["item_next_index"]
                )
                self.assertEqual(
                    following.item_active_upper_bound,
                    expected["item_active_upper_bound"],
                )
                self.assertEqual(
                    following.player_attack.spell_active,
                    expected["spell_active"],
                )
                self.assertEqual(
                    following.rng_generation, root.rng_generation
                )

    def test_stage4_phase_policy_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "stage4_phase_policy"
        )
        self.assertTrue(cases, "Stage 4 phase-policy corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                source_time = case["input"]["timeline_time"]
                machine = timeline_phase(source_time)
                state = machine.state(source_time)
                expected = case["expect"]
                self.assertEqual(machine.phase_id, expected["phase_id"])
                self.assertEqual(state.state_id, expected["policy_state"])
                self.assertEqual(state.algorithm, expected["algorithm"])
                self.assertEqual(state.horizon, expected["horizon"])
                if "target" in expected:
                    target = expected["target"]
                    self.assertEqual(
                        state.target,
                        tuple(target) if target is not None else None,
                    )

    def test_timeline_schedule_counterexamples(self):
        cases = tuple(
            case for case in load_cases()
            if case.get("runner") == "timeline_schedule"
        )
        self.assertTrue(cases, "timeline schedule corpus is empty")
        for case in cases:
            with self.subTest(case=case["id"]):
                values = case["input"]
                message = tuple(
                    MessageInstruction(**instruction)
                    for instruction in values["message_program"]
                )
                waits = _message_minimum_waits(message)
                self.assertEqual(waits, case["expect"]["message_waits"])
                timeline = tuple(
                    StageTimelineInstruction(**instruction)
                    for instruction in values["timeline"]
                )
                schedule = scheduled_timeline(
                    timeline,
                    values["current_time"],
                    stage=values["stage"],
                    difficulty=values["difficulty"],
                    character=values["character"],
                    message_delays=((values["message_index"], waits),),
                )
                self.assertEqual(
                    [
                        {"lead": lead, "opcode": instruction.opcode}
                        for lead, instruction in schedule
                    ],
                    case["expect"]["schedule"],
                )

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
                    if mode == "nominal" and (
                        expected_slots := case["expect"].get(
                            "nominal_continuation_slots"
                        )
                    ) is not None:
                        self.assertIsNotNone(forecast.continuation)
                        self.assertEqual(
                            [
                                emitter.slot for emitter
                                in forecast.continuation.emitters
                            ],
                            expected_slots,
                        )
                        self.assertEqual(
                            [
                                emitter.ecl_time for emitter
                                in forecast.continuation.emitters
                            ],
                            case["expect"][
                                "nominal_continuation_ecl_times"
                            ],
                        )
                        self.assertEqual(
                            forecast.continuation.rng_generation,
                            case["expect"]["nominal_rng_generation"],
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
                    hard = certify_actions(
                        state, 4, actions=CONTROL_ACTIONS
                    )
                    held = certify_actions(
                        state,
                        required_held_horizon,
                        actions=(current,),
                    )
                    self.assertTrue(held)
                    self.assertTrue(
                        covered_current_retry(
                            state.frame,
                            state.frame
                            + case["expect"]["observed_delivery_age"],
                            required_held_horizon,
                            current,
                            hard,
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

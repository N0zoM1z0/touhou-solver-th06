"""Thin runtime loop for the TH06 baseline."""

from __future__ import annotations

import argparse
from collections import deque
import csv
import ctypes
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .actuator import Keyboard
from .dialogue import DialogueSkipper, DialogueState
from .hazards.lasers import track_motion as track_laser_motion
from .input_lease import (
    BASE_CERTIFIED_DELIVERY_MAX_FRAMES,
    InputLease,
    bounded_delivery_age,
    changed_action_delivery_supported,
    covered_current_retry,
    required_changed_action_delivery_delay,
)
from .menu import start_hard_reimu_a, start_hard_reimu_a_practice
from .model import Decision, PLAYER_ALIVE, PLAYER_DEAD, Snapshot, action_from_input
from .native import (
    ADDR_LIFE_PATCH,
    NativeDecodeError,
    TARGET_SHA256,
    attach_exact,
    read_game_frame,
    read_snapshot,
    read_supervisor_state,
)
from .replay import ReplaySaver
from .solver import HARD_SAFETY_HORIZON, Solver
from .trial import PracticeTrial, physical_hit, stop_trial_now


PASSIVE_NO_ACTION_REASONS = frozenset(("menu", "player-not-active", "time-stopped"))


def _emitter_trace(snapshot: Snapshot) -> str:
    """Compact mutable ECL state; immutable instructions are dumped once."""
    fields = []
    for emitter in snapshot.spawners:
        instruction = emitter.next_instruction
        fields.append(":".join((
            str(emitter.slot),
            f"0x{instruction.address:08X}" if instruction is not None else "none",
            str(emitter.ecl_time),
            str(emitter.interval),
            str(emitter.timer),
            str(emitter.death_mode),
            str(emitter.repeat_ex_index),
            "/".join(map(str, emitter.ecl_ints)),
        )))
    return "|".join(fields)


def _prioritize_control_loop() -> None:
    """Reduce Windows scheduling stalls without using realtime priority."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = ()
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetCurrentThread.argtypes = ()
    kernel32.GetCurrentThread.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.SetPriorityClass.restype = ctypes.c_int
    kernel32.SetThreadPriority.argtypes = (ctypes.c_void_p, ctypes.c_int)
    kernel32.SetThreadPriority.restype = ctypes.c_int
    # HIGH_PRIORITY_CLASS plus THREAD_PRIORITY_HIGHEST bounds the safety-loop
    # tail more tightly while leaving the game and operating system outside
    # dangerous REALTIME_PRIORITY_CLASS scheduling.
    if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00000080):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel32.SetThreadPriority(kernel32.GetCurrentThread(), 2):
        raise ctypes.WinError(ctypes.get_last_error())


def authority_unavailable(decision: Decision) -> bool:
    """Distinguish missing hard authority from a passive gameplay phase."""
    return decision.action is None and decision.reason not in PASSIVE_NO_ACTION_REASONS


def run(args: argparse.Namespace) -> int:
    if os.name != "nt":
        raise RuntimeError("run this entry point with Windows Python")
    if args.start_hard and not args.armed:
        raise RuntimeError("--start-hard requires --armed")
    if args.practice_stage is not None and not args.armed:
        raise RuntimeError("--practice-stage requires --armed")
    if args.start_hard and args.practice_stage is not None:
        raise RuntimeError("choose either --start-hard or --practice-stage")
    if args.save_replay and not args.armed:
        raise RuntimeError("--save-replay requires --armed")
    if args.save_replay and args.practice_stage is not None:
        raise RuntimeError("the exact game cannot save Practice replays")
    if args.continue_on_failure and args.practice_stage is None:
        raise RuntimeError("--continue-on-failure is Practice-only")
    if args.continue_on_failure and not args.patch_lives:
        raise RuntimeError("--continue-on-failure requires --patch-lives")
    if args.rng_seed is not None and not args.armed:
        raise RuntimeError("--rng-seed requires --armed")
    if (
        args.rng_seed is not None
        and not args.start_hard
        and args.practice_stage is None
    ):
        raise RuntimeError("--rng-seed requires a fresh menu-started trial")
    _prioritize_control_loop()
    process = attach_exact(Path(args.game_dir).resolve())
    keyboard = Keyboard(process.pid) if args.armed else None
    dialogue_skipper = DialogueSkipper(process, keyboard) if keyboard is not None else None
    replay_saver = (
        ReplaySaver(Path(args.game_dir).resolve(), keyboard, args.replay_name, args.replay_slot)
        if args.save_replay and keyboard is not None
        else None
    )
    rng_suffix = (
        f"_rng{args.rng_seed:04x}" if args.rng_seed is not None else ""
    )
    if args.practice_stage is not None:
        trace_name = (
            f"th06_practice_stage{args.practice_stage}{rng_suffix}_latest.csv"
        )
    else:
        trace_name = (
            f"th06_baseline{rng_suffix}_latest.csv"
            if args.armed else "th06_observe_latest.csv"
        )
    trace_path = Path(__file__).resolve().parents[2] / "artifacts" / trace_name
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostic_path = trace_path.with_name(
        f"{trace_path.stem}_diagnostic_events.json"
    )
    diagnostic_events: list[dict] = []
    diagnostic_failure_active = False
    if args.continue_on_failure:
        diagnostic_path.write_text("[]\n", encoding="utf-8")
    solver = Solver()
    input_lease = InputLease()
    previous_state: int | None = None
    previous_snapshot: Snapshot | None = None
    # A rotating-laser failure can become geometrically unavoidable more than
    # one second after its warning phase.  Keep enough source-grounded state
    # to find the first still-viable decision, not merely the final empty set.
    snapshot_history: deque[Snapshot] = deque(maxlen=256)
    practice_trial = PracticeTrial() if args.practice_stage is not None else None
    last_frame: int | None = None
    last_reason: str | None = None
    exit_code = 0
    started = time.monotonic()
    trial_stopped = False

    def stop_immediately() -> None:
        nonlocal trial_stopped
        if trial_stopped:
            return
        trial_stopped = True
        stop_trial_now(process, keyboard, args.stop_game)

    def cleanup() -> None:
        try:
            stop_immediately()
        finally:
            process.close()
        cleanup_message = "released all keys" if keyboard is not None else "no input was created"
        if args.stop_game:
            cleanup_message += f"; stopped exact pid {process.pid}"
        print(f"{cleanup_message}; trace={trace_path}", flush=True)

    try:
        print(f"verified pid={process.pid} sha256={TARGET_SHA256}", flush=True)
        print(f"safety backend: {solver.backend}", flush=True)
        print("control priority: high/highest", flush=True)
        if args.patch_lives:
            print(f"life patch: {process.patch_lives()} at 0x{ADDR_LIFE_PATCH:08X}", flush=True)
        if args.rng_seed is not None:
            old_seed, old_generation = process.set_diagnostic_rng_seed(
                args.rng_seed
            )
            print(
                "diagnostic RNG: "
                f"0x{old_seed:04X}/{old_generation} -> "
                f"0x{args.rng_seed:04X}/0; source generator unchanged; "
                "not clear validation",
                flush=True,
            )
        if args.start_hard:
            assert keyboard is not None
            start_hard_reimu_a(process, keyboard)
            print("menu: Hard / Reimu-A selected", flush=True)
        elif args.practice_stage is not None:
            assert keyboard is not None
            start_hard_reimu_a_practice(process, keyboard, args.practice_stage)
            print(f"menu: Hard / Reimu-A Practice Stage {args.practice_stage} selected", flush=True)
        if replay_saver is not None:
            print(
                f"replay: reserved empty slot {replay_saver.slot:02d} name={replay_saver.name}",
                flush=True,
            )
        print("armed" if args.armed else "observe-only", flush=True)
    except Exception:
        cleanup()
        raise
    try:
        with trace_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow((
                "wall_s", "frame", "stage", "state", "x", "y", "bullets", "lasers",
                "enemies", "spawners", "emitter_state", "despawning",
                "bullet_retries",
                "rng_seed", "rng_generation", "power", "timeline_time",
                "replay", "native_input", "held_desired_input", "input_transitions",
                "decision_age", "command_issue_age",
                "input_lease",
                "frame_multiplier", "action", "safe", "horizon", "held_horizon",
                "effort_horizon",
                "effort_safe", "repairable",
                "clearance", "solve_ms",
                "dialogue", "skip", "advance_pulse", "authority_stop", "reason",
            ))
            while not args.seconds or time.monotonic() - started < args.seconds:
                if practice_trial is not None:
                    _wanted, current = read_supervisor_state(process)
                    if practice_trial.observe_supervisor(current):
                        print(
                            f"Practice Stage {args.practice_stage} reached its result path; "
                            "trial complete",
                            flush=True,
                        )
                        break
                if replay_saver is not None:
                    replay_status = replay_saver.update(process)
                    if replay_status == "saved":
                        print(f"replay: validated {replay_saver.path}", flush=True)
                        break
                    if replay_status == "active":
                        time.sleep(0.01)
                        continue
                # A full coherent snapshot walks every active native pool.
                # Poll the source stage-frame scalar first so an unchanged
                # frame does not repeatedly decode identical world state.
                if (
                    last_frame is not None
                    and read_game_frame(process) == last_frame
                ):
                    time.sleep(0.001)
                    continue
                try:
                    snapshot = read_snapshot(process)
                except NativeDecodeError as error:
                    decision = Decision(
                        None,
                        (),
                        0.0,
                        0,
                        "native-decode-error",
                    )
                    held_before_authority = (
                        keyboard.base_input_mask if keyboard is not None else 0
                    )
                    if keyboard is not None:
                        input_lease.cleared()
                    stop_immediately()
                    exit_code = 2
                    failure_path = trace_path.with_name(
                        "th06_failure_latest.json"
                        if args.rng_seed is None
                        else f"th06_failure_rng{args.rng_seed:04x}_latest.json"
                    )
                    failure_path.write_text(
                        json.dumps(
                            {
                                "wall_s": time.monotonic() - started,
                                "snapshot": None,
                                "previous_snapshot": (
                                    asdict(previous_snapshot)
                                    if previous_snapshot is not None
                                    else None
                                ),
                                "decision": asdict(decision),
                                "decode_evidence": error.evidence,
                                "held_before_stop": held_before_authority,
                                "held_desired_input": (
                                    keyboard.base_input_mask if keyboard else 0
                                ),
                            },
                            indent=2,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                    print(
                        f"authority unavailable: {error}; "
                        f"counterexample={failure_path}; stopping trial",
                        flush=True,
                    )
                    break
                if snapshot.frame == last_frame:
                    time.sleep(0.001)
                    continue
                if previous_snapshot is not None and snapshot.stage == previous_snapshot.stage:
                    snapshot = Snapshot(
                        **{
                            **snapshot.__dict__,
                            "lasers": track_laser_motion(
                                previous_snapshot.lasers,
                                snapshot.lasers,
                                snapshot.frame - previous_snapshot.frame,
                            ),
                        }
                    )
                snapshot_history.append(snapshot)
                last_frame = snapshot.frame
                prior_snapshot = previous_snapshot
                hit = physical_hit(previous_state, snapshot.player_state)
                if previous_state is not None:
                    solver.observe(not hit)
                previous_state = snapshot.player_state
                solve_started = time.perf_counter()
                lease_status = (
                    input_lease.status(snapshot.input_mask, snapshot.frame)
                    if keyboard is not None
                    else None
                )
                leased_action = lease_status.action if lease_status is not None else None
                if hit:
                    decision = Decision(
                        None,
                        (),
                        0.0,
                        HARD_SAFETY_HORIZON,
                        "physical-hit",
                        HARD_SAFETY_HORIZON,
                    )
                elif lease_status is not None and lease_status.timed_out:
                    decision = Decision(
                        None,
                        (),
                        0.0,
                        1,
                        "input-pickup-timeout",
                        1,
                    )
                else:
                    decision = solver.decide(snapshot, leased_action)
                solve_ms = (time.perf_counter() - solve_started) * 1000.0
                stale_retry = False
                dialogue = DialogueState(False, False, False)
                transition_count = 0
                decision_age = ""
                command_issue_age = ""
                authority_stop = False
                held_before_authority = keyboard.base_input_mask if keyboard is not None else 0

                if args.armed:
                    assert keyboard is not None
                    assert dialogue_skipper is not None
                    if authority_unavailable(decision):
                        transition_count += len(keyboard.release_all())
                        input_lease.cleared()
                        authority_stop = True
                        if args.continue_on_failure:
                            solver.reset_plan()
                        if not args.continue_on_failure:
                            exit_code = 2
                            # A dense counterexample can take many seconds to
                            # serialize. Stop the verified game first so it
                            # cannot continue into a visible HIT after
                            # authority ended.
                            stop_immediately()
                    elif not keyboard.foreground():
                        keyboard.release_all()
                        decision = Decision(None, (), 0.0, 0, "not-foreground")
                    else:
                        dialogue = dialogue_skipper.update(
                            not snapshot.in_menu and not snapshot.replay_or_demo
                        )
                        if (
                            decision.action is not None
                            and leased_action is None
                        ):
                            observed_frame = read_game_frame(process)
                            decision_age = observed_frame - snapshot.frame
                            delivery_age = bounded_delivery_age(
                                snapshot.frame, observed_frame
                            )
                            current_action = action_from_input(snapshot.input_mask)
                            if delivery_age is None:
                                # Never issue an aged proposal. A separately
                                # recorded constant-action certificate may keep
                                # the observed current input, with at least one
                                # covered frame left, while we retry from a fresh
                                # snapshot. This cannot publish a new action.
                                if covered_current_retry(
                                    snapshot.frame,
                                    observed_frame,
                                    max(decision.horizon, decision.held_horizon),
                                    current_action,
                                    decision.safe_actions,
                                ):
                                    stale_retry = True
                                else:
                                    decision = Decision(
                                        None,
                                        decision.safe_actions,
                                        0.0,
                                        decision.horizon,
                                        "unsupported-delivery-age",
                                        decision.effort_horizon,
                                        decision.effort_safe_count,
                                        decision.repairable_count,
                                        decision.held_horizon,
                                    )
                            else:
                                certified_max_delay = (
                                    BASE_CERTIFIED_DELIVERY_MAX_FRAMES
                                )
                                required_max_delay = (
                                    required_changed_action_delivery_delay(
                                        delivery_age
                                    )
                                )
                                if (
                                    decision.action != current_action
                                    and decision.reason != "same-frame-delivery-only"
                                    and required_max_delay > certified_max_delay
                                    and required_max_delay <= HARD_SAFETY_HORIZON
                                ):
                                    # Normal Hard-4 authority covers combined
                                    # solve age, the possible SendInput frame
                                    # crossing, and native pickup. Prove only
                                    # the selected changed action when the
                                    # measured publication bound is longer.
                                    if solver.selected_delivery_safe(
                                        snapshot,
                                        decision.action,
                                        required_max_delay,
                                    ):
                                        certified_max_delay = required_max_delay
                                    if (
                                        certified_max_delay >= required_max_delay
                                        and read_game_frame(process) - snapshot.frame
                                        != delivery_age
                                    ):
                                        # The measured age changed during the
                                        # extra proof, so its bound is obsolete.
                                        certified_max_delay = (
                                            BASE_CERTIFIED_DELIVERY_MAX_FRAMES
                                        )
                                if not changed_action_delivery_supported(
                                    delivery_age,
                                    current_action,
                                    decision.action,
                                    certified_max_delay,
                                ):
                                    # Retaining current input cannot publish an
                                    # uncertified transition; retry from a fresh
                                    # snapshot when the timing bound is too old.
                                    stale_retry = True
                            if (
                                not stale_retry
                                and decision.reason == "same-frame-delivery-only"
                                and delivery_age != 0
                            ):
                                # This fallback deliberately omits delay 3;
                                # it can publish only before the snapshot ages.
                                stale_retry = True
                        if decision.action is not None and not stale_retry:
                            events = keyboard.apply(decision.action)
                            transition_count += len(events)
                            if leased_action is None and events:
                                issued_frame = read_game_frame(process)
                                command_issue_age = issued_frame - snapshot.frame
                                input_lease.issued(
                                    issued_frame, decision.action
                                )
                        elif decision.action is None:
                            transition_count += len(keyboard.release_all())
                            input_lease.cleared()
                            authority_stop = authority_unavailable(decision)
                            if authority_stop and args.continue_on_failure:
                                solver.reset_plan()
                            if authority_stop and not args.continue_on_failure:
                                exit_code = 2

                row_reason = "stale-decision-retry" if stale_retry else decision.reason
                if (
                    decision.horizon == HARD_SAFETY_HORIZON
                    and decision.reason == "ok"
                ):
                    solver.observe_publication(stale_retry)
                if stale_retry:
                    action_name = "stale-retry"
                elif decision.action is not None:
                    action_name = decision.action.name
                elif authority_stop:
                    action_name = "authority-stop"
                else:
                    action_name = "no-action"
                writer.writerow((
                    f"{time.monotonic() - started:.3f}", snapshot.frame, snapshot.stage,
                    snapshot.player_state, f"{snapshot.x:.3f}", f"{snapshot.y:.3f}",
                    len(snapshot.bullets), snapshot.laser_count, len(snapshot.enemies),
                    len(snapshot.spawners),
                    _emitter_trace(snapshot),
                    len(snapshot.despawning_bullets), snapshot.bullet_read_retries,
                    snapshot.rng_seed, snapshot.rng_generation,
                    snapshot.current_power, snapshot.timeline_time,
                    int(snapshot.replay_or_demo),
                    f"0x{snapshot.input_mask:04X}",
                    f"0x{(keyboard.base_input_mask if keyboard is not None else 0):04X}",
                    transition_count, decision_age, command_issue_age,
                    int(leased_action is not None),
                    f"{snapshot.frame_multiplier:.3f}", action_name,
                    len(decision.safe_actions), decision.horizon, decision.held_horizon,
                    decision.effort_horizon,
                    decision.effort_safe_count, decision.repairable_count,
                    f"{decision.clearance:.3f}",
                    f"{solve_ms:.3f}",
                    int(dialogue.active),
                    int(dialogue.active and dialogue.skippable), int(dialogue.pulsed_shoot),
                    int(authority_stop), row_reason,
                ))
                if snapshot.frame % 60 == 0 or row_reason != last_reason:
                    output.flush()
                    print(
                        f"f={snapshot.frame} stage={snapshot.stage} state={snapshot.player_state} "
                        f"bullets={len(snapshot.bullets)} enemies={len(snapshot.enemies)} "
                        f"spawners={len(snapshot.spawners)} "
                        f"action={action_name} "
                        f"safe={len(decision.safe_actions)} effort_safe={decision.effort_safe_count} "
                        f"repairable={decision.repairable_count} "
                        f"h={decision.horizon}/{decision.held_horizon} reason={row_reason}",
                        flush=True,
                    )
                last_reason = row_reason
                if authority_stop:
                    output.flush()
                    if args.continue_on_failure:
                        if not diagnostic_failure_active or hit:
                            diagnostic_events.append({
                                "sequence": len(diagnostic_events) + 1,
                                "wall_s": time.monotonic() - started,
                                "frame": snapshot.frame,
                                "stage": snapshot.stage,
                                "physical_hit": hit,
                                "reason": decision.reason,
                                "snapshot": asdict(snapshot),
                                "previous_snapshot": (
                                    asdict(prior_snapshot)
                                    if prior_snapshot is not None else None
                                ),
                                "decision": asdict(decision),
                                "held_before_release": held_before_authority,
                            })
                            diagnostic_path.write_text(
                                json.dumps(
                                    diagnostic_events,
                                    indent=2,
                                    sort_keys=True,
                                ),
                                encoding="utf-8",
                            )
                            print(
                                f"diagnostic event {len(diagnostic_events)} "
                                f"at f={snapshot.frame}: {decision.reason}; "
                                f"released movement and continuing; "
                                f"events={diagnostic_path}",
                                flush=True,
                            )
                        diagnostic_failure_active = True
                        previous_snapshot = snapshot
                        continue
                    failure_path = trace_path.with_name(
                        "th06_failure_latest.json"
                        if args.rng_seed is None
                        else f"th06_failure_rng{args.rng_seed:04x}_latest.json"
                    )
                    failure_path.write_text(
                        json.dumps(
                            {
                                "wall_s": time.monotonic() - started,
                                "snapshot": asdict(snapshot),
                                "snapshot_history": [
                                    asdict(item) for item in snapshot_history
                                ],
                                "previous_snapshot": (
                                    asdict(prior_snapshot) if prior_snapshot is not None else None
                                ),
                                "decision": asdict(decision),
                                "held_before_stop": held_before_authority,
                                "held_desired_input": keyboard.base_input_mask if keyboard else 0,
                                "input_lease": (
                                    asdict(leased_action) if leased_action is not None else None
                                ),
                                "ecl_instruction_cache": [
                                    asdict(instruction)
                                    for instruction in process.ecl_instruction_cache.values()
                                ],
                                "ecl_timeline_instruction_cache": [
                                    asdict(instruction)
                                    for instruction in process.ecl_timeline_instruction_cache.values()
                                ],
                            },
                            indent=2,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                    print(
                        f"authority unavailable at f={snapshot.frame}: {decision.reason}; "
                        f"counterexample={failure_path}; stopping trial",
                        flush=True,
                    )
                    break
                if decision.action is not None:
                    diagnostic_failure_active = False
                previous_snapshot = snapshot
    finally:
        cleanup()
    return exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", default=r"D:\Entertainment\Game\Touhou\th06")
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--patch-lives", action="store_true")
    parser.add_argument("--start-hard", action="store_true", help="source-grounded Hard / Reimu-A menu start")
    parser.add_argument("--practice-stage", type=int, choices=range(1, 7), metavar="1..6")
    parser.add_argument("--stop-game", action="store_true", help="stop the exact attached trial process on exit")
    parser.add_argument("--save-replay", action="store_true", help="save and validate a non-Practice result replay")
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help=(
            "Practice diagnostic: record HIT/authority events, release input, "
            "and continue until the result path"
        ),
    )
    parser.add_argument("--replay-slot", type=int, choices=range(1, 16), metavar="1..15")
    parser.add_argument("--replay-name", default="TH06")
    parser.add_argument(
        "--rng-seed",
        type=lambda value: int(value, 0),
        choices=range(0x10000),
        metavar="0..0xffff",
        help=(
            "diagnostic only: fix the source RNG initial seed while keeping "
            "the original generator and consumer order"
        ),
    )
    parser.add_argument("--seconds", type=float, default=0.0, help="zero runs until Ctrl+C")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(sys.argv[1:] if argv is None else argv))

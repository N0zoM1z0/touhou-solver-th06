"""Thin runtime loop for the TH06 baseline."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from .actuator import Keyboard
from .dialogue import DialogueSkipper, DialogueState
from .menu import start_hard_reimu_a, start_hard_reimu_a_practice
from .model import Decision, PLAYER_ALIVE, PLAYER_DEAD
from .native import (
    ADDR_LIFE_PATCH,
    TARGET_SHA256,
    attach_exact,
    read_snapshot,
    read_supervisor_state,
)
from .replay import ReplaySaver
from .solver import HARD_SAFETY_HORIZON, Solver
from .trial import PracticeTrial, physical_hit


PASSIVE_NO_ACTION_REASONS = frozenset(("menu", "player-not-active", "time-stopped"))


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
    process = attach_exact(Path(args.game_dir).resolve())
    keyboard = Keyboard(process.pid) if args.armed else None
    dialogue_skipper = DialogueSkipper(process, keyboard) if keyboard is not None else None
    replay_saver = (
        ReplaySaver(Path(args.game_dir).resolve(), keyboard, args.replay_name, args.replay_slot)
        if args.save_replay and keyboard is not None
        else None
    )
    if args.practice_stage is not None:
        trace_name = f"th06_practice_stage{args.practice_stage}_latest.csv"
    else:
        trace_name = "th06_baseline_latest.csv" if args.armed else "th06_observe_latest.csv"
    trace_path = Path(__file__).resolve().parents[2] / "artifacts" / trace_name
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    solver = Solver()
    previous_state: int | None = None
    practice_trial = PracticeTrial() if args.practice_stage is not None else None
    last_frame: int | None = None
    last_reason: str | None = None
    exit_code = 0
    started = time.monotonic()

    def cleanup() -> None:
        try:
            if keyboard is not None:
                keyboard.release_all()
        finally:
            try:
                if args.stop_game:
                    process.terminate()
            finally:
                process.close()
        cleanup_message = "released all keys" if keyboard is not None else "no input was created"
        if args.stop_game:
            cleanup_message += f"; stopped exact pid {process.pid}"
        print(f"{cleanup_message}; trace={trace_path}", flush=True)

    try:
        print(f"verified pid={process.pid} sha256={TARGET_SHA256}", flush=True)
        print(f"safety backend: {solver.backend}", flush=True)
        if args.patch_lives:
            print(f"life patch: {process.patch_lives()} at 0x{ADDR_LIFE_PATCH:08X}", flush=True)
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
                "replay", "native_input", "held_desired_input", "input_transitions",
                "frame_multiplier", "action", "safe", "horizon", "effort_horizon",
                "effort_safe",
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
                snapshot = read_snapshot(process)
                if snapshot.frame == last_frame:
                    time.sleep(0.001)
                    continue
                last_frame = snapshot.frame
                hit = physical_hit(previous_state, snapshot.player_state)
                if previous_state is not None:
                    solver.observe(not hit)
                previous_state = snapshot.player_state
                solve_started = time.perf_counter()
                if hit:
                    decision = Decision(
                        None,
                        (),
                        0.0,
                        HARD_SAFETY_HORIZON,
                        "physical-hit",
                        HARD_SAFETY_HORIZON,
                    )
                else:
                    decision = solver.decide(snapshot)
                solve_ms = (time.perf_counter() - solve_started) * 1000.0
                dialogue = DialogueState(False, False, False)
                transition_count = 0
                authority_stop = False

                if args.armed:
                    assert keyboard is not None
                    assert dialogue_skipper is not None
                    if not keyboard.foreground():
                        keyboard.release_all()
                        decision = Decision(None, (), 0.0, 0, "not-foreground")
                    else:
                        dialogue = dialogue_skipper.update(
                            not snapshot.in_menu and not snapshot.replay_or_demo
                        )
                        if decision.action is not None:
                            transition_count += len(keyboard.apply(decision.action))
                        else:
                            transition_count += len(keyboard.release_all())
                            authority_stop = authority_unavailable(decision)
                            if authority_stop:
                                exit_code = 2

                if decision.action is not None:
                    action_name = decision.action.name
                elif authority_stop:
                    action_name = "authority-stop"
                else:
                    action_name = "no-action"
                writer.writerow((
                    f"{time.monotonic() - started:.3f}", snapshot.frame, snapshot.stage,
                    snapshot.player_state, f"{snapshot.x:.3f}", f"{snapshot.y:.3f}",
                    len(snapshot.bullets), snapshot.laser_count, int(snapshot.replay_or_demo),
                    f"0x{snapshot.input_mask:04X}",
                    f"0x{(keyboard.base_input_mask if keyboard is not None else 0):04X}",
                    transition_count, f"{snapshot.frame_multiplier:.3f}", action_name,
                    len(decision.safe_actions), decision.horizon, decision.effort_horizon,
                    decision.effort_safe_count,
                    f"{decision.clearance:.3f}",
                    f"{solve_ms:.3f}", int(dialogue.active),
                    int(dialogue.active and dialogue.skippable), int(dialogue.pulsed_shoot),
                    int(authority_stop), decision.reason,
                ))
                if snapshot.frame % 60 == 0 or decision.reason != last_reason:
                    output.flush()
                    print(
                        f"f={snapshot.frame} stage={snapshot.stage} state={snapshot.player_state} "
                        f"bullets={len(snapshot.bullets)} action={action_name} "
                        f"safe={len(decision.safe_actions)} effort_safe={decision.effort_safe_count} "
                        f"h={decision.horizon} reason={decision.reason}",
                        flush=True,
                    )
                last_reason = decision.reason
                if authority_stop:
                    output.flush()
                    failure_path = trace_path.with_name("th06_failure_latest.json")
                    failure_path.write_text(
                        json.dumps(
                            {
                                "wall_s": time.monotonic() - started,
                                "snapshot": asdict(snapshot),
                                "decision": asdict(decision),
                                "held_desired_input": keyboard.base_input_mask if keyboard else 0,
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
    parser.add_argument("--replay-slot", type=int, choices=range(1, 16), metavar="1..15")
    parser.add_argument("--replay-name", default="TH06")
    parser.add_argument("--seconds", type=float, default=0.0, help="zero runs until Ctrl+C")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(sys.argv[1:] if argv is None else argv))

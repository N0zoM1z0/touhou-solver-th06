"""Thin runtime loop for the TH06 baseline."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

from .actuator import Keyboard
from .dialogue import DialogueSkipper, DialogueState
from .menu import start_hard_reimu_a
from .model import Decision, PLAYER_ALIVE, PLAYER_DEAD
from .native import ADDR_LIFE_PATCH, TARGET_SHA256, attach_exact, read_snapshot
from .solver import Solver


def run(args: argparse.Namespace) -> int:
    if os.name != "nt":
        raise RuntimeError("run this entry point with Windows Python")
    if args.start_hard and not args.armed:
        raise RuntimeError("--start-hard requires --armed")
    process = attach_exact(Path(args.game_dir).resolve())
    keyboard = Keyboard(process.pid) if args.armed else None
    dialogue_skipper = DialogueSkipper(process, keyboard) if keyboard is not None else None
    trace_name = "th06_baseline_latest.csv" if args.armed else "th06_observe_latest.csv"
    trace_path = Path(__file__).resolve().parents[2] / "artifacts" / trace_name
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    solver = Solver()
    previous_state: int | None = None
    last_frame: int | None = None
    last_reason: str | None = None
    started = time.monotonic()
    try:
        print(f"verified pid={process.pid} sha256={TARGET_SHA256}", flush=True)
        if args.patch_lives:
            print(f"life patch: {process.patch_lives()} at 0x{ADDR_LIFE_PATCH:08X}", flush=True)
        if args.start_hard:
            assert keyboard is not None
            start_hard_reimu_a(process, keyboard)
            print("menu: Hard / Reimu-A selected", flush=True)
        print("armed" if args.armed else "observe-only", flush=True)
    except Exception:
        if keyboard is not None:
            keyboard.release_all()
        process.close()
        raise
    try:
        with trace_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow((
                "wall_s", "frame", "stage", "state", "x", "y", "bullets", "lasers",
                "replay", "native_input", "frame_multiplier", "action", "safe", "horizon",
                "clearance", "solve_ms", "dialogue", "skip", "advance_pulse", "reason",
            ))
            while not args.seconds or time.monotonic() - started < args.seconds:
                snapshot = read_snapshot(process)
                if snapshot.frame == last_frame:
                    time.sleep(0.001)
                    continue
                last_frame = snapshot.frame
                if previous_state is not None:
                    solver.observe(not (previous_state == PLAYER_ALIVE and snapshot.player_state == PLAYER_DEAD))
                previous_state = snapshot.player_state
                solve_started = time.perf_counter()
                decision = solver.decide(snapshot)
                solve_ms = (time.perf_counter() - solve_started) * 1000.0
                dialogue = DialogueState(False, False, False)

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
                            keyboard.apply(decision.action)
                        elif decision.reason in ("menu", "player-not-active", "time-stopped"):
                            keyboard.release_all()
                        # Empty or unsupported authority is no-write. It does
                        # not replace the last complete mask with a guess.

                action_name = decision.action.name if decision.action else "no-write"
                writer.writerow((
                    f"{time.monotonic() - started:.3f}", snapshot.frame, snapshot.stage,
                    snapshot.player_state, f"{snapshot.x:.3f}", f"{snapshot.y:.3f}",
                    len(snapshot.bullets), snapshot.laser_count, int(snapshot.replay_or_demo),
                    f"0x{snapshot.input_mask:04X}", f"{snapshot.frame_multiplier:.3f}", action_name,
                    len(decision.safe_actions), decision.horizon, f"{decision.clearance:.3f}",
                    f"{solve_ms:.3f}", int(dialogue.active),
                    int(dialogue.active and dialogue.skippable), int(dialogue.pulsed_shoot),
                    decision.reason,
                ))
                if snapshot.frame % 60 == 0 or decision.reason != last_reason:
                    output.flush()
                    print(
                        f"f={snapshot.frame} stage={snapshot.stage} state={snapshot.player_state} "
                        f"bullets={len(snapshot.bullets)} action={action_name} "
                        f"safe={len(decision.safe_actions)} h={decision.horizon} reason={decision.reason}",
                        flush=True,
                    )
                last_reason = decision.reason
    finally:
        if keyboard is not None:
            keyboard.release_all()
        process.close()
        cleanup = "released all keys" if keyboard is not None else "no input was created"
        print(f"{cleanup}; trace={trace_path}", flush=True)
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-dir", default=r"D:\Entertainment\Game\Touhou\th06")
    parser.add_argument("--armed", action="store_true")
    parser.add_argument("--patch-lives", action="store_true")
    parser.add_argument("--start-hard", action="store_true", help="source-grounded Hard / Reimu-A menu start")
    parser.add_argument("--seconds", type=float, default=0.0, help="zero runs until Ctrl+C")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(sys.argv[1:] if argv is None else argv))

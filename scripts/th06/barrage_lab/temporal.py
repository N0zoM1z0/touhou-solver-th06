"""Small temporal fuzz gate for proposal publication and expiry semantics."""

from __future__ import annotations

from dataclasses import dataclass
import random

from ..model import (
    BUTTON_FOCUS,
    BUTTON_DOWN,
    BUTTON_LEFT,
    BUTTON_RIGHT,
    BUTTON_UP,
    CONTROL_ACTIONS,
    Action,
    SafeAction,
    Snapshot,
)
from ..ranking import ProposalRanker


def _input_mask(action: Action) -> int:
    mask = BUTTON_FOCUS if action.focused else 0
    if action.dx < 0:
        mask |= BUTTON_LEFT
    elif action.dx > 0:
        mask |= BUTTON_RIGHT
    if action.dy < 0:
        mask |= BUTTON_UP
    elif action.dy > 0:
        mask |= BUTTON_DOWN
    return mask


def _snapshot(frame: int, action: Action) -> Snapshot:
    return Snapshot(
        frame=frame,
        stage=0,
        player_state=0,
        x=192.0,
        y=224.0,
        half_width=1.25,
        half_height=1.25,
        normal_speed=4.0,
        focus_speed=2.0,
        normal_diagonal_speed=2.8284270763397217,
        focus_diagonal_speed=1.4142135381698608,
        frame_multiplier=1.0,
        input_mask=_input_mask(action),
        bullets=(),
        laser_count=0,
        in_menu=False,
        time_stopped=False,
        replay_or_demo=False,
    )


@dataclass(frozen=True)
class TemporalSweepMismatch:
    seed: int
    focused: bool
    proposed_action: str
    commitment_frames: int
    pickup_frame: int
    observed_action: str


@dataclass(frozen=True)
class TemporalSweepSummary:
    seeds: int
    focused_cases: int
    fast_cases: int


def run_proposal_temporal_sweep(
    seeds: int, *, maximum_commitment_frames: int = 8,
) -> tuple[TemporalSweepSummary, TemporalSweepMismatch | None]:
    """Fuzz proposal -> pickup -> evidence-loss -> expiry sequences.

    The synthetic Hard sets are the authority input to the ranker.  The gate
    checks only the authority boundary: a directional soft proposal may be
    held through its bounded commitment, but cannot become an unbounded route
    when a focus-matched neutral action remains freshly Hard-certified.
    """
    if seeds <= 0 or maximum_commitment_frames <= 0:
        raise ValueError("temporal sweep bounds must be positive")
    focused_cases = 0
    fast_cases = 0
    for seed in range(seeds):
        chooser = random.Random(seed)
        focused = bool(chooser.getrandbits(1))
        if focused:
            focused_cases += 1
        else:
            fast_cases += 1
        family = tuple(
            action for action in CONTROL_ACTIONS
            if action.focused == focused
        )
        neutral = next(
            action for action in family if action.dx == action.dy == 0
        )
        proposed = chooser.choice(tuple(
            action for action in family if action.dx != 0 or action.dy != 0
        ))
        candidates = [
            SafeAction(neutral, chooser.uniform(1.0, 100.0), 192.0, 224.0),
            SafeAction(
                proposed,
                chooser.uniform(1.0, 100.0),
                192.0 + proposed.dx * (2.0 if focused else 4.0),
                224.0 + proposed.dy * (2.0 if focused else 4.0),
            ),
        ]
        distractors = [
            action for action in family
            if action not in (neutral, proposed)
        ]
        chooser.shuffle(distractors)
        for action in distractors[:chooser.randrange(0, 4)]:
            candidates.append(SafeAction(
                action,
                chooser.uniform(1.0, 100.0),
                192.0 + action.dx * (2.0 if focused else 4.0),
                224.0 + action.dy * (2.0 if focused else 4.0),
            ))
        chooser.shuffle(candidates)
        hard = tuple(candidates)
        commitment_frames = chooser.randrange(
            1, maximum_commitment_frames + 1
        )
        base_frame = chooser.randrange(0, 10000)
        ranker = ProposalRanker()
        selected = ranker.choose(
            _snapshot(base_frame, neutral),
            hard,
            frozenset((proposed,)),
            commitment_frames=commitment_frames,
        )
        if selected.action != proposed:
            return (
                TemporalSweepSummary(seed + 1, focused_cases, fast_cases),
                TemporalSweepMismatch(
                    seed, focused, proposed.name, commitment_frames,
                    base_frame, selected.action.name,
                ),
            )

        # Input delivery is controlled by the lease outside the ranker, so no
        # choose call occurs during this bounded pickup gap.
        pickup_frame = base_frame + chooser.randrange(1, 4)
        if pickup_frame < base_frame + commitment_frames:
            ranker.choose(_snapshot(pickup_frame, proposed), hard)
        expiry_frame = base_frame + commitment_frames
        observed = ranker.choose(
            _snapshot(max(pickup_frame, expiry_frame), proposed), hard
        )
        if observed.action != neutral:
            return (
                TemporalSweepSummary(seed + 1, focused_cases, fast_cases),
                TemporalSweepMismatch(
                    seed, focused, proposed.name, commitment_frames,
                    pickup_frame, observed.action.name,
                ),
            )
    return TemporalSweepSummary(seeds, focused_cases, fast_cases), None

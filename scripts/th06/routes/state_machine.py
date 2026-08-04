"""Small source-clock state machines owned by one route phase.

The common solver never evaluates these states.  A route first selects one
exact source phase, then asks only that phase's machine for an intent.  This
keeps tuned policy states from becoming another global scene-classifier tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import Action, Snapshot
from .base import RouteIntent


@dataclass(frozen=True)
class PolicyState:
    """One inspectable state inside a single source phase."""

    start_time: int
    state_id: str
    algorithm: str
    horizon: int
    target: tuple[float, float] | None
    commitment_frames: int = 4
    preferred_actions: tuple[Action, ...] = ()
    provenance: str = ""

    def intent(self, phase_id: str) -> RouteIntent:
        return RouteIntent(
            phase_id=phase_id,
            policy_state=self.state_id,
            algorithm=self.algorithm,
            horizon=self.horizon,
            target=self.target,
            commitment_frames=self.commitment_frames,
            preferred_actions=self.preferred_actions,
            provenance=self.provenance,
        )


@dataclass(frozen=True)
class TimelineStateMachine:
    """Deterministic phase-local machine driven by the source timeline clock.

    States are absolute source times so an offline replay can seek directly to
    a frame without inheriting mutable controller history.  RNG-, resource-,
    or callback-conditioned phases may implement the same ``intent`` contract
    with their own private machine; they do not require a new common-solver
    branch.
    """

    phase_id: str
    states: tuple[PolicyState, ...]

    def __post_init__(self) -> None:
        if not self.states:
            raise ValueError("phase state machine cannot be empty")
        starts = tuple(state.start_time for state in self.states)
        if starts != tuple(sorted(starts)) or len(starts) != len(set(starts)):
            raise ValueError("phase policy states need unique sorted source times")
        state_ids = tuple(state.state_id for state in self.states)
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("phase policy state IDs must be unique")

    @property
    def start_time(self) -> int:
        return self.states[0].start_time

    def state(self, timeline_time: int) -> PolicyState:
        eligible = tuple(
            state for state in self.states if state.start_time <= timeline_time
        )
        if not eligible:
            raise ValueError(
                f"phase {self.phase_id} has no state at t{timeline_time}"
            )
        return eligible[-1]

    def intent(self, snapshot: Snapshot) -> RouteIntent:
        return self.state(snapshot.timeline_time).intent(self.phase_id)
